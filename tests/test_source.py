"""
Testes unitarios para source-hubble.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from source_hubble.source import (
    SourceHubble,
    HubbleStream,
    HubbleConfigError,
    validate_url,
    validate_stream_name,
)


class TestValidateUrl:
    """Testes para funcao validate_url."""

    def test_valid_https_url(self):
        """URL HTTPS valida deve passar."""
        validate_url("https://example.com/api/data")

    def test_http_url_raises_error(self):
        """URL HTTP deve falhar."""
        with pytest.raises(HubbleConfigError) as exc_info:
            validate_url("http://example.com/api")
        assert "HTTPS" in str(exc_info.value)

    def test_empty_url_raises_error(self):
        """URL vazia deve falhar."""
        with pytest.raises(HubbleConfigError) as exc_info:
            validate_url("")
        assert "vazio" in str(exc_info.value)

    def test_url_without_domain_raises_error(self):
        """URL sem dominio deve falhar."""
        with pytest.raises(HubbleConfigError) as exc_info:
            validate_url("https:///path")
        assert "dominio" in str(exc_info.value)

    def test_url_with_dangerous_chars_raises_error(self):
        """URL com caracteres perigosos deve falhar."""
        dangerous_urls = [
            "https://example.com/<script>",
            "https://example.com/path?q=\"test\"",
            "https://example.com/{path}",
        ]
        for url in dangerous_urls:
            with pytest.raises(HubbleConfigError) as exc_info:
                validate_url(url)
            assert "caractere invalido" in str(exc_info.value)


class TestValidateStreamName:
    """Testes para funcao validate_stream_name."""

    def test_valid_names(self):
        """Nomes validos devem passar."""
        valid_names = ["vacancies", "candidates", "my_stream", "stream123", "a1b2c3"]
        for name in valid_names:
            validate_stream_name(name)

    def test_empty_name_raises_error(self):
        """Nome vazio deve falhar."""
        with pytest.raises(HubbleConfigError) as exc_info:
            validate_stream_name("")
        assert "vazio" in str(exc_info.value)

    def test_uppercase_raises_error(self):
        """Nome com maiusculas deve falhar."""
        with pytest.raises(HubbleConfigError) as exc_info:
            validate_stream_name("MyStream")
        assert "invalido" in str(exc_info.value)

    def test_starting_with_number_raises_error(self):
        """Nome comecando com numero deve falhar."""
        with pytest.raises(HubbleConfigError) as exc_info:
            validate_stream_name("123stream")
        assert "invalido" in str(exc_info.value)

    def test_special_chars_raises_error(self):
        """Nome com caracteres especiais deve falhar."""
        with pytest.raises(HubbleConfigError) as exc_info:
            validate_stream_name("my-stream")
        assert "invalido" in str(exc_info.value)


class TestHubbleStream:
    """Testes para classe HubbleStream."""

    def test_initialization(self, valid_config):
        """Stream deve inicializar corretamente."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="vacancies",
            endpoint_url="https://hub.data2apis.com/dataset/all-hub-vacancies"
        )

        assert stream.name == "vacancies"
        assert stream.url_base == "https://hub.data2apis.com/"
        assert stream.page_size == 100
        assert stream.request_timeout == 30

    def test_invalid_url_raises_error(self, valid_config):
        """URL invalida deve falhar na inicializacao."""
        auth = MagicMock()
        with pytest.raises(HubbleConfigError):
            HubbleStream(
                authenticator=auth,
                config=valid_config,
                stream_name="vacancies",
                endpoint_url="http://insecure.com/api"
            )

    def test_invalid_stream_name_raises_error(self, valid_config):
        """Nome invalido deve falhar na inicializacao."""
        auth = MagicMock()
        with pytest.raises(HubbleConfigError):
            HubbleStream(
                authenticator=auth,
                config=valid_config,
                stream_name="Invalid-Name",
                endpoint_url="https://hub.data2apis.com/dataset/test"
            )

    def test_clean_null_bytes(self, valid_config):
        """Deve limpar null bytes corretamente."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        # Teste com null byte unicode
        text_with_null = 'Test\\u0000Value'
        cleaned = stream._clean_null_bytes(text_with_null)
        assert '\\u0000' not in cleaned
        assert cleaned == 'TestValue'

        # Teste com null byte literal
        text_with_literal_null = 'Test\x00Value'
        cleaned = stream._clean_null_bytes(text_with_literal_null)
        assert '\x00' not in cleaned

    def test_infer_json_type(self, valid_config):
        """Deve inferir tipos JSON corretamente."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        # String
        assert stream._infer_json_type("hello")["type"] == ["null", "string"]

        # Integer
        assert stream._infer_json_type(42)["type"] == ["null", "integer"]

        # Float
        assert stream._infer_json_type(3.14)["type"] == ["null", "number"]

        # Boolean
        assert stream._infer_json_type(True)["type"] == ["null", "boolean"]

        # List
        assert stream._infer_json_type([1, 2, 3])["type"] == ["null", "array"]

        # Dict
        assert stream._infer_json_type({"key": "value"})["type"] == ["null", "object"]

        # None
        assert stream._infer_json_type(None)["type"] == "null"

        # Date string
        result = stream._infer_json_type("2024-01-01T00:00:00.000Z")
        assert result["format"] == "date-time"

    def test_parse_response(self, valid_config, mock_response):
        """Deve parsear response corretamente."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        records = list(stream.parse_response(mock_response))
        assert len(records) == 1
        assert records[0]["_id"] == "1"
        assert records[0]["name"] == "Test"

    def test_parse_response_with_null_bytes(self, valid_config, mock_response_with_null_bytes):
        """Deve limpar null bytes ao parsear."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        records = list(stream.parse_response(mock_response_with_null_bytes))
        assert len(records) == 1
        # Null bytes devem ter sido removidos
        assert "\\u0000" not in records[0].get("name", "")

    def test_next_page_token_continues(self, valid_config):
        """Deve continuar paginacao se page_size registros retornados."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )
        stream.page_size = 2

        response = MagicMock()
        response.text = '{"data": [{"_id": "1"}, {"_id": "2"}]}'

        token = stream.next_page_token(response)
        assert token is not None
        assert token["last_id"] == "2"

    def test_next_page_token_stops(self, valid_config):
        """Deve parar paginacao se menos que page_size registros."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )
        stream.page_size = 100

        response = MagicMock()
        response.text = '{"data": [{"_id": "1"}]}'

        token = stream.next_page_token(response)
        assert token is None

    def test_request_body_json(self, valid_config):
        """Deve montar body JSON corretamente."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        body = stream.request_body_json()
        assert body["$method"] == "find"
        assert "$limit" in body["params"]["query"]
        assert "$sort" in body["params"]["query"]

    def test_request_body_json_with_pagination(self, valid_config):
        """Deve incluir cursor na paginacao."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        body = stream.request_body_json(next_page_token={"last_id": "abc123"})
        assert body["params"]["query"]["_id"] == {"$gt": "abc123"}

    def test_should_retry_on_server_errors(self, valid_config):
        """Deve fazer retry em erros de servidor."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        for status_code in [429, 500, 502, 503, 504]:
            response = MagicMock()
            response.status_code = status_code
            assert stream.should_retry(response) is True

    def test_should_not_retry_on_client_errors(self, valid_config):
        """Nao deve fazer retry em erros de cliente."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        for status_code in [400, 401, 403, 404]:
            response = MagicMock()
            response.status_code = status_code
            assert stream.should_retry(response) is False

    def test_state_getter_setter(self, valid_config):
        """Deve gerenciar state corretamente."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        # Verifica state inicial
        assert "updatedAt" in stream.state

        # Atualiza state
        new_state = {"updatedAt": "2024-06-01T00:00:00.000Z"}
        stream.state = new_state

        assert stream.state["updatedAt"] == "2024-06-01T00:00:00.000Z"


class TestSourceHubble:
    """Testes para classe SourceHubble."""

    def test_streams_creation(self, valid_config):
        """Deve criar streams corretamente."""
        source = SourceHubble()
        streams = source.streams(valid_config)

        assert len(streams) == 2
        assert streams[0].name == "vacancies"
        assert streams[1].name == "candidates"

    def test_streams_with_invalid_endpoint_skipped(self, valid_config):
        """Deve pular endpoints invalidos."""
        config = valid_config.copy()
        config["endpoints"] = [
            {"name": "valid_stream", "endpoint_url": "https://valid.com/api"},
            {"name": "Invalid-Name", "endpoint_url": "https://also-valid.com/api"},
        ]

        source = SourceHubble()
        streams = source.streams(config)

        # Apenas o stream valido deve ser criado
        assert len(streams) == 1
        assert streams[0].name == "valid_stream"

    @patch('source_hubble.source.requests.post')
    def test_check_connection_success(self, mock_post, valid_config):
        """Deve retornar sucesso quando API responde."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_post.return_value = mock_response

        source = SourceHubble()
        success, error = source.check_connection(MagicMock(), valid_config)

        assert success is True
        assert error is None

    @patch('source_hubble.source.requests.post')
    def test_check_connection_timeout(self, mock_post, valid_config):
        """Deve retornar erro em timeout."""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        source = SourceHubble()
        success, error = source.check_connection(MagicMock(), valid_config)

        assert success is False
        assert "Timeout" in error

    @patch('source_hubble.source.requests.post')
    def test_check_connection_http_error(self, mock_post, valid_config):
        """Deve retornar erro em HTTP error."""
        import requests
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response
        mock_post.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        source = SourceHubble()
        success, error = source.check_connection(MagicMock(), valid_config)

        assert success is False
        assert "HTTP" in error or "401" in error

    def test_check_connection_no_endpoints(self):
        """Deve retornar erro se nenhum endpoint configurado."""
        config = {"api_token": "test", "endpoints": []}

        source = SourceHubble()
        success, error = source.check_connection(MagicMock(), config)

        assert success is False
        assert "endpoint" in error.lower()

    def test_check_connection_no_token(self, valid_config):
        """Deve retornar erro se token nao configurado."""
        config = valid_config.copy()
        del config["api_token"]

        source = SourceHubble()
        success, error = source.check_connection(MagicMock(), config)

        assert success is False
        assert "Token" in error

    def test_check_connection_invalid_endpoint_url(self, valid_config):
        """Deve retornar erro se URL do endpoint invalida."""
        config = valid_config.copy()
        config["endpoints"] = [
            {"name": "test", "endpoint_url": "http://insecure.com/api"}
        ]

        source = SourceHubble()
        success, error = source.check_connection(MagicMock(), config)

        assert success is False
        assert "HTTPS" in error


class TestSchemaDiscovery:
    """Testes para descoberta dinamica de schema."""

    def test_discover_schema_from_record(self, valid_config, sample_record):
        """Deve descobrir schema a partir de registro."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        stream._discover_schema_from_record(sample_record)

        schema = stream.get_json_schema()
        assert "_id" in schema["properties"]
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]
        assert "enabled" in schema["properties"]
        assert "tags" in schema["properties"]
        assert "metadata" in schema["properties"]

    def test_schema_not_rediscovered(self, valid_config, sample_record):
        """Schema nao deve ser redescoberto apos primeira vez."""
        auth = MagicMock()
        stream = HubbleStream(
            authenticator=auth,
            config=valid_config,
            stream_name="test",
            endpoint_url="https://hub.data2apis.com/dataset/test"
        )

        stream._discover_schema_from_record(sample_record)
        first_schema = stream.get_json_schema()

        # Tenta descobrir novamente com registro diferente
        different_record = {"_id": "1", "new_field": "value"}
        stream._discover_schema_from_record(different_record)
        second_schema = stream.get_json_schema()

        # Schema deve ser o mesmo
        assert first_schema == second_schema
        assert "new_field" not in second_schema["properties"]
