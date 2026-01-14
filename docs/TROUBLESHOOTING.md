# Troubleshooting - Conector Hubble

Guia para diagnosticar e resolver problemas comuns.

## Problemas de Conexao

### Erro: 401 Unauthorized

**Mensagem:**
```
HTTPError: 401 - Unauthorized
```

**Causa:** Token JWT invalido ou expirado.

**Solucao:**
1. Verifique se o token esta correto
2. Gere um novo token na plataforma Hubble
3. Certifique-se de usar o token completo (tokens JWT sao longos)

### Erro: Connection Timeout

**Mensagem:**
```
requests.exceptions.Timeout: Connection timed out
```

**Causa:** API lenta, indisponivel ou bloqueio de rede.

**Solucao:**
1. Verifique se a API esta acessivel:
   ```bash
   curl -I https://hub.data2apis.com/dataset/all-hub-vacancies
   ```
2. Aumente o timeout na configuracao:
   ```json
   {"request_timeout": 120}
   ```
3. Verifique firewall/proxy

### Erro: Connection Refused

**Mensagem:**
```
requests.exceptions.ConnectionError: Connection refused
```

**Causa:** API indisponivel ou URL incorreta.

**Solucao:**
1. Verifique a URL do endpoint
2. Teste acesso manual:
   ```bash
   curl https://hub.data2apis.com/health
   ```
3. Verifique DNS

### Erro: SSL Certificate Verify Failed

**Mensagem:**
```
SSLError: certificate verify failed
```

**Causa:** Problema com certificado SSL.

**Solucao:**
1. Verifique data/hora do sistema
2. Atualize certificados CA
3. NAO desabilite verificacao SSL (inseguro)

## Problemas de Dados

### Erro: JSON Parse Error

**Mensagem:**
```
json.JSONDecodeError: Invalid control character at: line X column Y
```

**Causa:** Null bytes (`\u0000`) no response.

**Solucao:** Automatica - o conector limpa null bytes. Se persistir:
1. Verifique os logs para confirmar limpeza
2. Reporte ao time da API Hubble

### Registros Faltando

**Sintoma:** Quantidade de registros menor que esperada.

**Causa Provavel:** Paginacao incorreta (offset em vez de cursor).

**Verificacao:**
1. Confirme que esta usando este conector (nao o generico)
2. Verifique logs de paginacao:
   ```
   Stream 'vacancies': paginacao concluida | total_registros=X
   ```

### Registros Duplicados

**Sintoma:** Mesmos registros aparecem multiplas vezes.

**Causa Provavel:** Sync mode incorreto no Airbyte.

**Solucao:**
1. Use "Append Dedup" ou "Overwrite" no Airbyte
2. Configure primary_key como `_id`
3. Verifique cursor_field como `updatedAt`

### Schema Mismatch

**Mensagem:**
```
Schema validation error: expected X, got Y
```

**Causa:** Dados da API nao correspondem ao schema esperado.

**Solucao:**
1. Execute `discover` novamente para atualizar schema
2. Reconfigure a connection no Airbyte
3. Verifique se a API mudou o formato dos dados

### Campos Novos Nao Aparecem

**Sintoma:** Novos campos adicionados pela API nao sao sincronizados.

**Solucao:**
1. Execute `discover` para descobrir novos campos
2. Reconfigure a connection no Airbyte
3. O schema discovery dinamico deve detectar automaticamente

## Problemas de Performance

### Sync Muito Lento

**Sintoma:** Sync demora horas para poucos registros.

**Causas e Solucoes:**

1. **Page size muito pequeno:**
   ```json
   {"page_size": 500}  // Recomendado
   ```

2. **Timeout muito baixo:**
   ```json
   {"request_timeout": 60}  // Ou mais para datasets grandes
   ```

3. **API lenta:** Nada a fazer, depende do servidor

4. **Muitos retries:** Verifique logs para 429/500

### Erro: Rate Limit Exceeded (429)

**Mensagem:**
```
HTTPError: 429 - Too Many Requests
```

**Causa:** Muitas requisicoes em pouco tempo.

**Solucao:** Automatica - conector aguarda e faz retry.

Se persistir:
1. Reduza `page_size` (menos requests)
2. Agende syncs em horarios de menor uso
3. Contate suporte Hubble para aumentar limite

### Erro: Memory Error

**Mensagem:**
```
MemoryError: Unable to allocate X bytes
```

**Causa:** Registros muito grandes ou muitos registros em memoria.

**Solucao:**
1. Reduza `page_size`:
   ```json
   {"page_size": 100}
   ```
2. Aumente memoria do container Docker
3. Use instancia com mais RAM

## Problemas de Configuracao

### Erro: HTTPS Required

**Mensagem:**
```
HubbleConfigError: URL deve usar HTTPS
```

**Causa:** URL configurada com HTTP em vez de HTTPS.

**Solucao:**
```json
// Errado
{"endpoint_url": "http://hub.data2apis.com/..."}

// Correto
{"endpoint_url": "https://hub.data2apis.com/..."}
```

### Erro: Invalid Stream Name

**Mensagem:**
```
HubbleConfigError: Nome do stream invalido: 'My-Stream'
```

**Causa:** Nome do stream com caracteres invalidos.

**Regras:**
- Apenas letras minusculas
- Numeros permitidos (exceto no inicio)
- Underscore permitido
- Sem hifens, espacos ou maiusculas

**Solucao:**
```json
// Errado
{"name": "My-Stream"}
{"name": "myStream"}
{"name": "123stream"}

// Correto
{"name": "my_stream"}
{"name": "mystream"}
{"name": "stream123"}
```

### Erro: No Endpoints Configured

**Mensagem:**
```
Nenhum endpoint configurado
```

**Causa:** Array de endpoints vazio.

**Solucao:**
```json
{
  "endpoints": [
    {
      "name": "vacancies",
      "endpoint_url": "https://hub.data2apis.com/dataset/all-hub-vacancies"
    }
  ]
}
```

### Erro: API Token Not Configured

**Mensagem:**
```
API Token nao configurado
```

**Causa:** Campo `api_token` vazio ou ausente.

**Solucao:**
```json
{
  "api_token": "seu_token_jwt_aqui"
}
```

## Logs e Debug

### Habilitar Logs Verbose

No Docker:
```bash
docker run --rm \
  -e LOG_LEVEL=DEBUG \
  -v /tmp:/tmp \
  airbyte/source-hubble:1.0.0 \
  read --config /tmp/config.json --catalog /tmp/catalog.json
```

### Logs Importantes

**Inicializacao:**
```
Inicializando stream 'vacancies' | endpoint=... | page_size=500
```

**Progresso:**
```
Stream 'vacancies': 5000 registros lidos | 10 paginas
```

**Conclusao:**
```
Stream 'vacancies': paginacao concluida | total_registros=15000
```

**Avisos:**
```
Stream 'vacancies': 5 null bytes removidos
Stream 'vacancies': retry necessario | status=429
```

### Verificar Saude da Conexao

```bash
# Testar conexao
docker run --rm -v /tmp:/tmp airbyte/source-hubble:1.0.0 \
  check --config /tmp/config.json

# Output esperado:
# {"type": "CONNECTION_STATUS", "connectionStatus": {"status": "SUCCEEDED"}}
```

## Contato e Suporte

Se o problema persistir:

1. **Colete informacoes:**
   - Versao do conector
   - Configuracao (sem token)
   - Logs de erro completos
   - Passos para reproduzir

2. **Abra issue no GitHub:**
   https://github.com/CazouVilela/conector_airbyte_hubble/issues

3. **Contato:**
   - Email: cazou@hubtalent.com.br
