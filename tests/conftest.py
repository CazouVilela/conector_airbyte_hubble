"""
Pytest fixtures for source-hubble tests.
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def valid_config():
    """Configuracao valida para testes."""
    return {
        "api_token": "test_token_123",
        "start_date": "2024-01-01T00:00:00.000Z",
        "page_size": 100,
        "request_timeout": 30,
        "max_retries": 3,
        "inter_page_delay": 0,  # Desabilita delay nos testes
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


@pytest.fixture
def mock_response():
    """Mock de response HTTP."""
    response = MagicMock()
    response.status_code = 200
    response.text = '{"data": [{"_id": "1", "updatedAt": "2024-01-01T00:00:00.000Z", "name": "Test"}]}'
    response.json.return_value = {
        "data": [
            {"_id": "1", "updatedAt": "2024-01-01T00:00:00.000Z", "name": "Test"}
        ]
    }
    return response


@pytest.fixture
def mock_response_with_null_bytes():
    """Mock de response com null bytes."""
    response = MagicMock()
    response.status_code = 200
    response.text = '{"data": [{"_id": "1", "name": "Test\\u0000Value"}]}'
    return response


@pytest.fixture
def mock_response_paginated():
    """Mock de response com paginacao."""
    def create_response(page: int, total_pages: int = 3, page_size: int = 100):
        response = MagicMock()
        response.status_code = 200

        records = []
        for i in range(page_size if page < total_pages else page_size // 2):
            record_id = (page - 1) * page_size + i + 1
            records.append({
                "_id": str(record_id),
                "updatedAt": "2024-01-01T00:00:00.000Z",
                "name": f"Record {record_id}"
            })

        response.text = f'{{"data": {records}}}'.replace("'", '"')
        response.json.return_value = {"data": records}
        return response

    return create_response


@pytest.fixture
def mock_error_response():
    """Mock de response com erro."""
    response = MagicMock()
    response.status_code = 500
    response.text = '{"error": "Internal Server Error"}'
    return response


@pytest.fixture
def sample_record():
    """Registro de exemplo para testes."""
    return {
        "_id": "abc123",
        "updatedAt": "2024-06-15T10:30:00.000Z",
        "createdAt": "2024-01-01T00:00:00.000Z",
        "name": "Test Record",
        "status": "active",
        "count": 42,
        "enabled": True,
        "tags": ["tag1", "tag2"],
        "metadata": {"key": "value"}
    }
