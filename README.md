# Source Hubble - Conector Airbyte para API Hubble

Conector customizado para [Airbyte](https://airbyte.com) que extrai dados da API Hubble (data2apis.com).

**Versao**: 1.0.1 | **Licenca**: MIT | **Status**: Producao

## Por que um conector customizado?

O conector generico de API do Airbyte apresentava limitacoes criticas com a API Hubble:

| Problema | Impacto | Solucao |
|----------|---------|---------|
| Null bytes (`\u0000`) | JSON corrompido, falha no parse | Limpeza automatica antes do parse |
| Paginacao por offset | Registros perdidos ou duplicados | Paginacao por cursor (`_id`) |
| Full sync obrigatorio | Syncs lentos e custosos | Sync incremental via `updatedAt` |
| Endpoints fixos | Rigidez, codigo duplicado | Streams dinamicos via config |
| Falhas intermitentes | Syncs incompletos | Retry com backoff exponencial |

## Features

- Limpeza automatica de null bytes
- Paginacao por cursor (evita perda de dados)
- Sync incremental via campo `updatedAt`
- Streams dinamicos configuraveis
- Retry automatico com backoff exponencial
- Rate limiting respeitando header `Retry-After`
- Schema discovery dinamico
- Validacao de seguranca (HTTPS obrigatorio)
- Testes unitarios com pytest

## Instalacao

### Pre-requisitos

- Docker
- Airbyte (local, Docker ou Kubernetes)
- Token JWT da API Hubble

### Build da Imagem Docker

```bash
cd /home/cazouvilela/projetos/conector_airbyte_hubble
docker build -t airbyte/source-hubble:1.0.0 .
```

### Deploy no Kubernetes (Kind)

```bash
kind load docker-image airbyte/source-hubble:1.0.0 --name airbyte
```

### Registrar no Airbyte

1. Acesse **Settings > Sources** no Airbyte
2. Clique em **New Connector**
3. Preencha:
   - **Name**: `Source Hubble`
   - **Docker Repository**: `airbyte/source-hubble`
   - **Docker Tag**: `1.0.0`
   - **Documentation URL**: `https://docs.grupohub.com`

## Configuracao

### Parametros

| Campo | Tipo | Obrigatorio | Padrao | Descricao |
|-------|------|-------------|--------|-----------|
| `api_token` | string | Sim | - | Token JWT para autenticacao |
| `start_date` | string | Nao | - | Data inicial para sync incremental (ISO 8601) |
| `page_size` | integer | Nao | 200 | Registros por pagina (1-1000). Reduza para APIs lentas. |
| `inter_page_delay` | number | Nao | 0.5 | Delay em segundos entre paginas (0-30). Aumente para APIs com rate limit. |
| `request_timeout` | integer | Nao | 60 | Timeout em segundos (10-300) |
| `max_retries` | integer | Nao | 5 | Tentativas em caso de erro (1-10) |
| `endpoints` | array | Sim | - | Lista de endpoints para extrair |

### Estrutura de Endpoint

Cada endpoint define um stream no Airbyte:

```yaml
endpoints:
  - name: vacancies                                           # Nome do stream
    endpoint_url: https://hub.data2apis.com/dataset/all-hub-vacancies  # URL completa
```

**Regras para nome do stream:**
- Apenas letras minusculas, numeros e underscore
- Deve comecar com letra
- Exemplos validos: `vacancies`, `candidates`, `my_stream_123`

### Endpoints Padrao

O conector vem pre-configurado com:

| Stream | URL | Descricao |
|--------|-----|-----------|
| `vacancies` | hub.data2apis.com/dataset/all-hub-vacancies | Vagas de emprego |
| `candidates` | hub.data2apis.com/dataset/all-hub-candidates | Candidatos |
| `projetos` | hub.data2apis.com/dataset/all-hub-projetos | Projetos |
| `companies` | hub.data2apis.com/dataset/all-hub-companies | Empresas |

## Uso

### Arquivo de Configuracao

Crie `/tmp/config.json`:

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
    },
    {
      "name": "candidates",
      "endpoint_url": "https://hub.data2apis.com/dataset/all-hub-candidates"
    }
  ]
}
```

### Comandos Docker

```bash
# Ver especificacao do conector
docker run --rm airbyte/source-hubble:1.0.0 spec

# Verificar conexao com a API
docker run --rm -v /tmp:/tmp airbyte/source-hubble:1.0.0 \
  check --config /tmp/config.json

# Descobrir schemas disponiveis
docker run --rm -v /tmp:/tmp airbyte/source-hubble:1.0.0 \
  discover --config /tmp/config.json

# Executar sync (requer catalog.json)
docker run --rm -v /tmp:/tmp airbyte/source-hubble:1.0.0 \
  read --config /tmp/config.json --catalog /tmp/catalog.json
```

### No Airbyte UI

1. Crie uma nova **Source** do tipo "Source Hubble"
2. Preencha o **Token JWT**
3. Configure os **endpoints** desejados
4. Teste a conexao
5. Crie uma **Connection** com o destino (PostgreSQL, BigQuery, etc)
6. Execute o sync

## Arquitetura

### Fluxo de Dados

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Airbyte UI    │────▶│  SourceHubble   │────▶│   API Hubble    │
└─────────────────┘     └────────┬────────┘     └────────┬────────┘
                                 │                       │
                                 ▼                       ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │  HubbleStream   │◀────│   JSON + Nulls  │
                        └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
             ┌──────────┐ ┌──────────┐ ┌──────────┐
             │  Limpa   │ │ Pagina   │ │  Infere  │
             │  Nulls   │ │ Cursor   │ │  Schema  │
             └──────────┘ └──────────┘ └──────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │    Destino      │
                        │ (PG, BQ, S3...) │
                        └─────────────────┘
```

### Paginacao por Cursor

Em vez de offset (`$skip`), que perde registros quando dados sao inseridos durante a paginacao:

```
Pagina 1: sem filtro _id  -> ids 1-500,     ultimo = "500"
Pagina 2: _id > "500"     -> ids 501-1000,  ultimo = "1000"
Pagina 3: _id > "1000"    -> ids 1001-1300, FIM (< 500 registros)
```

### Sync Incremental

```
Execucao 1 (Full):
  - Extrai todos registros com updatedAt >= start_date
  - Salva state = {"updatedAt": "maior_data_encontrada"}

Execucao 2+ (Incremental):
  - Filtra: updatedAt >= state.updatedAt
  - Extrai apenas registros modificados
  - Atualiza state
```

## Estrutura do Projeto

```
conector_airbyte_hubble/
├── source_hubble/
│   ├── __init__.py      # Exporta SourceHubble
│   ├── source.py        # Codigo principal (HubbleStream + SourceHubble)
│   └── spec.yaml        # Especificacao UI do Airbyte
├── tests/
│   ├── __init__.py
│   ├── conftest.py      # Fixtures pytest
│   └── test_source.py   # Testes unitarios (37 testes)
├── main.py              # Entry point
├── setup.py             # Configuracao do pacote
├── Dockerfile           # Build Docker
├── metadata.yaml        # Metadados Airbyte
├── pytest.ini           # Configuracao pytest
└── README.md            # Esta documentacao
```

## Testes

### Executar Testes

```bash
cd /home/cazouvilela/projetos/conector_airbyte_hubble

# Instalar dependencias de teste
pip install -e ".[tests]"

# Executar todos os testes
pytest

# Com cobertura
pytest --cov=source_hubble --cov-report=html

# Teste especifico
pytest tests/test_source.py::TestHubbleStream -v
```

### Estrutura de Testes

| Classe | Testes | Descricao |
|--------|--------|-----------|
| TestValidateUrl | 5 | Validacao de URLs |
| TestValidateStreamName | 5 | Validacao de nomes de stream |
| TestHubbleStream | 17 | Funcionalidades do stream |
| TestSourceHubble | 8 | Source principal |
| TestSchemaDiscovery | 2 | Descoberta de schema |

## Troubleshooting

### Erro: JSON Parse Error

**Causa**: Null bytes no response da API

**Solucao**: Automatica. Verifique os logs:
```
Stream 'vacancies': X null bytes removidos
```

### Erro: 401 Unauthorized

**Causa**: Token JWT invalido ou expirado

**Solucao**: Gere um novo token na plataforma Hubble

### Erro: Connection Timeout

**Causa**: API lenta ou indisponivel

**Solucao**:
1. Verifique o status da API
2. Aumente `request_timeout` (max 300 segundos)

### Erro: 429 Rate Limit

**Causa**: Muitas requisicoes

**Solucao**: Automatica - conector aguarda e faz retry

### Erro: HTTPS Required

**Causa**: URL usando HTTP

**Solucao**: Use apenas URLs com HTTPS

### Erro: Invalid Stream Name

**Causa**: Nome com caracteres invalidos

**Solucao**: Use apenas letras minusculas, numeros e underscore

### Registros Duplicados/Faltando

**Causa** (outros conectores): Paginacao por offset

**Solucao**: Este conector usa cursor por `_id`, evitando o problema

## Desenvolvimento

### Instalacao Local

```bash
# Clone o repositorio
git clone https://github.com/CazouVilela/conector_airbyte_hubble.git
cd conector_airbyte_hubble

# Crie um virtualenv
python -m venv venv
source venv/bin/activate

# Instale em modo desenvolvimento
pip install -e ".[tests]"

# Execute os testes
pytest -v
```

### Executar Localmente (sem Docker)

```bash
# Entry point direto
python main.py spec
python main.py check --config /tmp/config.json
python main.py discover --config /tmp/config.json
```

## Dependencias

### Producao
- airbyte-cdk >= 7.0.0, < 8.0.0
- requests >= 2.28.0

### Desenvolvimento
- pytest >= 7.0.0
- pytest-cov >= 4.0.0
- pytest-mock >= 3.10.0
- requests-mock >= 1.11.0

## Changelog

### v1.0.1 (2026-01-14)
- Delay configuravel entre paginas (inter_page_delay)
- Page size padrao reduzido de 500 para 200
- Logging melhorado com checkpoints de retomada
- Informacoes de pagina e registros nas mensagens de retry

### v1.0.0 (2026-01-14)
- Limpeza de null bytes
- Paginacao por cursor
- Sync incremental
- Streams dinamicos
- Retry com backoff
- Rate limiting
- Schema discovery
- Validacao HTTPS
- Testes unitarios

### v0.1.0
- Versao inicial

## Documentacao Adicional

- [Documentacao Tecnica](.claude/memory.md) - Detalhes de implementacao para desenvolvedores

## Autor

**Cazou Vilela**
- Email: cazou@hubtalent.com.br
- GitHub: [@CazouVilela](https://github.com/CazouVilela)

## Licenca

MIT License - Veja [LICENSE](LICENSE) para detalhes.

## Referencias

- [Airbyte CDK Python](https://docs.airbyte.com/platform/connector-development/cdk-python)
- [Airbyte CDK GitHub](https://github.com/airbytehq/airbyte-python-cdk)
- [Airbyte CDK PyPI](https://pypi.org/project/airbyte-cdk/)
- [API Hubble](https://hub.data2apis.com)
