"""
Source Hubble - Conector customizado Airbyte para API data2apis.com

Este conector resolve problemas que o conector generico de API nao consegue:
1. Limpeza de null bytes (\u0000) que corrompem JSON
2. Paginacao por cursor (_id) em vez de $skip (offset)
3. Sync incremental via campo updatedAt
4. Streams dinamicos configuraveis via UI do Airbyte

Autor: Cazou Vilela (cazou@hubtalent.com.br)
Versao: 0.1.0
"""

from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple
from urllib.parse import urlparse
import requests
import json
import re
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream
from airbyte_cdk.sources.streams.http.requests_native_auth import TokenAuthenticator


class HubbleStream(HttpStream):
    """
    Stream HTTP customizado para API Hubble.

    Caracteristicas:
    - Usa POST com body JSON (padrao da API Hubble)
    - Limpa null bytes automaticamente do response
    - Pagina por cursor (_id) para evitar perda de registros
    - Suporta sync incremental via updatedAt

    A paginacao por cursor e importante porque o $skip (offset) pode
    perder registros quando novos dados sao inseridos durante a paginacao.
    """

    # Configuracao do HTTP
    http_method = "POST"
    primary_key = "_id"
    cursor_field = "updatedAt"  # Campo usado para sync incremental
    page_size = 500  # Registros por pagina

    # Schema JSON flexivel - aceita qualquer campo adicional
    # Isso e necessario porque cada endpoint pode ter campos diferentes
    _schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "_id": {"type": ["null", "string"]},
            "updatedAt": {"type": ["null", "string"]},
            "createdAt": {"type": ["null", "string"]}
        },
        "additionalProperties": True  # Permite campos nao definidos
    }

    def __init__(
        self,
        authenticator: TokenAuthenticator,
        config: Mapping[str, Any],
        stream_name: str,
        endpoint_url: str,
        **kwargs
    ):
        """
        Inicializa o stream com URL completa do endpoint.

        Args:
            authenticator: Autenticador Bearer Token
            config: Configuracao do conector (api_token, start_date, etc)
            stream_name: Nome do stream (ex: vacancies, candidates)
            endpoint_url: URL completa do endpoint da API
        """
        # IMPORTANTE: Definir atributos ANTES de chamar super().__init__
        # O Airbyte CDK acessa alguns atributos durante a inicializacao
        self._stream_name = stream_name
        self._endpoint_url = endpoint_url

        # Extrair base_url e path da URL completa
        # Ex: "https://hub.data2apis.com/dataset/all-hub-vacancies"
        #     base_url = "https://hub.data2apis.com/"
        #     path = "dataset/all-hub-vacancies"
        parsed = urlparse(endpoint_url)
        self._url_base = f"{parsed.scheme}://{parsed.netloc}/"
        self._path = parsed.path.lstrip("/")

        self.config = config

        # Inicializa cursor para sync incremental
        # Usa start_date da config ou data padrao
        self._cursor_value = config.get("start_date", "2020-01-01T00:00:00.000Z")
        self._last_id = None  # Ultimo _id processado (para paginacao)

        super().__init__(authenticator=authenticator, **kwargs)

    @property
    def url_base(self) -> str:
        """URL base do endpoint (ex: https://hub.data2apis.com/)"""
        return self._url_base

    @property
    def name(self) -> str:
        """Nome do stream (aparece no Airbyte UI)"""
        return self._stream_name

    def path(self, **kwargs) -> str:
        """Path do endpoint (ex: dataset/all-hub-vacancies)"""
        return self._path

    def get_json_schema(self) -> Mapping[str, Any]:
        """Retorna schema JSON do stream"""
        return self._schema

    @property
    def state(self) -> MutableMapping[str, Any]:
        """
        Estado atual do stream para sync incremental.
        O Airbyte salva isso entre execucoes.
        """
        return {self.cursor_field: self._cursor_value}

    @state.setter
    def state(self, value: MutableMapping[str, Any]):
        """Restaura estado de execucao anterior"""
        self._cursor_value = value.get(self.cursor_field, "2020-01-01T00:00:00.000Z")

    def _clean_null_bytes(self, text: str) -> str:
        """
        Remove null bytes do texto que corrompem o JSON.

        A API Hubble as vezes retorna dados com \u0000 (null byte) que
        causam erro no json.loads(). Esta funcao limpa esses caracteres.

        Args:
            text: Texto do response HTTP

        Returns:
            Texto sem null bytes
        """
        # Remove representacao unicode do null byte
        text = re.sub(r'\\u0000', '', text)
        # Remove null byte literal
        text = text.replace('\x00', '')
        return text

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        """
        Processa response da API e extrai registros.

        Limpa null bytes, faz parse do JSON, atualiza cursor
        e retorna registros um a um (generator).
        """
        # Limpa null bytes antes do parse
        clean_text = self._clean_null_bytes(response.text)

        try:
            data = json.loads(clean_text)
        except json.JSONDecodeError as e:
            self.logger.error(f"Erro ao fazer parse do JSON: {e}")
            return

        # A API retorna dados no campo "data"
        records = data.get("data", [])

        for record in records:
            # Atualiza cursor com maior updatedAt encontrado
            record_cursor = record.get(self.cursor_field)
            if record_cursor and record_cursor > self._cursor_value:
                self._cursor_value = record_cursor

            # Guarda ultimo _id para paginacao
            self._last_id = record.get("_id")
            yield record

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """
        Determina se ha mais paginas e retorna token para proxima.

        Usa paginacao por cursor (_id) em vez de $skip (offset).
        Isso evita perda de registros quando dados sao inseridos
        durante a paginacao.

        Returns:
            Dict com last_id se ha mais paginas, None se terminou
        """
        clean_text = self._clean_null_bytes(response.text)

        try:
            data = json.loads(clean_text)
        except json.JSONDecodeError:
            return None

        records = data.get("data", [])

        # Se retornou menos que page_size, nao ha mais paginas
        if len(records) < self.page_size:
            return None

        # Retorna ultimo _id para usar como cursor na proxima pagina
        return {"last_id": records[-1].get("_id")}

    def request_body_json(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Optional[Mapping]:
        """
        Monta body JSON para request POST.

        A API Hubble usa formato especifico com $method e params.
        Inclui filtros para sync incremental e paginacao por cursor.
        """
        query = {
            "$limit": self.page_size,
            "$sort": {"_id": 1},  # Ordena por _id para paginacao consistente
        }

        # Filtro para sync incremental - apenas registros atualizados
        cursor = stream_state.get(self.cursor_field) if stream_state else self._cursor_value
        if cursor:
            query["updatedAt"] = {"$gte": cursor}

        # Filtro para paginacao por cursor - _id maior que ultimo da pagina anterior
        if next_page_token:
            query["_id"] = {"$gt": next_page_token["last_id"]}

        return {
            "$method": "find",
            "params": {"query": query}
        }

    def request_headers(self, **kwargs) -> Mapping[str, Any]:
        """Headers adicionais para requests"""
        return {"Content-Type": "application/json"}


class SourceHubble(AbstractSource):
    """
    Source Airbyte para API Hubble (data2apis.com).

    Permite configurar multiplos endpoints via UI do Airbyte,
    cada um se tornando um stream separado.
    """

    def check_connection(self, logger, config) -> Tuple[bool, Any]:
        """
        Verifica se a conexao com a API esta funcionando.

        Chamado quando usuario clica em "Test" na UI do Airbyte.
        Faz uma request de teste para o primeiro endpoint configurado.

        Returns:
            Tupla (sucesso: bool, mensagem_erro: str ou None)
        """
        try:
            headers = {
                "Authorization": f"Bearer {config['api_token']}",
                "Content-Type": "application/json"
            }

            endpoints = config.get("endpoints", [])
            if not endpoints:
                return False, "Nenhum endpoint configurado"

            # Testa conexao com primeiro endpoint
            test_url = endpoints[0].get("endpoint_url")

            body = {
                "$method": "find",
                "params": {"query": {"$limit": 1}}  # Apenas 1 registro para teste
            }
            response = requests.post(
                test_url,
                headers=headers,
                json=body,
                timeout=30
            )
            response.raise_for_status()
            return True, None
        except Exception as e:
            return False, str(e)

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """
        Cria lista de streams baseado nos endpoints configurados.

        Cada endpoint na config vira um stream separado no Airbyte.
        Isso permite extrair dados de multiplas colecoes em uma unica source.

        Returns:
            Lista de HubbleStream, um para cada endpoint configurado
        """
        auth = TokenAuthenticator(token=config["api_token"])

        streams = []
        for ep_config in config.get("endpoints", []):
            stream_name = ep_config.get("name")
            endpoint_url = ep_config.get("endpoint_url")

            if stream_name and endpoint_url:
                streams.append(
                    HubbleStream(
                        authenticator=auth,
                        config=config,
                        stream_name=stream_name,
                        endpoint_url=endpoint_url
                    )
                )

        return streams
