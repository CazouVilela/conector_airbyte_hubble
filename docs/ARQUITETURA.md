# Arquitetura do Conector Hubble

## Visao Geral

O Source Hubble e um conector customizado para Airbyte que segue a arquitetura padrao do Airbyte CDK, mas com extensoes especificas para lidar com particularidades da API Hubble.

## Componentes

### 1. Entry Point (main.py)

```python
# Ponto de entrada do conector
# Recebe comandos: spec, check, discover, read
from airbyte_cdk.entrypoint import launch
from source_hubble import SourceHubble

source = SourceHubble()
launch(source, sys.argv[1:])
```

O Airbyte executa o conector via Docker com comandos padronizados:
- `spec`: Retorna especificacao de configuracao
- `check`: Valida conexao com a API
- `discover`: Descobre schemas disponiveis
- `read`: Extrai dados

### 2. Source (source_hubble/source.py)

#### Classe SourceHubble

Responsavel por:
- Validar configuracao
- Testar conexao
- Criar streams dinamicamente

```
┌─────────────────────────────────────┐
│           SourceHubble              │
├─────────────────────────────────────┤
│ + check_connection(logger, config)  │
│ + streams(config) -> List[Stream]   │
└─────────────────────────────────────┘
                    │
                    │ cria
                    ▼
┌─────────────────────────────────────┐
│          HubbleStream               │
│     (1 por endpoint configurado)    │
└─────────────────────────────────────┘
```

#### Classe HubbleStream

Stream HTTP customizado que herda de `HttpStream` do Airbyte CDK.

```
┌─────────────────────────────────────────────────────────┐
│                    HubbleStream                         │
├─────────────────────────────────────────────────────────┤
│ Atributos:                                              │
│   http_method = "POST"                                  │
│   primary_key = "_id"                                   │
│   cursor_field = "updatedAt"                            │
│   max_retries = 5                                       │
├─────────────────────────────────────────────────────────┤
│ Metodos Principais:                                     │
│   + request_body_json() -> dict     # Monta body POST   │
│   + parse_response() -> Iterable    # Processa response │
│   + next_page_token() -> dict|None  # Controla paginacao│
│   + get_json_schema() -> dict       # Retorna schema    │
├─────────────────────────────────────────────────────────┤
│ Metodos Auxiliares:                                     │
│   - _clean_null_bytes(text)         # Remove \u0000    │
│   - _infer_json_type(value)         # Infere tipo JSON │
│   - _discover_schema_from_record()  # Schema dinamico  │
└─────────────────────────────────────────────────────────┘
```

### 3. Especificacao (source_hubble/spec.yaml)

Define a UI de configuracao no Airbyte:

```yaml
connectionSpecification:
  properties:
    api_token:        # Campo obrigatorio
    start_date:       # Campo opcional
    page_size:        # Campo opcional com default
    request_timeout:  # Campo opcional com default
    max_retries:      # Campo opcional com default
    endpoints:        # Array de endpoints dinamicos
```

## Fluxo de Execucao

### 1. Check Connection

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│ Airbyte │────▶│ SourceHubble│────▶│   API       │
│         │     │   check()   │     │   Hubble    │
└─────────┘     └──────┬──────┘     └──────┬──────┘
                       │                    │
                       │  POST /endpoint    │
                       │  $limit: 1         │
                       │───────────────────▶│
                       │                    │
                       │◀───────────────────│
                       │  {"data": [...]}   │
                       │                    │
                       ▼                    │
              (True, None) ou (False, erro) │
```

### 2. Discover

```
┌─────────┐     ┌─────────────┐     ┌───────────────┐
│ Airbyte │────▶│ SourceHubble│────▶│  HubbleStream │
│         │     │   streams() │     │  (por endpoint)│
└─────────┘     └──────┬──────┘     └───────┬───────┘
                       │                    │
                       │                    │ get_json_schema()
                       │                    │─────────────────────┐
                       │                    │                     │
                       │                    │◀────────────────────┘
                       │                    │ Schema base ou      │
                       │                    │ descoberto          │
                       │◀───────────────────│                     │
                       │                    │
                       ▼
               AirbyteCatalog com streams
```

### 3. Read (Sync)

```
┌─────────┐     ┌─────────────┐     ┌───────────────┐     ┌─────────┐
│ Airbyte │────▶│ SourceHubble│────▶│  HubbleStream │────▶│   API   │
│         │     │   streams() │     │               │     │  Hubble │
└─────────┘     └─────────────┘     └───────┬───────┘     └────┬────┘
                                            │                  │
       LOOP por pagina:                     │                  │
       ┌────────────────────────────────────┤                  │
       │                                    │                  │
       │    1. request_body_json()          │                  │
       │    ─────────────────────────▶      │                  │
       │                                    │                  │
       │    2. POST com body JSON           │  request         │
       │    ────────────────────────────────┼─────────────────▶│
       │                                    │                  │
       │    3. Response {"data": [...]}     │  response        │
       │    ◀───────────────────────────────┼──────────────────│
       │                                    │                  │
       │    4. _clean_null_bytes()          │                  │
       │    5. parse_response()             │                  │
       │       - atualiza cursor            │                  │
       │       - yield records              │                  │
       │    6. next_page_token()            │                  │
       │       - None: FIM                  │                  │
       │       - {last_id}: CONTINUA        │                  │
       │                                    │                  │
       └────────────────────────────────────┘                  │
                                            │
                                            ▼
                                   Registros para destino
```

## Mecanismos Especiais

### 1. Limpeza de Null Bytes

A API Hubble ocasionalmente retorna dados com caracteres `\u0000` (null bytes) que corrompem o parse JSON:

```
Response bruto:     {"name": "Test\u0000Value"}
Apos limpeza:       {"name": "TestValue"}
```

Implementado em `_clean_null_bytes()`:
```python
text = re.sub(r'\\u0000', '', text)  # Unicode escape
text = text.replace('\x00', '')       # Byte literal
```

### 2. Paginacao por Cursor

Em vez de offset (`$skip`), usamos cursor por `_id`:

```
Offset (problematico):
  Pagina 1: $skip=0    -> ids 1-500
  [novo registro inserido, id=501]
  Pagina 2: $skip=500  -> ids 501-1000  # 501 PERDIDO!

Cursor (seguro):
  Pagina 1: sem filtro -> ids 1-500
  [novo registro inserido, id=501]
  Pagina 2: _id > 500  -> ids 501-1001  # 501 INCLUIDO
```

### 3. Schema Discovery Dinamico

Na primeira request, o conector infere o schema a partir dos dados:

```python
def _infer_json_type(value):
    if isinstance(value, bool):
        return {"type": ["null", "boolean"]}
    elif isinstance(value, int):
        return {"type": ["null", "integer"]}
    # ... etc
```

Isso permite que novos campos na API sejam automaticamente suportados.

### 4. Retry com Backoff

Status codes que disparam retry:
- 429: Rate Limit (aguarda Retry-After ou 60s)
- 500, 502, 503, 504: Erros de servidor

Backoff exponencial: 2^tentativa segundos

```
Tentativa 1: 2s
Tentativa 2: 4s
Tentativa 3: 8s
Tentativa 4: 16s
Tentativa 5: 32s (max)
```

## Seguranca

### Validacao de URL

Todas as URLs sao validadas antes de uso:
- Protocolo: Apenas HTTPS
- Dominio: Obrigatorio e valido
- Caracteres: Sem `< > " ' { } | \ ^ \``

### Autenticacao

Bearer Token via header:
```
Authorization: Bearer <api_token>
```

Token e marcado como `airbyte_secret` no spec.yaml, garantindo que seja criptografado no Airbyte.

## Configuracao do Docker

```dockerfile
FROM airbyte/python-connector-base:4.1.0

# Imagem base do Airbyte com Python e CDK

COPY source_hubble ./source_hubble
COPY main.py ./
COPY setup.py ./

RUN pip install .

ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]
```

## Dependencias

```
airbyte-cdk >= 7.0.0, < 8.0.0
  - AbstractSource
  - HttpStream
  - TokenAuthenticator
  - SyncMode
  - entrypoint

requests >= 2.28.0
  - HTTP client

backoff (via CDK)
  - Retry com backoff exponencial
```
