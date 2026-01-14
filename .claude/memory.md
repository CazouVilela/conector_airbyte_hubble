# Conector Airbyte Hubble - Documentacao Tecnica

## Informacoes do Projeto

| Campo | Valor |
|-------|-------|
| **Nome** | source-hubble |
| **Versao** | 1.0.0 |
| **Stack** | Python 3.10+, Airbyte CDK 7.x, Docker |
| **Status** | Producao |
| **Autor** | Cazou Vilela (cazou@hubtalent.com.br) |
| **Repositorio** | https://github.com/CazouVilela/conector_airbyte_hubble |

## Visao Geral

Conector customizado para Airbyte que extrai dados da API Hubble (data2apis.com). Desenvolvido para resolver limitacoes criticas do conector generico de API do Airbyte.

### Problemas Resolvidos

| Problema | Causa | Solucao Implementada |
|----------|-------|---------------------|
| JSON corrompido | Null bytes (`\u0000`) nos dados | Limpeza automatica via `_clean_null_bytes()` |
| Perda de registros | Paginacao por offset (`$skip`) | Paginacao por cursor (`_id`) |
| Sync lento | Full sync a cada execucao | Sync incremental via `updatedAt` |
| Rigidez | Codigo fixo por endpoint | Streams dinamicos via configuracao |
| Falhas intermitentes | API instavel | Retry com backoff exponencial |
| Seguranca | URLs nao validadas | Validacao obrigatoria HTTPS |

### Features (v1.0.0)

1. Limpeza automatica de null bytes que corrompem JSON
2. Paginacao por cursor (`_id`) em vez de `$skip` (offset)
3. Sync incremental via campo `updatedAt`
4. Streams dinamicos configuraveis via UI do Airbyte
5. Retry com backoff exponencial (max 5 tentativas)
6. Rate limiting configuravel
7. Schema discovery dinamico
8. Logging estruturado
9. Validacao de URLs (apenas HTTPS)
10. Testes unitarios com pytest

---

## Arquitetura

### Stack Tecnologico

```
Python 3.10+ (compativel ate 3.13)
Airbyte CDK >= 7.0.0, < 8.0.0
Requests >= 2.28.0
Backoff (retry automatico)
Docker (airbyte/python-connector-base:4.1.0)
```

### Estrutura de Arquivos

```
conector_airbyte_hubble/
├── .claude/
│   └── memory.md              # Este arquivo (documentacao tecnica)
├── source_hubble/
│   ├── __init__.py            # Exporta SourceHubble
│   ├── source.py              # Codigo principal (513 linhas)
│   └── spec.yaml              # Especificacao UI do Airbyte
├── tests/
│   ├── __init__.py            # Pacote de testes
│   ├── conftest.py            # Fixtures pytest
│   └── test_source.py         # Testes unitarios (479 linhas)
├── main.py                    # Entry point do conector
├── setup.py                   # Configuracao do pacote Python
├── Dockerfile                 # Build da imagem Docker
├── metadata.yaml              # Metadados Airbyte
├── pytest.ini                 # Configuracao pytest
├── README.md                  # Documentacao para usuarios
└── .gitignore                 # Arquivos ignorados
```

### Diagrama de Fluxo

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Airbyte UI    │────▶│  SourceHubble   │────▶│   API Hubble    │
│                 │     │                 │     │ data2apis.com   │
└─────────────────┘     └────────┬────────┘     └────────┬────────┘
                                 │                       │
                                 ▼                       ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │  HubbleStream   │◀────│   JSON + Null   │
                        │                 │     │     Bytes       │
                        └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
             ┌──────────┐ ┌──────────┐ ┌──────────┐
             │  Limpa   │ │ Pagina   │ │  Infere  │
             │  Nulls   │ │ Cursor   │ │  Schema  │
             └──────────┘ └──────────┘ └──────────┘
                    │            │            │
                    └────────────┼────────────┘
                                 ▼
                        ┌─────────────────┐
                        │    Destino      │
                        │ (PG, BQ, etc)   │
                        └─────────────────┘
```

---

## Classes e Funcoes

### Excecoes

#### HubbleConfigError
```python
class HubbleConfigError(Exception):
    """Erro de configuracao do conector Hubble."""
    pass
```
Lancada quando configuracoes sao invalidas (URLs, nomes de stream, etc).

#### HubbleAPIError
```python
class HubbleAPIError(Exception):
    """Erro na comunicacao com a API Hubble."""
    pass
```
Lancada em falhas de comunicacao com a API.

### Funcoes de Validacao

#### validate_url(url, field_name)
```python
def validate_url(url: str, field_name: str = "URL") -> None:
    """
    Valida se uma URL e valida e segura (HTTPS).

    Args:
        url: URL para validar
        field_name: Nome do campo para mensagem de erro

    Raises:
        HubbleConfigError: Se a URL for invalida
    """
```
**Validacoes:**
- URL nao pode ser vazia
- Deve usar protocolo HTTPS
- Deve ter dominio valido
- Nao pode conter caracteres perigosos: `< > " ' { } | \ ^ \``

#### validate_stream_name(name)
```python
def validate_stream_name(name: str) -> None:
    """
    Valida nome do stream.

    Args:
        name: Nome do stream

    Raises:
        HubbleConfigError: Se o nome for invalido
    """
```
**Validacoes:**
- Nao pode ser vazio
- Padrao regex: `^[a-z][a-z0-9_]*$`
- Deve comecar com letra minuscula
- Apenas letras minusculas, numeros e underscore

### Classe HubbleStream

```python
class HubbleStream(HttpStream):
    """
    Stream HTTP customizado para API Hubble.

    Attributes:
        http_method: str = "POST"
        primary_key: str = "_id"
        cursor_field: str = "updatedAt"
        max_retries: int = 5
        retry_factor: int = 2
    """
```

#### Construtor
```python
def __init__(
    self,
    authenticator: TokenAuthenticator,
    config: Mapping[str, Any],
    stream_name: str,
    endpoint_url: str,
    **kwargs
):
    """
    Inicializa o stream com configuracoes.

    Args:
        authenticator: Autenticador Bearer Token
        config: Configuracao do conector
        stream_name: Nome do stream (validado)
        endpoint_url: URL completa do endpoint (validada)
    """
```

#### Propriedades
| Propriedade | Tipo | Descricao |
|-------------|------|-----------|
| `url_base` | str | Base da URL (ex: https://hub.data2apis.com/) |
| `name` | str | Nome do stream |
| `state` | MutableMapping | Estado do cursor para sync incremental |

#### Metodos Principais

**_clean_null_bytes(text)**
```python
def _clean_null_bytes(self, text: str) -> str:
    """
    Remove null bytes que corrompem JSON.

    Args:
        text: Texto com possiveis null bytes

    Returns:
        str: Texto limpo
    """
```

**_infer_json_type(value)**
```python
def _infer_json_type(self, value: Any) -> dict:
    """
    Infere tipo JSON Schema a partir de um valor Python.

    Args:
        value: Valor Python para inferir tipo

    Returns:
        dict: Definicao de tipo JSON Schema
    """
```
Mapeamento:
- `None` -> `{"type": "null"}`
- `bool` -> `{"type": ["null", "boolean"]}`
- `int` -> `{"type": ["null", "integer"]}`
- `float` -> `{"type": ["null", "number"]}`
- `str` -> `{"type": ["null", "string"]}` (com `format: date-time` se ISO date)
- `list` -> `{"type": ["null", "array"], "items": {}}`
- `dict` -> `{"type": ["null", "object"], "additionalProperties": true}`

**_discover_schema_from_record(record)**
```python
def _discover_schema_from_record(self, record: Mapping[str, Any]) -> None:
    """
    Descobre schema dinamicamente a partir do primeiro registro.

    Args:
        record: Primeiro registro retornado pela API
    """
```

**parse_response(response, ...)**
```python
def parse_response(
    self,
    response: requests.Response,
    stream_state: Mapping[str, Any] = None,
    stream_slice: Mapping[str, Any] = None,
    next_page_token: Mapping[str, Any] = None,
) -> Iterable[Mapping]:
    """
    Processa response da API e extrai registros.

    Yields:
        Mapping: Cada registro da API
    """
```

**next_page_token(response)**
```python
def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
    """
    Determina se ha mais paginas usando cursor por _id.

    Args:
        response: Response HTTP

    Returns:
        Optional[Mapping]: {"last_id": "..."} ou None se ultima pagina
    """
```

**request_body_json(...)**
```python
def request_body_json(
    self,
    stream_state: Mapping[str, Any] = None,
    stream_slice: Mapping[str, Any] = None,
    next_page_token: Mapping[str, Any] = None,
) -> Optional[Mapping]:
    """
    Monta body JSON para request POST.

    Returns:
        Mapping: Body no formato da API Hubble
    """
```
Formato do body:
```json
{
  "$method": "find",
  "params": {
    "query": {
      "$limit": 500,
      "$sort": {"_id": 1},
      "updatedAt": {"$gte": "2024-01-01T00:00:00.000Z"},
      "_id": {"$gt": "ultimo_id"}
    }
  }
}
```

**should_retry(response)**
```python
def should_retry(self, response: requests.Response) -> bool:
    """
    Determina se deve fazer retry baseado no status code.

    Returns:
        bool: True para status 429, 500, 502, 503, 504
    """
```

**backoff_time(response)**
```python
def backoff_time(self, response: requests.Response) -> Optional[float]:
    """
    Calcula tempo de backoff para retry.

    Returns:
        Optional[float]: Segundos para aguardar ou None para default CDK
    """
```
- 429 (Rate Limit): Respeita header `Retry-After` ou 60s
- Outros: Usa backoff exponencial do CDK

### Classe SourceHubble

```python
class SourceHubble(AbstractSource):
    """
    Source Airbyte para API Hubble (data2apis.com).
    """
```

#### Metodos

**check_connection(logger, config)**
```python
def check_connection(self, logger, config) -> Tuple[bool, Any]:
    """
    Verifica conexao com a API.

    Args:
        logger: Logger do Airbyte
        config: Configuracao do conector

    Returns:
        Tuple[bool, Any]: (sucesso, mensagem_erro)
    """
```
Validacoes realizadas:
1. Pelo menos um endpoint configurado
2. API token presente
3. Nomes de stream validos
4. URLs validas (HTTPS)
5. Conexao com primeiro endpoint funciona
6. Response contem campo `data`

**streams(config)**
```python
def streams(self, config: Mapping[str, Any]) -> List[Stream]:
    """
    Cria lista de streams baseado nos endpoints configurados.

    Args:
        config: Configuracao do conector

    Returns:
        List[Stream]: Lista de HubbleStream
    """
```

---

## Configuracao (spec.yaml)

### Parametros Disponiveis

| Campo | Tipo | Obrigatorio | Default | Descricao |
|-------|------|-------------|---------|-----------|
| `api_token` | string | Sim | - | Token JWT para autenticacao |
| `start_date` | string | Nao | - | Data inicial para sync (ISO format) |
| `page_size` | integer | Nao | 500 | Registros por pagina (1-1000) |
| `request_timeout` | integer | Nao | 60 | Timeout em segundos (10-300) |
| `max_retries` | integer | Nao | 5 | Max tentativas em erro (1-10) |
| `endpoints` | array | Sim | - | Lista de endpoints |

### Estrutura de Endpoint

```yaml
endpoints:
  - name: string          # Nome do stream (regex: ^[a-z][a-z0-9_]*$)
    endpoint_url: string  # URL HTTPS completa
```

### Endpoints Padrao

```yaml
endpoints:
  - name: vacancies
    endpoint_url: "https://hub.data2apis.com/dataset/all-hub-vacancies"
  - name: candidates
    endpoint_url: "https://hub.data2apis.com/dataset/all-hub-candidates"
  - name: projetos
    endpoint_url: "https://hub.data2apis.com/dataset/all-hub-projetos"
  - name: companies
    endpoint_url: "https://hub.data2apis.com/dataset/all-hub-companies"
```

### Validacao de URL (Pattern)

```regex
^https://[a-zA-Z0-9][a-zA-Z0-9-]*(\.[a-zA-Z0-9][a-zA-Z0-9-]*)+(/[a-zA-Z0-9_.~-]*)*$
```

---

## Testes

### Estrutura de Testes

```
tests/
├── __init__.py
├── conftest.py      # Fixtures compartilhadas
└── test_source.py   # Testes unitarios
```

### Classes de Teste

| Classe | Testes | Descricao |
|--------|--------|-----------|
| `TestValidateUrl` | 5 | Validacao de URLs |
| `TestValidateStreamName` | 5 | Validacao de nomes |
| `TestHubbleStream` | 17 | Funcionalidades do stream |
| `TestSourceHubble` | 8 | Source principal |
| `TestSchemaDiscovery` | 2 | Descoberta de schema |

### Fixtures (conftest.py)

**valid_config**
```python
{
    "api_token": "test_token_123",
    "start_date": "2024-01-01T00:00:00.000Z",
    "page_size": 100,
    "request_timeout": 30,
    "max_retries": 3,
    "endpoints": [
        {"name": "vacancies", "endpoint_url": "https://hub.data2apis.com/dataset/all-hub-vacancies"},
        {"name": "candidates", "endpoint_url": "https://hub.data2apis.com/dataset/all-hub-candidates"}
    ]
}
```

**mock_response**
- Response 200 com dados validos

**mock_response_with_null_bytes**
- Response com `\u0000` para testar limpeza

**mock_response_paginated**
- Factory para criar responses paginadas

**mock_error_response**
- Response 500 para testar retry

**sample_record**
- Registro de exemplo com varios tipos de dados

### Executar Testes

```bash
cd /home/cazouvilela/projetos/conector_airbyte_hubble

# Executar todos os testes
pytest

# Com cobertura
pytest --cov=source_hubble --cov-report=html

# Verbose
pytest -v

# Teste especifico
pytest tests/test_source.py::TestHubbleStream::test_clean_null_bytes
```

### Configuracao pytest (pytest.ini)

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

---

## Build e Deploy

### Dockerfile

```dockerfile
FROM airbyte/python-connector-base:4.1.0

WORKDIR /airbyte/integration_code

COPY source_hubble ./source_hubble
COPY main.py ./
COPY setup.py ./
COPY README.md ./

RUN pip install --no-cache-dir .

ENV AIRBYTE_ENTRYPOINT="python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

LABEL io.airbyte.version=1.0.0
LABEL io.airbyte.name=airbyte/source-hubble
LABEL io.airbyte.protocol-version=0.2.0
```

### Comandos de Build

```bash
cd /home/cazouvilela/projetos/conector_airbyte_hubble

# Build da imagem
docker build -t airbyte/source-hubble:1.0.0 .

# Verificar imagem
docker images | grep source-hubble

# Carregar no Kind (Kubernetes local)
kind load docker-image airbyte/source-hubble:1.0.0 --name airbyte
```

### Testes Locais com Docker

```bash
# Ver especificacao
docker run --rm airbyte/source-hubble:1.0.0 spec

# Verificar conexao
docker run --rm -v /tmp:/tmp airbyte/source-hubble:1.0.0 \
  check --config /tmp/config.json

# Descobrir schemas
docker run --rm -v /tmp:/tmp airbyte/source-hubble:1.0.0 \
  discover --config /tmp/config.json

# Executar sync
docker run --rm -v /tmp:/tmp airbyte/source-hubble:1.0.0 \
  read --config /tmp/config.json --catalog /tmp/catalog.json
```

### Exemplo config.json

```json
{
  "api_token": "seu_token_jwt_aqui",
  "start_date": "2024-01-01T00:00:00.000Z",
  "page_size": 500,
  "request_timeout": 60,
  "max_retries": 5,
  "endpoints": [
    {
      "name": "vacancies",
      "endpoint_url": "https://hub.data2apis.com/dataset/all-hub-vacancies"
    }
  ]
}
```

### Registrar no Airbyte

1. Acesse Settings > Sources no Airbyte
2. Clique em "New Connector"
3. Preencha:
   - Name: `Source Hubble`
   - Docker Repository: `airbyte/source-hubble`
   - Docker Tag: `1.0.0`
   - Documentation URL: `https://docs.grupohub.com`

---

## Fluxo de Dados Detalhado

### Request para API

```json
POST https://hub.data2apis.com/dataset/all-hub-vacancies
Authorization: Bearer <token>
Content-Type: application/json

{
  "$method": "find",
  "params": {
    "query": {
      "$limit": 500,
      "$sort": {"_id": 1},
      "updatedAt": {"$gte": "2024-01-01T00:00:00.000Z"},
      "_id": {"$gt": "ultimo_id_pagina_anterior"}
    }
  }
}
```

### Response da API

```json
{
  "data": [
    {
      "_id": "abc123",
      "updatedAt": "2024-06-15T10:30:00.000Z",
      "createdAt": "2024-01-01T00:00:00.000Z",
      "title": "Desenvolvedor Python",
      "status": "open",
      ...
    },
    ...
  ]
}
```

### Paginacao por Cursor

```
Pagina 1: query sem _id         -> retorna _ids 1-500, ultimo = "500"
Pagina 2: _id > "500"           -> retorna _ids 501-1000, ultimo = "1000"
Pagina 3: _id > "1000"          -> retorna _ids 1001-1500, ultimo = "1500"
Pagina N: _id > "X"             -> retorna < 500, FIM
```

**Por que cursor em vez de offset?**
Se novos registros sao inseridos durante a paginacao:
- Offset ($skip): pode pular registros ou duplicar
- Cursor (_id): sempre pega todos, em ordem

### Sync Incremental

```
Execucao 1 (Full):
  1. state vazio ou start_date
  2. Extrai TODOS registros com updatedAt >= start_date
  3. Salva state = {"updatedAt": "2024-06-15T23:59:59Z"}

Execucao 2 (Incremental):
  1. state = {"updatedAt": "2024-06-15T23:59:59Z"}
  2. Filtra query: updatedAt >= state.updatedAt
  3. Extrai APENAS registros modificados
  4. Atualiza state com maior updatedAt encontrado
```

---

## Troubleshooting

### Erro: JSON Parse Error

**Sintoma**: `json.JSONDecodeError: Invalid control character`

**Causa**: Null bytes (`\u0000` ou `\x00`) no response da API

**Solucao**: Automatica via `_clean_null_bytes()`. Se persistir, verificar logs:
```
Stream 'vacancies': X null bytes removidos
```

### Erro: 401 Unauthorized

**Sintoma**: `HTTPError: 401 - Unauthorized`

**Causa**: Token JWT invalido ou expirado

**Solucao**: Gerar novo token na plataforma Hubble

### Erro: Connection Timeout

**Sintoma**: `requests.exceptions.Timeout`

**Causa**: API lenta ou indisponivel

**Solucao**:
1. Verificar status da API
2. Aumentar `request_timeout` na config (max 300s)

### Erro: 429 Rate Limit

**Sintoma**: `HTTPError: 429 - Too Many Requests`

**Causa**: Muitas requisicoes em pouco tempo

**Solucao**: Automatica - conector aguarda 60s ou valor do header `Retry-After`

### Erro: HTTPS Required

**Sintoma**: `HubbleConfigError: URL deve usar HTTPS`

**Causa**: URL com protocolo HTTP

**Solucao**: Usar apenas URLs HTTPS

### Erro: Invalid Stream Name

**Sintoma**: `HubbleConfigError: Nome do stream invalido`

**Causa**: Nome com caracteres nao permitidos

**Solucao**: Usar apenas letras minusculas, numeros e underscore, comecando com letra

### Registros Faltando/Duplicados

**Sintoma**: Quantidade de registros inconsistente

**Causa** (outros conectores): Paginacao por offset

**Solucao**: Este conector usa cursor por `_id`, evitando o problema

### Logs para Debug

```bash
# Ver logs do container
docker logs <container_id>

# Logs estruturados
# Procure por: "airbyte.source-hubble"
```

---

## Metadados (metadata.yaml)

```yaml
data:
  connectorSubtype: api
  connectorType: source
  definitionId: "hubble-source-001"
  dockerImageTag: 1.0.0
  dockerRepository: airbyte/source-hubble
  githubIssueLabel: source-hubble
  license: MIT
  name: Hubble
  registries:
    cloud:
      enabled: false
    oss:
      enabled: true
  releaseStage: alpha
  supportLevel: community
  documentationUrl: https://docs.grupohub.com
  tags:
    - language:python
```

---

## Dependencias (setup.py)

### Producao
```
airbyte-cdk>=7.0.0,<8.0.0
requests>=2.28.0
```

### Desenvolvimento/Testes
```
pytest>=7.0.0
pytest-cov>=4.0.0
pytest-mock>=3.10.0
requests-mock>=1.11.0
```

### Instalacao Local

```bash
cd /home/cazouvilela/projetos/conector_airbyte_hubble

# Instalacao basica
pip install -e .

# Com dependencias de teste
pip install -e ".[tests]"
```

---

## Referencias

- [Airbyte CDK Python](https://docs.airbyte.com/platform/connector-development/cdk-python)
- [Airbyte CDK GitHub](https://github.com/airbytehq/airbyte-python-cdk)
- [Airbyte CDK PyPI](https://pypi.org/project/airbyte-cdk/)
- [API Hubble](https://hub.data2apis.com)

---

## Changelog

### v1.0.0 (2026-01-14)
- Limpeza de null bytes (`\u0000`)
- Paginacao por cursor (`_id`)
- Sync incremental via `updatedAt`
- Streams dinamicos configuraveis
- Retry com backoff exponencial
- Rate limiting configuravel
- Schema discovery dinamico
- Logging estruturado
- Validacao de URLs (HTTPS obrigatorio)
- Testes unitarios com pytest (37 testes)

### v0.1.0 (anterior)
- Versao inicial

---

**Ultima Atualizacao**: 2026-01-14
**Versao da Documentacao**: 1.0.0
