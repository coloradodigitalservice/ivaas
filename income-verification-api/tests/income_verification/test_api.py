import asyncio
import json
import logging
from collections.abc import Awaitable, Iterator
from datetime import datetime
from io import StringIO
from typing import Any, cast
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory, override_settings
from example_adapter import ExampleAdapter
from ivaas_core import SubjectNotFound

from adapter_engine.registry import INCOME_SOURCE_ADAPTERS, registry
from income_verification.api_error_codes import ERRORS, ErrorCode
from income_verification.request_context import (
    JsonLogFormatter,
    LogField,
    RequestContextFilter,
    RequestContextMiddleware,
    set_agency_log_context,
    set_client_log_context,
    set_verification_log_context,
)
from tests.income_verification.security.authentication_test_support import (
    TEST_ACCESS_TOKEN,
    TEST_AGENCY_ID,
    TEST_CLIENT_ID,
)

pytestmark = pytest.mark.usefixtures("configured_api_authentication")

CORRELATION_ID = "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31:APP-2026-004471"
API_ROOT = "/api"
INCOME_VERIFICATION_PATH = f"{API_ROOT}/{settings.API_VERSION}/income-verification"
EXAMPLE_ADAPTER_SETTINGS = {
    "example": {
        "class": "example_adapter.ExampleAdapter",
        "enabled": True,
        "retry_policy": None,
        "circuit_breaker": None,
    }
}


@pytest.fixture(autouse=True)
def example_adapter_registered() -> Iterator[None]:
    """Serve every request from the example adapter, whatever the machine's settings enable."""
    with override_settings(**{INCOME_SOURCE_ADAPTERS: EXAMPLE_ADAPTER_SETTINGS}):
        registry.refresh_from_settings()
        yield
    registry.refresh_from_settings()


def authenticated_headers(**headers: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TEST_ACCESS_TOKEN}",
        **headers,
    }


def valid_request() -> dict[str, object]:
    return {
        "applicationId": "APP-2026-004471",
        "firstName": "John",
        "lastName": "Doe",
        "last4Ssn": "1234",
        "lookbackPeriod": {
            "startDate": "2026-01-01",
            "endDate": "2026-06-30",
        },
    }


def post_verification(client: Client, payload: object) -> Any:
    return client.post(
        INCOME_VERIFICATION_PATH,
        data=json.dumps(payload),
        content_type="application/json",
        headers=authenticated_headers(**{"Correlation-Id": CORRELATION_ID}),
    )


def assert_error_response(response: Any, code: ErrorCode, *, echoes_correlation_id: bool) -> None:
    definition = ERRORS[code]
    assert response.status_code == definition.status_code
    assert response.json() == {"code": code.value, "message": definition.message}
    if echoes_correlation_id:
        assert response.headers["Correlation-Id"] == CORRELATION_ID
    else:
        assert "Correlation-Id" not in response.headers


@pytest.fixture
def captured_income_verification_logs() -> Iterator[StringIO]:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("income_verification")
    original_handlers = logger.handlers
    logger.handlers = [handler]
    try:
        yield stream
    finally:
        logger.handlers = original_handlers


def test_health_endpoint(client: Client) -> None:
    response = client.get(f"{API_ROOT}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_accepts_verification_request(client: Client) -> None:
    with patch("income_verification.routes.logger") as logger:
        response = post_verification(client, valid_request())

    assert response.status_code == 200
    assert response.headers["Correlation-Id"] == CORRELATION_ID
    body = response.json()
    assert UUID(body["verificationId"]).version == 4
    [source] = body["sources"]
    assert datetime.fromisoformat(source.pop("retrievedAt")).tzinfo is not None
    assert source == {"sourceId": ExampleAdapter.source_id, "status": "OK", "rawIncome": {}}
    logger.info.assert_called_once_with(
        "income verification request accepted",
        extra={
            LogField.EVENT_NAME.value: "income_verification.request.accepted",
            LogField.HTTP_REQUEST_METHOD.value: "POST",
            LogField.URL_PATH.value: INCOME_VERIFICATION_PATH,
        },
    )


def test_adapter_failure_is_reported_as_the_source_status(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ExampleAdapter, "verify", MagicMock(side_effect=SubjectNotFound()))

    response = post_verification(client, valid_request())

    assert response.status_code == 200
    [source] = response.json()["sources"]
    assert source["status"] == "NO_DATA"
    assert source["retrievedAt"] is None
    assert source["rawIncome"] is None


def test_accepts_full_ssn_instead_of_last_four(client: Client) -> None:
    payload = valid_request()
    payload.pop("last4Ssn")
    payload["ssn"] = "123001234"

    response = post_verification(client, payload)

    assert response.status_code == 200


def test_rejects_malformed_full_ssn(client: Client) -> None:
    payload = valid_request()
    payload.pop("last4Ssn")
    payload["ssn"] = "99999PII9"

    response = post_verification(client, payload)

    assert_error_response(response, ErrorCode.INVALID_SSN_FORMAT, echoes_correlation_id=True)


def test_rejects_malformed_last_four_ssn(client: Client) -> None:
    payload = valid_request()
    payload["last4Ssn"] = "PII!"

    response = post_verification(client, payload)

    assert_error_response(response, ErrorCode.INVALID_LAST4_SSN_FORMAT, echoes_correlation_id=True)


def test_rejects_missing_identity_identifier(client: Client) -> None:
    payload = valid_request()
    payload.pop("last4Ssn")

    response = post_verification(client, payload)

    assert_error_response(
        response,
        ErrorCode.MISSING_IDENTITY_IDENTIFIER,
        echoes_correlation_id=True,
    )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("firstName", "SENTINEL-FIRST\nPRIVATE", ErrorCode.INVALID_FIRST_NAME),
        ("lastName", "SENTINEL-LAST\nPRIVATE", ErrorCode.INVALID_LAST_NAME),
        ("applicationId", "SENTINEL-APP\x00PRIVATE", ErrorCode.INVALID_APPLICATION_ID),
    ],
)
def test_rejects_invalid_text_fields(
    client: Client,
    field: str,
    value: str,
    code: ErrorCode,
) -> None:
    payload = valid_request()
    payload[field] = value

    response = post_verification(client, payload)

    assert_error_response(response, code, echoes_correlation_id=True)


def test_rejects_missing_correlation_id(client: Client) -> None:
    with patch("income_verification.api_errors.logger") as logger:
        response = client.post(
            INCOME_VERIFICATION_PATH,
            data=json.dumps(valid_request()),
            content_type="application/json",
            headers=authenticated_headers(),
        )

    assert_error_response(response, ErrorCode.MISSING_CORRELATION_ID, echoes_correlation_id=False)
    logger.warning.assert_called_once_with(
        "income verification request rejected",
        extra={
            LogField.EVENT_NAME.value: "income_verification.request.rejected",
            LogField.ERROR_TYPE.value: "validation_error",
            LogField.ERROR_CODE.value: ErrorCode.MISSING_CORRELATION_ID.value,
            LogField.HTTP_REQUEST_METHOD.value: "POST",
            LogField.HTTP_RESPONSE_STATUS_CODE.value: 400,
            LogField.URL_PATH.value: INCOME_VERIFICATION_PATH,
            LogField.VALIDATION_ERROR_COUNT.value: 1,
            LogField.VALIDATION_ERRORS.value: [{"field": "Correlation-Id", "reason": "missing"}],
        },
    )


def test_rejects_malformed_correlation_id_without_echoing_or_retaining_it(
    client: Client,
    captured_income_verification_logs: StringIO,
) -> None:
    malformed_correlation_id = "SENTINEL-MALFORMED-CORRELATION-ID"
    response = client.post(
        INCOME_VERIFICATION_PATH,
        data=json.dumps(valid_request()),
        content_type="application/json",
        headers=authenticated_headers(**{"Correlation-Id": malformed_correlation_id}),
    )

    assert_error_response(response, ErrorCode.INVALID_CORRELATION_ID, echoes_correlation_id=False)
    record = json.loads(captured_income_verification_logs.getvalue())
    assert record["error.code"] == ErrorCode.INVALID_CORRELATION_ID
    assert "ivaas.correlation.id" not in record
    assert malformed_correlation_id not in captured_income_verification_logs.getvalue()


def test_accepts_correlation_id_without_client_ref(client: Client) -> None:
    uuid__only_correlation_id = CORRELATION_ID.split(":")[0]
    response = client.post(
        INCOME_VERIFICATION_PATH,
        data=json.dumps(valid_request()),
        content_type="application/json",
        headers=authenticated_headers(**{"Correlation-Id": uuid__only_correlation_id}),
    )

    assert response.status_code == 200
    assert response.headers["Correlation-Id"] == uuid__only_correlation_id


def test_rejects_both_ssn_forms(client: Client) -> None:
    payload = valid_request()
    payload["ssn"] = "123001234"

    response = post_verification(client, payload)

    assert_error_response(
        response,
        ErrorCode.MULTIPLE_IDENTITY_IDENTIFIERS,
        echoes_correlation_id=True,
    )


def test_logs_validation_count_without_rejected_value(
    client: Client,
    captured_income_verification_logs: StringIO,
) -> None:
    rejected_name = "sensitive-name-value" * 20
    payload = valid_request()
    payload["firstName"] = rejected_name

    response = post_verification(client, payload)

    assert response.status_code == 400
    record = json.loads(captured_income_verification_logs.getvalue())
    assert record["event.name"] == "income_verification.request.rejected"
    assert record["error.type"] == "validation_error"
    assert record["error.code"] == ErrorCode.INVALID_FIRST_NAME
    assert record["validation.error.count"] == 1
    assert record["validation.errors"] == [{"field": "firstName", "reason": "invalid"}]
    assert record["http.request.method"] == "POST"
    assert record["url.path"] == INCOME_VERIFICATION_PATH
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert rejected_name not in captured_income_verification_logs.getvalue()


def test_stdout_is_structured_and_request_context_does_not_leak(
    client: Client,
    captured_income_verification_logs: StringIO,
) -> None:
    payload = valid_request()
    payload["firstName"] = "SensitiveGivenName"
    payload["lastName"] = "SensitiveFamilyName"
    payload["last4Ssn"] = "9876"

    response = post_verification(client, payload)
    logging.getLogger("income_verification.test").info(
        "outside request context",
        extra={
            LogField.EVENT_NAME.value: "outside_request.test",
            "custom_count": 2,
            "custom_details": {"status": "ok"},
            "request": "raw-sensitive-request",
            "request_payload": {"firstName": "never-serialize-this"},
        },
    )

    assert response.status_code == 200
    records = [
        json.loads(line) for line in captured_income_verification_logs.getvalue().splitlines()
    ]
    assert len(records) == 2
    accepted, outside_request = records
    assert accepted["level"] == "INFO"
    assert accepted["logger"] == "income_verification.routes"
    assert accepted["message"] == "income verification request accepted"
    assert accepted["event.name"] == "income_verification.request.accepted"
    assert accepted["ivaas.correlation.id"] == CORRELATION_ID
    assert accepted["auth.client.id"] == TEST_CLIENT_ID
    assert accepted["ivaas.agency.id"] == TEST_AGENCY_ID
    assert accepted["ivaas.application.id"] == "APP-2026-004471"
    assert accepted["ivaas.verification.id"] == response.json()["verificationId"]
    assert accepted["timestamp"].endswith("Z")

    assert outside_request["message"] == "outside request context"
    assert outside_request["event.name"] == "outside_request.test"
    assert "custom_count" not in outside_request
    assert "custom_details" not in outside_request
    assert "ivaas.correlation.id" not in outside_request
    assert "auth.client.id" not in outside_request
    assert "ivaas.agency.id" not in outside_request
    assert "ivaas.application.id" not in outside_request
    assert "ivaas.verification.id" not in outside_request

    serialized_records = json.dumps(records)
    assert "SensitiveGivenName" not in serialized_records
    assert "SensitiveFamilyName" not in serialized_records
    assert "9876" not in serialized_records
    assert "raw-sensitive-request" not in serialized_records
    assert "never-serialize-this" not in serialized_records


def test_downstream_logs_inherit_verification_context(client: Client) -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(JsonLogFormatter())
    adapter_logger = logging.getLogger("adapter_engine")
    original_handlers = adapter_logger.handlers
    adapter_logger.handlers = [handler]

    try:
        response = post_verification(client, valid_request())
    finally:
        adapter_logger.handlers = original_handlers

    assert response.status_code == 200
    record = json.loads(stream.getvalue())
    assert record["message"] == "invoking adapter 'example' to handle request"
    assert record["event.name"] == "adapter_engine.adapter.invoked"
    assert record["ivaas.source.id"] == ExampleAdapter.source_id
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert record["auth.client.id"] == TEST_CLIENT_ID
    assert record["ivaas.agency.id"] == TEST_AGENCY_ID
    assert record["ivaas.application.id"] == "APP-2026-004471"
    assert record["ivaas.verification.id"] == response.json()["verificationId"]


def test_async_request_context_is_isolated_between_concurrent_requests() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(JsonLogFormatter())
    api_logger = logging.getLogger("income_verification")
    original_handlers = api_logger.handlers
    api_logger.handlers = [handler]

    context_by_path = {
        "/one": ("client-one", "agency-one", "application-one", "verification-one"),
        "/two": ("client-two", "agency-two", "application-two", "verification-two"),
    }

    async def get_response(request: HttpRequest) -> HttpResponse:
        await asyncio.sleep(0)
        client_id, agency_id, application_id, verification_id = context_by_path[request.path]
        set_client_log_context(client_id)
        set_agency_log_context(agency_id)
        set_verification_log_context(application_id, verification_id)
        await asyncio.sleep(0)
        logging.getLogger("income_verification.concurrent").info("concurrent request")
        return HttpResponse()

    middleware = RequestContextMiddleware(get_response)
    request_factory = RequestFactory()
    requests = [
        request_factory.get(
            "/one",
            headers={
                "Correlation-Id": "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31:one",
            },
        ),
        request_factory.get(
            "/two",
            headers={
                "Correlation-Id": "4b459959-cdd4-4a77-ae2f-56b57c012028:two",
            },
        ),
    ]

    async def run_requests() -> None:
        await asyncio.gather(
            *(cast(Awaitable[HttpResponse], middleware(request)) for request in requests)
        )

    try:
        asyncio.run(run_requests())
        logging.getLogger("income_verification.concurrent").info("after concurrent requests")
    finally:
        api_logger.handlers = original_handlers

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    request_records = {record["ivaas.application.id"]: record for record in records[:2]}
    assert request_records["application-one"]["ivaas.correlation.id"].endswith(":one")
    assert request_records["application-one"]["auth.client.id"] == "client-one"
    assert request_records["application-one"]["ivaas.agency.id"] == "agency-one"
    assert request_records["application-one"]["ivaas.verification.id"] == "verification-one"
    assert request_records["application-two"]["ivaas.correlation.id"].endswith(":two")
    assert request_records["application-two"]["auth.client.id"] == "client-two"
    assert request_records["application-two"]["ivaas.agency.id"] == "agency-two"
    assert request_records["application-two"]["ivaas.verification.id"] == "verification-two"
    assert "ivaas.correlation.id" not in records[2]
    assert "auth.client.id" not in records[2]
    assert "ivaas.agency.id" not in records[2]
    assert "ivaas.application.id" not in records[2]
    assert "ivaas.verification.id" not in records[2]


def test_rejects_reversed_lookback_period(client: Client) -> None:
    payload = valid_request()
    payload["lookbackPeriod"] = {
        "startDate": "2026-06-30",
        "endDate": "2026-01-01",
    }

    response = post_verification(client, payload)

    assert_error_response(response, ErrorCode.INVALID_LOOKBACK_PERIOD, echoes_correlation_id=True)


@pytest.mark.parametrize(
    ("case", "sentinels"),
    [
        ("ssn", ("SENTINEL-SSN-98765",)),
        ("last4Ssn", ("SENTINEL-LAST4",)),
        ("firstName", ("SENTINEL-FIRST-PRIVATE",)),
        ("lastName", ("SENTINEL-LAST-PRIVATE",)),
        ("applicationId", ("SENTINEL-APPLICATION-PRIVATE",)),
        ("lookbackPeriod", ("2099-12-31", "1901-01-01")),
    ],
)
def test_rejected_request_logs_exclude_user_values(
    client: Client,
    captured_income_verification_logs: StringIO,
    case: str,
    sentinels: tuple[str, ...],
) -> None:
    payload = valid_request()
    if case == "ssn":
        payload.pop("last4Ssn")
        payload["ssn"] = sentinels[0]
    elif case == "lookbackPeriod":
        payload[case] = {"startDate": sentinels[0], "endDate": sentinels[1]}
    else:
        payload[case] = f"{sentinels[0]}\x00"

    response = post_verification(client, payload)

    assert response.status_code == 400
    emitted = captured_income_verification_logs.getvalue()
    record = json.loads(emitted)
    assert record["event.name"] == "income_verification.request.rejected"
    assert record["error.type"] == "validation_error"
    assert record["http.request.method"] == "POST"
    assert record["http.response.status_code"] == 400
    assert record["url.path"] == INCOME_VERIFICATION_PATH
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert record["validation.error.count"] >= 1
    assert all(set(error) == {"field", "reason"} for error in record["validation.errors"])
    assert "exception" not in record
    assert "stack" not in record
    for sentinel in sentinels:
        assert sentinel not in emitted


def test_multiple_validation_failures_use_fallback_without_logging_values(
    client: Client,
    captured_income_verification_logs: StringIO,
) -> None:
    sentinels = (
        "SENTINEL-MULTI-APP",
        "SENTINEL-MULTI-FIRST",
        "SENTINEL-MULTI-LAST4",
    )
    payload = valid_request()
    payload["applicationId"] = f"{sentinels[0]}\x00"
    payload["firstName"] = f"{sentinels[1]}\x00"
    payload["last4Ssn"] = sentinels[2]

    response = post_verification(client, payload)

    assert_error_response(response, ErrorCode.INVALID_REQUEST, echoes_correlation_id=True)
    emitted = captured_income_verification_logs.getvalue()
    record = json.loads(emitted)
    assert record["error.code"] == ErrorCode.INVALID_REQUEST
    assert record["validation.error.count"] == 3
    assert all(sentinel not in emitted for sentinel in sentinels)


def test_rejects_malformed_json(client: Client) -> None:
    response = client.post(
        INCOME_VERIFICATION_PATH,
        data="{",
        content_type="application/json",
        headers=authenticated_headers(**{"Correlation-Id": CORRELATION_ID}),
    )

    assert_error_response(response, ErrorCode.INVALID_REQUEST, echoes_correlation_id=True)


def test_openapi_exposes_versioned_income_verification_path(client: Client) -> None:
    schema = client.get(f"{API_ROOT}/openapi.json").json()

    assert schema["info"]["version"] == settings.API_VERSION
    assert INCOME_VERIFICATION_PATH in schema["paths"]
    assert f"{API_ROOT}/health" not in schema["paths"]


def test_openapi_documentation_endpoint(client: Client) -> None:
    response = client.get(f"{API_ROOT}/docs")

    assert response.status_code == 200


def test_core_runtime_error_during_request_validation_returns_500(client: Client) -> None:
    with patch(
        "income_verification.schemas.CoreVerificationRequest",
        side_effect=RuntimeError("simulated unexpected failure"),
    ):
        response = post_verification(client, valid_request())

    assert_error_response(
        response,
        ErrorCode.INTERNAL_ERROR,
        echoes_correlation_id=True,
    )
