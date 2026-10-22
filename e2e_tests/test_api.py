"""HTTP E2E tests for an existing deployment; run with `make test-e2e`."""

import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from e2e_test_client import ApiRequest, RecordProperty, check_connection, request_json

type NoIncomeCase = tuple[Path, set[str]]


def test_health(base_url: str) -> None:
    status, _, body = request_json(f"{base_url}/api/health", endpoint="Health endpoint")
    assert status == 200, f"Health endpoint returned HTTP {status}; expected HTTP 200."
    assert body == {"status": "ok"}, "Unexpected health response."


def test_connection(api: ApiRequest) -> None:
    check_connection(api)


def test_missing_authentication(base_url: str, record_property: RecordProperty) -> None:
    correlation_id = str(uuid4())
    record_property("correlation_id", correlation_id)
    version = os.environ.get("E2E_API_VERSION", "v1")
    status, _, _ = request_json(
        f"{base_url}/api/{version}/test-connection",
        endpoint="Unauthenticated connection endpoint",
        headers={"Correlation-Id": correlation_id},
        parse_json=False,
    )
    assert status == 401, f"Unauthenticated request returned HTTP {status}; expected HTTP 401."


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Collect one verification test per approved no-income scenario."""
    if "no_income_case" not in metafunc.fixturenames:
        return
    cases_path = os.environ.get("E2E_NO_INCOME_CASES")
    if not cases_path:
        metafunc.parametrize(
            "no_income_case",
            [
                pytest.param(
                    None,
                    id="not-configured",
                    marks=pytest.mark.skip(
                        reason="No approved cases supplied; verification coverage not exercised."
                    ),
                )
            ],
        )
        return
    try:
        cases = json.loads(Path(cases_path).read_text())
    except OSError, ValueError:
        pytest.fail("E2E_NO_INCOME_CASES must name a readable JSON case file.", pytrace=False)
    if not isinstance(cases, list) or not cases:
        pytest.fail("No-income cases must be a nonempty JSON array.", pytrace=False)
    parameters: list[NoIncomeCase] = []
    names: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            pytest.fail("Each no-income case must be a JSON object.", pytrace=False)
        name = case.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name):
            pytest.fail(
                "Case names must contain 1-64 letters, digits, underscores, or hyphens.",
                pytrace=False,
            )
        if name in names:
            pytest.fail("No-income case names must be unique.", pytrace=False)
        request_file = case.get("requestFile")
        if not isinstance(request_file, str) or not request_file:
            pytest.fail("Each no-income case must specify requestFile.", pytrace=False)
        expected = case.get("expectedSources")
        if not isinstance(expected, dict) or not expected:
            pytest.fail("Each case must specify a nonempty expectedSources object.", pytrace=False)
        for source_id, result in expected.items():
            if not source_id or not isinstance(result, dict) or result.get("status") != "NO_DATA":
                pytest.fail(
                    "Each expected source must have a nonempty ID and status NO_DATA.",
                    pytrace=False,
                )
        parameters.append((Path(cases_path).parent / request_file, set(expected)))
        names.append(name)
    metafunc.parametrize("no_income_case", parameters, ids=names)


@pytest.fixture
def no_income_request(no_income_case: NoIncomeCase) -> dict[str, Any]:
    fixture_path, _ = no_income_case
    try:
        payload = json.loads(fixture_path.read_text())
    except OSError, ValueError:
        pytest.fail("No-income request fixtures must be readable JSON files.", pytrace=False)
    assert isinstance(payload, dict), "No-income request fixture must be a JSON object."
    return payload | {"applicationId": f"E2E-{uuid4()}"}


def test_no_income(
    no_income_request: dict[str, Any],
    no_income_case: NoIncomeCase,
    verified_api: ApiRequest,
    record_property: RecordProperty,
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
    _, expected_sources = no_income_case
    assert len(sources) == len(expected_sources), "Unexpected number of source results."
    seen: set[str] = set()
    for source in sources:
        assert isinstance(source, dict), "Each source result must be a JSON object."
        source_id = source.get("sourceId")
        assert isinstance(source_id, str), "Each source result must have a string sourceId."
        assert source_id in expected_sources, "Unexpected source in verification response."
        assert source_id not in seen, "Duplicate source in verification response."
        seen.add(source_id)
        assert source.get("status") == "NO_DATA", "Expected NO_DATA from each configured source."
        assert source.keys() >= {"rawIncome", "retrievedAt"}, "Missing income or retrieval fields."
        assert source["rawIncome"] is None, "Expected null rawIncome."
        assert source["retrievedAt"] is None, "Expected null retrievedAt."
