"""HTTP smoke tests for an existing deployment; run with `make test-smoke`."""

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from smoke_client import ApiRequest, RecordProperty, check_connection, request_json, required_env


def test_health(base_url: str) -> None:
    status, _, body = request_json(f"{base_url}/api/health", endpoint="Health endpoint")
    assert status == 200, f"Health endpoint returned HTTP {status}; expected HTTP 200."
    assert body == {"status": "ok"}, "Unexpected health response."


def test_connection(api: ApiRequest) -> None:
    check_connection(api)


def test_missing_authentication(base_url: str, record_property: RecordProperty) -> None:
    correlation_id = str(uuid4())
    record_property("correlation_id", correlation_id)
    version = os.environ.get("SMOKE_API_VERSION", "v1")
    status, _, _ = request_json(
        f"{base_url}/api/{version}/test-connection",
        endpoint="Unauthenticated connection endpoint",
        headers={"Correlation-Id": correlation_id},
        parse_json=False,
    )
    assert status == 401, f"Unauthenticated request returned HTTP {status}; expected HTTP 401."


@pytest.fixture
def no_income_request() -> dict[str, Any]:
    fixture_path = os.environ.get("SMOKE_NO_INCOME_REQUEST")
    source_id = os.environ.get("SMOKE_SOURCE_ID")
    if not fixture_path and not source_id:
        pytest.skip("No approved no-income fixture supplied; verification coverage not exercised.")
    if not fixture_path or not source_id:
        pytest.fail("Set both SMOKE_NO_INCOME_REQUEST and SMOKE_SOURCE_ID.", pytrace=False)
    try:
        payload = json.loads(Path(fixture_path).read_text())
    except OSError, ValueError:
        pytest.fail(
            "SMOKE_NO_INCOME_REQUEST must name a readable JSON request file.", pytrace=False
        )
    assert isinstance(payload, dict), "No-income request fixture must be a JSON object."
    return payload | {"applicationId": f"SMOKE-{uuid4()}"}


def test_no_income(
    no_income_request: dict[str, Any], verified_api: ApiRequest, record_property: RecordProperty
) -> None:
    status, body = verified_api("income-verification", no_income_request)
    assert status == 200, f"No-income verification returned HTTP {status}; expected HTTP 200."
    assert isinstance(body, dict), "Verification response must be a JSON object."
    try:
        verification_id = UUID(body["verificationId"])
    except KeyError, TypeError, ValueError, AttributeError:
        pytest.fail("Verification response has no valid verificationId.", pytrace=False)
    record_property("verification_id", str(verification_id))
    sources = body.get("sources")
    assert isinstance(sources, list), "Verification response has no sources list."
    source_id = required_env("SMOKE_SOURCE_ID")
    matches = [
        source
        for source in sources
        if isinstance(source, dict) and source.get("sourceId") == source_id
    ]
    assert len(matches) == 1, "Expected exactly one result for SMOKE_SOURCE_ID."
    source = matches[0]
    assert source.get("status") == "NO_DATA", "Expected NO_DATA from the configured source."
    assert source.keys() >= {"rawIncome", "retrievedAt"}, "Missing income or retrieval fields."
    assert source["rawIncome"] is None, "Expected null rawIncome."
    assert source["retrievedAt"] is None, "Expected null retrievedAt."
