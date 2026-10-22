"""Shared HTTP helpers for IVaaS E2E tests and deployer-owned extensions."""

import json
import os
from collections.abc import Callable
from http.client import HTTPConnection, HTTPException, HTTPMessage, HTTPSConnection
from typing import Any
from urllib.parse import urlsplit

import pytest

type ApiRequest = Callable[[str, dict[str, Any] | None], tuple[int, Any]]
type RecordProperty = Callable[[str, object], None]


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"Set {name} before running E2E tests.", pytrace=False)
    return value


def request_json(
    url: str,
    *,
    endpoint: str,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    parse_json: bool = True,
) -> tuple[int, HTTPMessage, Any]:
    """Make a bounded request; diagnostics use a static endpoint label, never response data."""
    try:
        target = urlsplit(url)
        port = target.port
    except ValueError:
        pytest.fail(f"{endpoint} URL is invalid.", pytrace=False)
    if (
        target.scheme not in {"http", "https"}
        or not target.hostname
        or target.username is not None
        or target.password is not None
        or target.fragment
    ):
        pytest.fail(
            f"{endpoint} URL must use HTTP(S) without credentials or fragments.", pytrace=False
        )
    if target.scheme == "http" and target.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail(f"{endpoint} URL must use HTTPS outside localhost.", pytrace=False)
    connection_class = HTTPSConnection if target.scheme == "https" else HTTPConnection
    connection = connection_class(target.hostname, port, timeout=30)
    path = target.path or "/"
    if target.query:
        path += f"?{target.query}"
    status = None
    try:
        connection.request("POST" if data is not None else "GET", path, data, headers or {})
        with connection.getresponse() as response:
            status = response.status
            if 300 <= status < 400:
                pytest.fail(
                    f"{endpoint} returned HTTP {status}; redirects are disabled.", pytrace=False
                )
            if not parse_json:
                return status, response.headers, None
            try:
                body = json.load(response)
            except ValueError, UnicodeError:
                pytest.fail(f"{endpoint} returned HTTP {status} with invalid JSON.", pytrace=False)
            return status, response.headers, body
    except OSError, HTTPException:
        status_note = f" after HTTP {status}" if status is not None else ""
        pytest.fail(
            f"{endpoint} request failed or timed out{status_note}; check connectivity and TLS.",
            pytrace=False,
        )
    finally:
        connection.close()


def check_connection(api: ApiRequest) -> None:
    """Confirm the configured program and environment before invoking verification."""
    status, body = api("test-connection", None)
    assert status == 200, f"Connection test returned HTTP {status}; expected HTTP 200."
    assert isinstance(body, dict), "Connection test response must be a JSON object."
    assert body.keys() >= {"authenticatedAs", "environment"}, (
        "Connection test response is missing required fields."
    )
    assert body["authenticatedAs"] == required_env("E2E_EXPECTED_PROGRAM"), (
        "Connection test returned an unexpected program; check E2E_EXPECTED_PROGRAM "
        "and the application's client-to-program configuration."
    )
    assert body["environment"] == required_env("E2E_EXPECTED_ENVIRONMENT"), (
        "Connection test returned an unexpected environment; check E2E_EXPECTED_ENVIRONMENT "
        "and the application's DEPLOYMENT_ENVIRONMENT."
    )
