"""HTTP and authentication fixtures shared by E2E tests and nested adapter tests."""

import base64
import json
import os
from typing import Any
from urllib.parse import quote_plus, urlencode
from uuid import uuid4

import pytest

from e2e_test_client import ApiRequest, RecordProperty, check_connection, request_json, required_env


def pytest_sessionstart(session: pytest.Session) -> None:
    """Reject incomplete runner configuration before collecting and executing HTTP tests."""
    if session.config.option.collectonly:
        return
    required = (
        "E2E_BASE_URL",
        "E2E_TOKEN_URL",
        "E2E_CLIENT_ID",
        "E2E_CLIENT_SECRET",
        "E2E_EXPECTED_AGENCY",
        "E2E_EXPECTED_ENVIRONMENT",
    )
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise pytest.UsageError(
            f"Missing required E2E environment variables: {', '.join(missing)}."
        )


@pytest.fixture(scope="session")
def base_url() -> str:
    return required_env("E2E_BASE_URL").rstrip("/")


@pytest.fixture(scope="session")
def access_token() -> str:
    client_id = quote_plus(required_env("E2E_CLIENT_ID"), safe="")
    client_secret = quote_plus(required_env("E2E_CLIENT_SECRET"), safe="")
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    status, _, body = request_json(
        required_env("E2E_TOKEN_URL"),
        endpoint="Token endpoint",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=urlencode(
            {
                "grant_type": "client_credentials",
                "scope": os.environ.get("E2E_SCOPE", "ivaas/income.verify"),
            }
        ).encode(),
    )
    assert status == 200, f"Token endpoint returned HTTP {status}; expected HTTP 200."
    assert isinstance(body, dict), "Token response must be a JSON object."
    assert body.get("token_type", "").lower() == "bearer", "Expected a Bearer token."
    token = body.get("access_token")
    assert isinstance(token, str), "Token response has no access token."
    assert token, "Token response has an empty access token."
    return token


@pytest.fixture
def api(base_url: str, access_token: str, record_property: RecordProperty) -> ApiRequest:
    prefix = f"{base_url}/api/{os.environ.get('E2E_API_VERSION', 'v1')}"

    def request(path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
        correlation_id = str(uuid4())
        record_property(f"correlation_id_{path}", correlation_id)
        endpoint = {
            "test-connection": "Connection endpoint",
            "income-verification": "Verification endpoint",
        }.get(path, "API endpoint")
        status, headers, body = request_json(
            f"{prefix}/{path}",
            endpoint=endpoint,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Correlation-Id": correlation_id,
            },
            data=json.dumps(payload).encode() if payload is not None else None,
        )
        assert headers.get("Correlation-Id") == correlation_id, (
            f"{endpoint} returned HTTP {status} without the expected correlation ID."
        )
        return status, body

    return request


@pytest.fixture
def verified_api(api: ApiRequest) -> ApiRequest:
    check_connection(api)
    return api
