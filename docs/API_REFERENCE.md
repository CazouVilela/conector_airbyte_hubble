# Referencia da API Hubble

Este documento descreve como o conector interage com a API Hubble (data2apis.com).

## Endpoints

A API Hubble disponibiliza datasets via endpoints REST:

| Dataset | URL |
|---------|-----|
| Vacancies | https://hub.data2apis.com/dataset/all-hub-vacancies |
| Candidates | https://hub.data2apis.com/dataset/all-hub-candidates |
| Projetos | https://hub.data2apis.com/dataset/all-hub-projetos |
| Companies | https://hub.data2apis.com/dataset/all-hub-companies |

## Autenticacao

Bearer Token via header Authorization:

```http
Authorization: Bearer <token_jwt>
```

O token JWT e obtido na plataforma Hubble e tem validade limitada.

## Formato de Request

A API usa o metodo POST com body JSON seguindo o padrao MongoDB-like:

```http
POST /dataset/all-hub-vacancies HTTP/1.1
Host: hub.data2apis.com
Authorization: Bearer <token>
Content-Type: application/json

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

### Parametros da Query

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `$limit` | integer | Numero maximo de registros por pagina (max 1000) |
| `$sort` | object | Ordenacao. Ex: `{"_id": 1}` = crescente |
| `$skip` | integer | Offset (NAO USAR - causa perda de dados) |
| `updatedAt` | object | Filtro por data de atualizacao |
| `_id` | object | Filtro por ID (usado para paginacao por cursor) |

### Operadores de Filtro

| Operador | Descricao | Exemplo |
|----------|-----------|---------|
| `$gte` | Maior ou igual | `{"updatedAt": {"$gte": "2024-01-01"}}` |
| `$gt` | Maior que | `{"_id": {"$gt": "abc123"}}` |
| `$lte` | Menor ou igual | `{"updatedAt": {"$lte": "2024-12-31"}}` |
| `$lt` | Menor que | `{"_id": {"$lt": "xyz789"}}` |
| `$eq` | Igual | `{"status": {"$eq": "active"}}` |
| `$ne` | Diferente | `{"status": {"$ne": "deleted"}}` |

## Formato de Response

A API retorna JSON com a estrutura:

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
  ],
  "meta": {
    "total": 15000,
    "count": 500
  }
}
```

### Campos Comuns

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `_id` | string | Identificador unico (MongoDB ObjectId) |
| `updatedAt` | string (ISO 8601) | Data da ultima atualizacao |
| `createdAt` | string (ISO 8601) | Data de criacao |

### Campos por Dataset

**Vacancies:**
- `title`: Titulo da vaga
- `company`: Empresa
- `location`: Localizacao
- `status`: Status (open, closed, etc)
- `salary`: Informacoes de salario
- ...

**Candidates:**
- `name`: Nome do candidato
- `email`: Email
- `phone`: Telefone
- `skills`: Lista de habilidades
- `experience`: Experiencia profissional
- ...

**Projetos:**
- `name`: Nome do projeto
- `client`: Cliente
- `startDate`: Data de inicio
- `endDate`: Data de fim
- `status`: Status do projeto
- ...

**Companies:**
- `name`: Nome da empresa
- `cnpj`: CNPJ
- `industry`: Setor
- `size`: Porte
- ...

## Paginacao

### Por Cursor (RECOMENDADO)

Usar `_id > ultimo_id` para paginacao segura:

```
Pagina 1:
POST {"params": {"query": {"$limit": 500, "$sort": {"_id": 1}}}}
Response: [{_id: "1"}, ..., {_id: "500"}]

Pagina 2:
POST {"params": {"query": {"$limit": 500, "_id": {"$gt": "500"}, "$sort": {"_id": 1}}}}
Response: [{_id: "501"}, ..., {_id: "1000"}]
```

### Por Offset (NAO RECOMENDADO)

Usar `$skip` pode causar perda de dados:

```
Pagina 1:
POST {"params": {"query": {"$limit": 500, "$skip": 0}}}

[Novo registro inserido durante paginacao]

Pagina 2:
POST {"params": {"query": {"$limit": 500, "$skip": 500}}}
# Registro pode ter sido pulado ou duplicado!
```

## Codigos de Status HTTP

| Codigo | Descricao | Acao do Conector |
|--------|-----------|------------------|
| 200 | Sucesso | Processa dados |
| 400 | Bad Request | Erro - verifica payload |
| 401 | Unauthorized | Erro - token invalido |
| 403 | Forbidden | Erro - sem permissao |
| 404 | Not Found | Erro - endpoint invalido |
| 429 | Rate Limit | Retry apos Retry-After |
| 500 | Internal Error | Retry com backoff |
| 502 | Bad Gateway | Retry com backoff |
| 503 | Unavailable | Retry com backoff |
| 504 | Timeout | Retry com backoff |

## Rate Limiting

A API impoe limites de requisicoes:

- Limite: ~100 requests/minuto (varia por conta)
- Header de resposta: `Retry-After: <segundos>`

O conector automaticamente:
1. Detecta status 429
2. Le header `Retry-After`
3. Aguarda o tempo indicado
4. Faz retry

## Problemas Conhecidos

### Null Bytes

A API ocasionalmente retorna dados com caracteres `\u0000`:

```json
{"name": "Test\u0000Value"}
```

Isso corrompe o parse JSON. O conector limpa automaticamente.

### Timeout

Datasets grandes podem causar timeout na API:
- Default: 30s
- Configuravel: `request_timeout` (max 300s)

Recomendacao: usar `page_size` menor para datasets grandes.

### Caracteres Especiais

Campos texto podem conter:
- Unicode: caracteres acentuados, emojis
- Escape: `\n`, `\t`, `\\`
- HTML: `&amp;`, `&lt;`, `&gt;`

O conector preserva esses caracteres (exceto null bytes).

## Exemplos

### Buscar Todas as Vagas Abertas

```json
{
  "$method": "find",
  "params": {
    "query": {
      "$limit": 500,
      "status": {"$eq": "open"}
    }
  }
}
```

### Buscar Candidatos Atualizados Apos Data

```json
{
  "$method": "find",
  "params": {
    "query": {
      "$limit": 500,
      "$sort": {"_id": 1},
      "updatedAt": {"$gte": "2024-06-01T00:00:00.000Z"}
    }
  }
}
```

### Paginacao Completa com Cursor

```json
// Pagina 1
{
  "$method": "find",
  "params": {
    "query": {
      "$limit": 500,
      "$sort": {"_id": 1}
    }
  }
}

// Paginas 2+
{
  "$method": "find",
  "params": {
    "query": {
      "$limit": 500,
      "$sort": {"_id": 1},
      "_id": {"$gt": "<ultimo_id_da_pagina_anterior>"}
    }
  }
}
```
