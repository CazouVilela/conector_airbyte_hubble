# Conector Airbyte Hubble - Memoria do Projeto

> **Referencia**: Este projeto segue o template documentado em [TEMPLATE_PROJETO.md](.claude/TEMPLATE_PROJETO.md)

<!-- CHAPTER: 1 Visao Geral -->

## Sobre o Projeto

Conector customizado para Airbyte que extrai dados da API Hubble (data2apis.com). Desenvolvido para resolver limitacoes do conector generico de API.

## Informacoes Principais

**Versao Atual**: v0.1.0
**Stack**: Python 3.9+, Airbyte CDK, Docker
**Status**: Producao
**Autor**: Cazou Vilela (cazou@hubtalent.com.br)

## Problemas Resolvidos

1. **Null Bytes** - API retorna `\u0000` que corrompe JSON. Conector limpa automaticamente.
2. **Paginacao** - Usa cursor por `_id` em vez de `$skip` (offset) para evitar perda de registros.
3. **Sync Incremental** - Usa campo `updatedAt` para extrair apenas registros modificados.
4. **Streams Dinamicos** - Endpoints configuraveis via UI do Airbyte.

<!-- CHAPTER: 2 Arquitetura -->

## Arquitetura

### Stack Tecnologico
- Python 3.9+
- Airbyte CDK >= 0.50.0
- Requests >= 2.28.0
- Docker (airbyte/python-connector-base:1.1.0)

### Estrutura de Arquivos
```
conector_airbyte_hubble/
├── .claude/
│   ├── memory.md                         # Este arquivo
│   ├── commands/ → symlink               # Comandos compartilhados
│   ├── settings.local.json → symlink     # Permissoes compartilhadas
│   ├── GUIA_SISTEMA_PROJETOS.md → symlink
│   └── TEMPLATE_PROJETO.md → symlink
├── source_hubble/
│   ├── __init__.py                       # Exporta SourceHubble
│   ├── source.py                         # Codigo principal (HubbleStream + SourceHubble)
│   └── spec.yaml                         # Especificacao UI do Airbyte
├── main.py                               # Entry point do conector
├── setup.py                              # Configuracao do pacote Python
├── Dockerfile                            # Build da imagem Docker
├── README.md                             # Documentacao
└── documentacao/                         # Docs detalhadas
```

### Classes Principais

**HubbleStream** (`source.py:12`)
- Herda de `HttpStream` do Airbyte CDK
- Implementa paginacao por cursor (`_id`)
- Limpa null bytes do response
- Suporta sync incremental via `updatedAt`

**SourceHubble** (`source.py:149`)
- Herda de `AbstractSource` do Airbyte CDK
- Verifica conexao com a API
- Cria streams dinamicamente baseado na config

<!-- CHAPTER: 3 Configuracao -->

## Configuracao

### Parametros (spec.yaml)

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `api_token` | string | Sim | Token JWT para autenticacao |
| `start_date` | string | Nao | Data inicial para sync incremental (ISO) |
| `endpoints` | array | Sim | Lista de endpoints para extrair |

### Estrutura de Endpoint

```yaml
endpoints:
  - name: vacancies           # Nome do stream no Airbyte
    endpoint_url: "https://hub.data2apis.com/dataset/all-hub-vacancies"
```

### Endpoints Padrao

- `vacancies` - https://hub.data2apis.com/dataset/all-hub-vacancies
- `candidates` - https://hub.data2apis.com/dataset/all-hub-candidates
- `projetos` - https://hub.data2apis.com/dataset/all-hub-projetos
- `companies` - https://hub.data2apis.com/dataset/all-hub-companies

<!-- CHAPTER: 4 Comandos -->

## Comandos Uteis

### Build e Deploy

```bash
# Build da imagem Docker
docker build -t airbyte/source-hubble:0.1.0 .

# Carregar no Kubernetes (Kind)
kind load docker-image airbyte/source-hubble:0.1.0 --name airbyte
```

### Testes Locais

```bash
# Ver especificacao do conector
docker run --rm -v /tmp:/tmp airbyte/source-hubble:0.1.0 spec

# Verificar conexao
docker run --rm -v /tmp:/tmp airbyte/source-hubble:0.1.0 check --config /tmp/config.json

# Descobrir schemas
docker run --rm -v /tmp:/tmp airbyte/source-hubble:0.1.0 discover --config /tmp/config.json

# Executar sync
docker run --rm -v /tmp:/tmp airbyte/source-hubble:0.1.0 read --config /tmp/config.json --catalog /tmp/catalog.json
```

### Exemplo de config.json

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

<!-- CHAPTER: 5 Fluxo de Dados -->

## Fluxo de Dados

### Request para API

```json
{
  "$method": "find",
  "params": {
    "query": {
      "$limit": 500,
      "$sort": {"_id": 1},
      "updatedAt": {"$gte": "2024-01-01T00:00:00.000Z"},
      "_id": {"$gt": "ultimo_id_da_pagina_anterior"}
    }
  }
}
```

### Paginacao por Cursor

1. Primeira request: sem filtro de `_id`
2. Proximas requests: `_id > ultimo_id` da pagina anterior
3. Para quando retorna menos que `page_size` (500) registros

### Sync Incremental

1. Usa `state` do Airbyte para guardar ultimo `updatedAt`
2. Proxima execucao filtra `updatedAt >= state.updatedAt`
3. Atualiza `state` com maior `updatedAt` encontrado

<!-- CHAPTER: 6 Troubleshooting -->

## Troubleshooting

### Erro: JSON Parse Error

**Causa**: Null bytes no response da API
**Solucao**: Conector ja limpa automaticamente via `_clean_null_bytes()`

### Erro: Connection Timeout

**Causa**: API lenta ou indisponivel
**Solucao**: Aumentar timeout (atualmente 30s) ou verificar status da API

### Erro: 401 Unauthorized

**Causa**: Token JWT invalido ou expirado
**Solucao**: Gerar novo token na plataforma Hubble

### Registros Duplicados

**Causa**: Usar $skip em vez de cursor por _id
**Solucao**: Conector ja usa cursor por _id para evitar isso

<!-- CHAPTER: 7 Melhorias Futuras -->

## Melhorias Futuras

- [ ] Adicionar testes unitarios
- [ ] Implementar rate limiting configuravel
- [ ] Suportar filtros customizados por stream
- [ ] Adicionar metricas de sync (registros/segundo)
- [ ] Implementar retry com backoff exponencial
- [ ] Suportar schema discovery dinamico da API
- [ ] Adicionar validacao de URL de endpoint
- [ ] Logging estruturado (JSON)

<!-- CHAPTER: 8 Referencias -->

## Referencias

- [Airbyte CDK Docs](https://docs.airbyte.com/connector-development/cdk-python)
- [API Hubble](https://hub.data2apis.com)
- [TEMPLATE_PROJETO.md](.claude/TEMPLATE_PROJETO.md) - Template de organizacao
- [GUIA_SISTEMA_PROJETOS.md](.claude/GUIA_SISTEMA_PROJETOS.md) - Guia do sistema

---

**Ultima Atualizacao**: 2026-01-14
**Versao**: 0.1.0
**Status**: Producao
