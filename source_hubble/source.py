"""
Source Hubble - Conector customizado Airbyte para API data2apis.com

Versao 1.0.0 - Features:
1. Limpeza de null bytes (\u0000) que corrompem JSON
2. Paginacao por cursor (_id) em vez de $skip (offset)
3. Sync incremental via campo updatedAt
4. Streams dinamicos configuraveis via UI do Airbyte
5. Retry com backoff exponencial
6. Rate limiting configuravel
7. Schema discovery dinamico
8. Logging estruturado
9. Validacao de URLs

Autor: Cazou Vilela (cazou@hubtalent.com.br)
Versao: 1.0.0
"""

import json
import logging
import re
import time
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple
from urllib.parse import urlparse

import backoff
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream
from airbyte_cdk.sources.streams.http.requests_native_auth import TokenAuthenticator


# Configuracao de logging estruturado
logger = logging.getLogger("airbyte.source-hubble")


class HubbleConfigError(Exception):
    """Erro de configuracao do conector Hubble."""
    pass


class HubbleAPIError(Exception):
    """Erro na comunicacao com a API Hubble."""
    pass


def validate_url(url: str, field_name: str = "URL") -> None:
    """
    Valida se uma URL e valida e segura (HTTPS).

    Args:
        url: URL para validar
        field_name: Nome do campo para mensagem de erro

    Raises:
        HubbleConfigError: Se a URL for invalida
    """
    if not url:
        raise HubbleConfigError(f"{field_name} nao pode ser vazio")

    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise HubbleConfigError(
            f"{field_name} deve usar HTTPS. Recebido: {parsed.scheme}://"
        )

    if not parsed.netloc:
        raise HubbleConfigError(f"{field_name} invalida: dominio nao encontrado")

    # Valida que nao tem caracteres perigosos
    dangerous_chars = ["<", ">", '"', "'", "{", "}", "|", "\\", "^", "`"]
    for char in dangerous_chars:
        if char in url:
            raise HubbleConfigError(
                f"{field_name} contem caractere invalido: {char}"
            )


def validate_stream_name(name: str) -> None:
    """
    Valida nome do stream (apenas letras minusculas, numeros e underscore).

    Args:
        name: Nome do stream

    Raises:
        HubbleConfigError: Se o nome for invalido
    """
    if not name:
        raise HubbleConfigError("Nome do stream nao pode ser vazio")

    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        raise HubbleConfigError(
            f"Nome do stream invalido: '{name}'. "
            "Use apenas letras minusculas, numeros e underscore, "
            "comecando com letra."
        )


class HubbleStream(HttpStream):
    """
    Stream HTTP customizado para API Hubble.

    Features:
    - POST com body JSON (padrao da API Hubble)
    - Limpeza automatica de null bytes
    - Paginacao por cursor (_id)
    - Sync incremental via updatedAt
    - Retry com backoff exponencial
    - Logging estruturado
    """

    http_method = "POST"
    primary_key = "_id"
    cursor_field = "updatedAt"

    # Configuracao de retry (usado pelo CDK)
    max_retries = 5
    retry_factor = 2

    # Schema base - sera enriquecido dinamicamente
    _base_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "_id": {"type": ["null", "string"]},
            "updatedAt": {"type": ["null", "string"]},
            "createdAt": {"type": ["null", "string"]}
        },
        "additionalProperties": True
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
        Inicializa o stream com configuracoes.

        Args:
            authenticator: Autenticador Bearer Token
            config: Configuracao do conector
            stream_name: Nome do stream
            endpoint_url: URL completa do endpoint
        """
        # Validacao de inputs
        validate_stream_name(stream_name)
        validate_url(endpoint_url, f"Endpoint URL para stream '{stream_name}'")

        self._stream_name = stream_name
        self._endpoint_url = endpoint_url

        # Parse da URL
        parsed = urlparse(endpoint_url)
        self._url_base = f"{parsed.scheme}://{parsed.netloc}/"
        self._path = parsed.path.lstrip("/")

        # Configuracoes do conector
        self.config = config
        self.page_size = config.get("page_size", 200)
        self.request_timeout = config.get("request_timeout", 60)
        self.max_retries = config.get("max_retries", 5)
        self.inter_page_delay = config.get("inter_page_delay", 0.5)

        # Estado do cursor
        self._cursor_value = config.get("start_date", "2020-01-01T00:00:00.000Z")
        self._last_id = None

        # Schema dinamico (sera populado no primeiro request)
        self._discovered_schema = None
        self._schema_discovered = False

        # Contadores para logging
        self._records_read = 0
        self._pages_read = 0

        logger.info(
            f"Inicializando stream '{stream_name}' | "
            f"endpoint={endpoint_url} | "
            f"page_size={self.page_size} | "
            f"timeout={self.request_timeout}s | "
            f"delay={self.inter_page_delay}s"
        )

        super().__init__(authenticator=authenticator, **kwargs)

    @property
    def url_base(self) -> str:
        return self._url_base

    @property
    def name(self) -> str:
        return self._stream_name

    def path(self, **kwargs) -> str:
        return self._path

    def get_json_schema(self) -> Mapping[str, Any]:
        """Retorna schema JSON, enriquecido dinamicamente se disponivel."""
        if self._discovered_schema:
            return self._discovered_schema
        return self._base_schema

    @property
    def state(self) -> MutableMapping[str, Any]:
        return {self.cursor_field: self._cursor_value}

    @state.setter
    def state(self, value: MutableMapping[str, Any]):
        self._cursor_value = value.get(self.cursor_field, "2020-01-01T00:00:00.000Z")
        logger.debug(f"Stream '{self.name}' state restaurado: {self._cursor_value}")

    def _clean_null_bytes(self, text: str) -> str:
        """Remove null bytes que corrompem JSON."""
        original_len = len(text)
        text = re.sub(r'\\u0000', '', text)
        text = text.replace('\x00', '')

        cleaned_len = len(text)
        if cleaned_len != original_len:
            logger.warning(
                f"Stream '{self.name}': {original_len - cleaned_len} null bytes removidos"
            )

        return text

    def _infer_json_type(self, value: Any) -> dict:
        """Infere tipo JSON Schema a partir de um valor Python."""
        if value is None:
            return {"type": "null"}
        elif isinstance(value, bool):
            return {"type": ["null", "boolean"]}
        elif isinstance(value, int):
            return {"type": ["null", "integer"]}
        elif isinstance(value, float):
            return {"type": ["null", "number"]}
        elif isinstance(value, str):
            # Detecta datas ISO
            if re.match(r'^\d{4}-\d{2}-\d{2}', value):
                return {"type": ["null", "string"], "format": "date-time"}
            return {"type": ["null", "string"]}
        elif isinstance(value, list):
            return {"type": ["null", "array"], "items": {}}
        elif isinstance(value, dict):
            return {"type": ["null", "object"], "additionalProperties": True}
        else:
            return {"type": ["null", "string"]}

    def _discover_schema_from_record(self, record: Mapping[str, Any]) -> None:
        """
        Descobre schema dinamicamente a partir do primeiro registro.

        Args:
            record: Primeiro registro retornado pela API
        """
        if self._schema_discovered:
            return

        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }

        for key, value in record.items():
            schema["properties"][key] = self._infer_json_type(value)

        self._discovered_schema = schema
        self._schema_discovered = True

        logger.info(
            f"Stream '{self.name}': schema descoberto com {len(record)} campos"
        )

    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, json.JSONDecodeError),
        max_tries=5,
        factor=2,
        logger=logger
    )
    def _parse_response_with_retry(self, response: requests.Response) -> dict:
        """Parse response com retry em caso de erro."""
        clean_text = self._clean_null_bytes(response.text)
        return json.loads(clean_text)

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        """Processa response da API e extrai registros."""
        try:
            data = self._parse_response_with_retry(response)
        except json.JSONDecodeError as e:
            logger.error(
                f"Stream '{self.name}': erro ao fazer parse do JSON | "
                f"status={response.status_code} | error={e}"
            )
            return

        records = data.get("data", [])
        self._pages_read += 1

        # Descoberta de schema no primeiro registro
        if records and not self._schema_discovered:
            self._discover_schema_from_record(records[0])

        for record in records:
            # Atualiza cursor
            record_cursor = record.get(self.cursor_field)
            if record_cursor and record_cursor > self._cursor_value:
                self._cursor_value = record_cursor

            self._last_id = record.get("_id")
            self._records_read += 1
            yield record

        # Log periodico de progresso
        if self._pages_read % 10 == 0:
            logger.info(
                f"Stream '{self.name}': {self._records_read} registros lidos | "
                f"{self._pages_read} paginas | cursor={self._cursor_value}"
            )

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """Determina se ha mais paginas usando cursor por _id."""
        try:
            data = self._parse_response_with_retry(response)
        except json.JSONDecodeError:
            return None

        records = data.get("data", [])

        if len(records) < self.page_size:
            logger.info(
                f"Stream '{self.name}': paginacao concluida | "
                f"total_registros={self._records_read} | "
                f"total_paginas={self._pages_read}"
            )
            return None

        last_id = records[-1].get("_id")

        # Delay entre paginas para nao sobrecarregar a API
        if self.inter_page_delay > 0:
            logger.debug(
                f"Stream '{self.name}': aguardando {self.inter_page_delay}s antes da proxima pagina"
            )
            time.sleep(self.inter_page_delay)

        # Log de checkpoint para facilitar retomada em caso de falha
        logger.info(
            f"Stream '{self.name}': checkpoint | "
            f"pagina={self._pages_read} | "
            f"registros={self._records_read} | "
            f"last_id={last_id} | "
            f"cursor={self._cursor_value}"
        )

        return {"last_id": last_id}

    def request_body_json(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Optional[Mapping]:
        """Monta body JSON para request POST."""
        query = {
            "$limit": self.page_size,
            "$sort": {"_id": 1},
        }

        # Filtro incremental
        cursor = stream_state.get(self.cursor_field) if stream_state else self._cursor_value
        if cursor:
            query["updatedAt"] = {"$gte": cursor}

        # Paginacao por cursor
        if next_page_token:
            query["_id"] = {"$gt": next_page_token["last_id"]}

        return {
            "$method": "find",
            "params": {"query": query}
        }

    def request_headers(self, **kwargs) -> Mapping[str, Any]:
        return {"Content-Type": "application/json"}

    def request_kwargs(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Mapping[str, Any]:
        """Configura timeout para requests."""
        return {"timeout": self.request_timeout}

    def should_retry(self, response: requests.Response) -> bool:
        """Determina se deve fazer retry baseado no status code."""
        # Retry em 429 (rate limit), 500, 502, 503, 504
        retry_codes = {429, 500, 502, 503, 504}
        should = response.status_code in retry_codes

        if should:
            logger.warning(
                f"Stream '{self.name}': retry necessario | "
                f"status={response.status_code} | "
                f"pagina={self._pages_read} | "
                f"registros={self._records_read} | "
                f"last_id={self._last_id}"
            )

        return should

    def backoff_time(self, response: requests.Response) -> Optional[float]:
        """Calcula tempo de backoff para retry."""
        if response.status_code == 429:
            # Respeita header Retry-After se presente
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                return float(retry_after)
            return 60.0  # Default 60s para rate limit

        # Backoff exponencial para outros erros
        return None  # Usa default do CDK


class SourceHubble(AbstractSource):
    """
    Source Airbyte para API Hubble (data2apis.com).

    Features:
    - Multiplos endpoints configuraveis via UI
    - Validacao robusta de configuracao
    - Logging estruturado
    """

    def check_connection(self, logger, config) -> Tuple[bool, Any]:
        """Verifica conexao com a API."""
        try:
            # Valida configuracao
            endpoints = config.get("endpoints", [])
            if not endpoints:
                return False, "Nenhum endpoint configurado"

            api_token = config.get("api_token")
            if not api_token:
                return False, "API Token nao configurado"

            # Valida cada endpoint
            for ep in endpoints:
                name = ep.get("name", "")
                url = ep.get("endpoint_url", "")

                try:
                    validate_stream_name(name)
                    validate_url(url, f"Endpoint '{name}'")
                except HubbleConfigError as e:
                    return False, str(e)

            # Testa conexao com primeiro endpoint
            test_url = endpoints[0].get("endpoint_url")
            timeout = config.get("request_timeout", 60)

            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            }

            body = {
                "$method": "find",
                "params": {"query": {"$limit": 1}}
            }

            response = requests.post(
                test_url,
                headers=headers,
                json=body,
                timeout=timeout
            )
            response.raise_for_status()

            # Valida que retornou JSON valido
            data = response.json()
            if "data" not in data:
                return False, "Resposta da API nao contem campo 'data'"

            logger.info(f"Conexao verificada com sucesso: {test_url}")
            return True, None

        except requests.exceptions.Timeout:
            return False, f"Timeout ao conectar com a API ({timeout}s)"
        except requests.exceptions.ConnectionError as e:
            return False, f"Erro de conexao: {e}"
        except requests.exceptions.HTTPError as e:
            return False, f"Erro HTTP: {e.response.status_code} - {e.response.text[:200]}"
        except Exception as e:
            return False, f"Erro inesperado: {str(e)}"

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """Cria lista de streams baseado nos endpoints configurados."""
        auth = TokenAuthenticator(token=config["api_token"])

        streams = []
        for ep_config in config.get("endpoints", []):
            stream_name = ep_config.get("name")
            endpoint_url = ep_config.get("endpoint_url")

            if stream_name and endpoint_url:
                try:
                    stream = HubbleStream(
                        authenticator=auth,
                        config=config,
                        stream_name=stream_name,
                        endpoint_url=endpoint_url
                    )
                    streams.append(stream)
                except HubbleConfigError as e:
                    logger.error(f"Erro ao criar stream '{stream_name}': {e}")
                    continue

        logger.info(f"SourceHubble: {len(streams)} streams configurados")
        return streams
