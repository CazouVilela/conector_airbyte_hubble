# Source Hubble - Conector Customizado Airbyte

Conector customizado para Airbyte que extrai dados da API Hubble (data2apis.com).

## Por que um conector customizado?

O conector generico de API do Airbyte nao conseguia lidar com:

| Problema | Solucao Implementada |
|----------|---------------------|
| Null bytes (`\u0000`) corrompendo JSON | Limpeza automatica antes do parse |
| Perda de registros com `$skip` (offset) | Paginacao por cursor (`_id`) |
| Sync full a cada execucao | Sync incremental via `updatedAt` |
| Codigo para cada endpoint | Streams dinamicos via config |

## Instalacao

### Pre-requisitos

- Docker
- Airbyte (local ou Kubernetes)
- Token JWT da API Hubble

### Build da Imagem

```bash
cd /home/cazouvilela/projetos/conector_airbyte_hubble
docker build -t airbyte/source-hubble:0.1.0 .
```

### Deploy no Kubernetes (Kind)

```bash
kind load docker-image airbyte/source-hubble:0.1.0 --name airbyte
```

### Registrar no Airbyte

1. Acesse Settings > Sources no Airbyte
2. Clique em "New Connector"
3. Preencha:
   - Name: `Source Hubble`
   - Docker Repository: `airbyte/source-hubble`
   - Docker Tag: `0.1.0`
   - Documentation URL: `https://docs.grupohub.com`

## Configuracao

### Parametros

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `api_token` | string | Sim | Token JWT para autenticacao na API |
| `start_date` | string | Nao | Data inicial para sync incremental (formato ISO) |
| `endpoints` | array | Sim | Lista de endpoints para extrair |

### Estrutura de Endpoint

Cada endpoint define um stream no Airbyte:

```yaml
name: vacancies                                      # Nome do stream
endpoint_url: https://hub.data2apis.com/dataset/... # URL completa
```

### Endpoints Padrao

O conector vem pre-configurado com:

- **vacancies** - Vagas de emprego
- **candidates** - Candidatos
- **projetos** - Projetos
- **companies** - Empresas

## Uso

### Testes Locais

Crie um arquivo `/tmp/config.json`:

```json
{
  "api_token": "seu_token_jwt_aqui",
  "start_date": "2024-01-01T00:00:00.000Z",
  "endpoints": [
    {
      "name": "vacancies",
      "endpoint_url": "https://hub.data2apis.com/dataset/all-hub-vacancies"
    }
  ]
}
```

Execute os comandos:

```bash
# Ver especificacao do conector
docker run --rm airbyte/source-hubble:0.1.0 spec

# Verificar conexao com a API
docker run --rm -v /tmp:/tmp airbyte/source-hubble:0.1.0 check --config /tmp/config.json

# Descobrir schemas disponiveis
docker run --rm -v /tmp:/tmp airbyte/source-hubble:0.1.0 discover --config /tmp/config.json
```

### No Airbyte UI

1. Crie uma nova Source do tipo "Source Hubble"
2. Preencha o token JWT
3. Configure os endpoints desejados
4. Crie uma Connection com o destino desejado
5. Execute o sync

## Arquitetura

### Fluxo de Dados

```
API Hubble → Source Hubble → Airbyte → Destino (PostgreSQL, BigQuery, etc)
     |              |
     |              ├── Limpa null bytes
     |              ├── Pagina por cursor (_id)
     |              └── Filtra por updatedAt (incremental)
     |
     └── POST com body JSON:
         {
           "$method": "find",
           "params": {"query": {...}}
         }
```

### Paginacao por Cursor

Em vez de usar `$skip` (offset), que pode perder registros quando dados sao inseridos durante a paginacao:

```
Pagina 1: _id > null          → retorna ids 1-500
Pagina 2: _id > 500           → retorna ids 501-1000
Pagina 3: _id > 1000          → retorna ids 1001-1500
...
```

### Sync Incremental

1. Primeira execucao: extrai todos os registros
2. Salva maior `updatedAt` no state do Airbyte
3. Proxima execucao: filtra `updatedAt >= state.updatedAt`
4. Atualiza state com novo maior `updatedAt`

## Estrutura do Projeto

```
conector_airbyte_hubble/
├── source_hubble/
│   ├── __init__.py      # Exporta SourceHubble
│   ├── source.py        # Codigo principal
│   └── spec.yaml        # Especificacao UI
├── main.py              # Entry point
├── setup.py             # Configuracao pacote Python
├── Dockerfile           # Build Docker
└── README.md            # Esta documentacao
```

## Classes Principais

### HubbleStream

Stream HTTP customizado que:
- Faz requests POST com body JSON
- Limpa null bytes do response
- Implementa paginacao por cursor
- Atualiza cursor_field para sync incremental

### SourceHubble

Source do Airbyte que:
- Verifica conexao com a API
- Cria streams dinamicamente a partir da config
- Implementa autenticacao Bearer Token

## Troubleshooting

### Erro: JSON Parse Error

A API retornou dados com null bytes. O conector deveria limpar automaticamente, mas se persistir:

```python
# Em source.py, metodo _clean_null_bytes
text = re.sub(r'\\u0000', '', text)
text = text.replace('\x00', '')
```

### Erro: 401 Unauthorized

Token JWT invalido ou expirado. Gere um novo token na plataforma Hubble.

### Erro: Connection Timeout

A API esta lenta. Aumente o timeout em `check_connection()` (atualmente 30s).

### Registros Faltando

Se usando outro conector com `$skip`, troque para este que usa cursor por `_id`.

## Melhorias Futuras

- [ ] Testes unitarios com pytest
- [ ] Rate limiting configuravel
- [ ] Filtros customizados por stream
- [ ] Metricas de sync
- [ ] Retry com backoff exponencial
- [ ] Schema discovery dinamico
- [ ] Validacao de URL de endpoint
- [ ] Logging estruturado JSON

## Documentacao Adicional

- [`/.claude/memory.md`](.claude/memory.md) - Memoria do projeto para Claude Code
- [`/documentacao/`](documentacao/) - Documentacao detalhada

## Autor

Cazou Vilela - cazou@hubtalent.com.br

## Licenca

Proprietario - Hub Talent
