import asyncio
import json
import logging
from collections.abc import Awaitable
from io import StringIO
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory
from ivaas_core import NAME_MAX_LENGTH, SSN_PATTERN

from income_verification.request_context import (
    JsonLogFormatter,
    RequestContextFilter,
    RequestContextMiddleware,
    set_verification_log_context,
)

CORRELATION_ID = "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31:APP-2026-004471"
API_ROOT = "/api"
INCOME_VERIFICATION_PATH = f"{API_ROOT}/{settings.API_VERSION}/income-verification"


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
        headers={"Correlation-Id": CORRELATION_ID},
    )


def test_health_endpoint(client: Client) -> None:
    response = client.get(f"{API_ROOT}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_accepts_verification_request(client: Client) -> None:
    with patch("api.routes.logger") as logger:
        response = post_verification(client, valid_request())

    assert response.status_code == 200
    assert response.headers["Correlation-Id"] == CORRELATION_ID
    body = response.json()
    assert UUID(body["verificationId"]).version == 4
    assert body["sources"] == []
    logger.info.assert_called_once_with(
        "income verification request accepted",
        extra={
            "event_name": "income_verification.request.accepted",
            "http_request_method": "POST",
            "url_path": INCOME_VERIFICATION_PATH,
        },
    )


def test_accepts_full_ssn_instead_of_last_four(client: Client) -> None:
    payload = valid_request()
    payload.pop("last4Ssn")
    payload["ssn"] = "123001234"

    response = post_verification(client, payload)

    assert response.status_code == 200


def test_rejects_missing_correlation_id(client: Client) -> None:
    with patch("api.api.logger") as logger:
        response = client.post(
            INCOME_VERIFICATION_PATH,
            data=json.dumps(valid_request()),
            content_type="application/json",
        )

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "Request failed validation.",
    }
    logger.warning.assert_called_once_with(
        "income verification request rejected",
        extra={
            "event_name": "income_verification.request.rejected",
            "error_type": "validation_error",
            "http_request_method": "POST",
            "url_path": INCOME_VERIFICATION_PATH,
            "validation_error_count": 1,
        },
    )


def test_accepts_correlation_id_without_client_ref(client: Client) -> None:
    uuid__only_correlation_id = CORRELATION_ID.split(":")[0]
    response = client.post(
        INCOME_VERIFICATION_PATH,
        data=json.dumps(valid_request()),
        content_type="application/json",
        headers={"Correlation-Id": uuid__only_correlation_id},
    )

    assert response.status_code == 200
    assert response.headers["Correlation-Id"] == uuid__only_correlation_id


def test_rejects_both_ssn_forms(client: Client) -> None:
    payload = valid_request()
    payload["ssn"] = "123001234"

    response = post_verification(client, payload)

    assert response.status_code == 400
    assert response.headers["Correlation-Id"] == CORRELATION_ID
    assert response.json()["code"] == "INVALID_REQUEST"


def test_logs_validation_count_without_rejected_value(client: Client) -> None:
    rejected_name = "sensitive-name-value" * 20
    payload = valid_request()
    payload["firstName"] = rejected_name
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(JsonLogFormatter())
    api_logger = logging.getLogger("api")
    original_handlers = api_logger.handlers
    api_logger.handlers = [handler]

    try:
        response = post_verification(client, payload)
    finally:
        api_logger.handlers = original_handlers

    assert response.status_code == 400
    record = json.loads(stream.getvalue())
    assert record["event.name"] == "income_verification.request.rejected"
    assert record["error.type"] == "validation_error"
    assert record["validation.error.count"] == 1
    assert record["http.request.method"] == "POST"
    assert record["url.path"] == INCOME_VERIFICATION_PATH
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert rejected_name not in stream.getvalue()


def test_stdout_is_structured_and_request_context_does_not_leak(client: Client) -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(JsonLogFormatter())
    api_logger = logging.getLogger("api")
    original_handlers = api_logger.handlers
    api_logger.handlers = [handler]
    payload = valid_request()
    payload["firstName"] = "SensitiveGivenName"
    payload["lastName"] = "SensitiveFamilyName"
    payload["last4Ssn"] = "9876"

    try:
        response = post_verification(client, payload)
        logging.getLogger("api.test").info(
            "outside request context",
            extra={
                "event_name": "outside_request.test",
                "custom_count": 2,
                "custom_details": {"status": "ok"},
                "request": "raw-sensitive-request",
                "request_payload": {"firstName": "never-serialize-this"},
            },
        )
    finally:
        api_logger.handlers = original_handlers

    assert response.status_code == 200
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(records) == 2
    accepted, outside_request = records
    assert accepted["level"] == "INFO"
    assert accepted["logger"] == "api.routes"
    assert accepted["message"] == "income verification request accepted"
    assert accepted["event.name"] == "income_verification.request.accepted"
    assert accepted["ivaas.correlation.id"] == CORRELATION_ID
    assert accepted["ivaas.application.id"] == "APP-2026-004471"
    assert accepted["ivaas.verification.id"] == response.json()["verificationId"]
    assert accepted["timestamp"].endswith("Z")

    assert outside_request["message"] == "outside request context"
    assert outside_request["event.name"] == "outside_request.test"
    assert "custom_count" not in outside_request
    assert "custom_details" not in outside_request
    assert "ivaas.correlation.id" not in outside_request
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
    adapter_logger = logging.getLogger("adapter_registry")
    original_handlers = adapter_logger.handlers
    adapter_logger.handlers = [handler]

    def emit_downstream_log(message: str, *, extra: dict[str, object]) -> None:
        logging.getLogger("adapter_registry.downstream").info(
            "downstream verification processing",
            extra={"event_name": "income_verification.downstream.test", "attempt": 1},
        )

    try:
        with patch("api.routes.logger.info", side_effect=emit_downstream_log):
            response = post_verification(client, valid_request())
    finally:
        adapter_logger.handlers = original_handlers

    assert response.status_code == 200
    record = json.loads(stream.getvalue())
    assert record["event.name"] == "income_verification.downstream.test"
    assert "attempt" not in record
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert record["ivaas.application.id"] == "APP-2026-004471"
    assert record["ivaas.verification.id"] == response.json()["verificationId"]


def test_async_request_context_is_isolated_between_concurrent_requests() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(JsonLogFormatter())
    api_logger = logging.getLogger("api")
    original_handlers = api_logger.handlers
    api_logger.handlers = [handler]

    async def get_response(request: HttpRequest) -> HttpResponse:
        await asyncio.sleep(0)
        application_id = request.headers["X-Application-Id"]
        verification_id = request.headers["X-Verification-Id"]
        set_verification_log_context(application_id, verification_id)
        await asyncio.sleep(0)
        logging.getLogger("api.concurrent").info("concurrent request")
        return HttpResponse()

    middleware = RequestContextMiddleware(get_response)
    request_factory = RequestFactory()
    requests = [
        request_factory.get(
            "/",
            headers={
                "Correlation-Id": "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31:one",
                "X-Application-Id": "application-one",
                "X-Verification-Id": "verification-one",
            },
        ),
        request_factory.get(
            "/",
            headers={
                "Correlation-Id": "4b459959-cdd4-4a77-ae2f-56b57c012028:two",
                "X-Application-Id": "application-two",
                "X-Verification-Id": "verification-two",
            },
        ),
    ]

    async def run_requests() -> None:
        await asyncio.gather(
            *(cast(Awaitable[HttpResponse], middleware(request)) for request in requests)
        )

    try:
        asyncio.run(run_requests())
        logging.getLogger("api.concurrent").info("after concurrent requests")
    finally:
        api_logger.handlers = original_handlers

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    request_records = {record["ivaas.application.id"]: record for record in records[:2]}
    assert request_records["application-one"]["ivaas.correlation.id"].endswith(":one")
    assert request_records["application-one"]["ivaas.verification.id"] == "verification-one"
    assert request_records["application-two"]["ivaas.correlation.id"].endswith(":two")
    assert request_records["application-two"]["ivaas.verification.id"] == "verification-two"
    assert "ivaas.correlation.id" not in records[2]
    assert "ivaas.application.id" not in records[2]
    assert "ivaas.verification.id" not in records[2]


def test_rejects_reversed_lookback_period(client: Client) -> None:
    payload = valid_request()
    payload["lookbackPeriod"] = {
        "startDate": "2026-06-30",
        "endDate": "2026-01-01",
    }

    response = post_verification(client, payload)

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_rejects_malformed_json(client: Client) -> None:
    response = client.post(
        INCOME_VERIFICATION_PATH,
        data="{",
        content_type="application/json",
        headers={"Correlation-Id": CORRELATION_ID},
    )

    assert response.status_code == 400
    assert response.headers["Correlation-Id"] == CORRELATION_ID
    assert response.json()["code"] == "INVALID_REQUEST"


def test_openapi_exposes_versioned_income_verification_path(client: Client) -> None:
    schema = client.get(f"{API_ROOT}/openapi.json").json()

    assert schema["info"]["version"] == settings.API_VERSION
    versioned_path = INCOME_VERIFICATION_PATH
    assert versioned_path in schema["paths"]
    operation = schema["paths"][versioned_path]["post"]
    assert operation["parameters"][0]["name"] == "Correlation-Id"
    assert "Correlation-Id" in operation["responses"]["200"]["headers"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/VerificationRequest"
    }
    request_schema = schema["components"]["schemas"]["VerificationRequest"]
    assert request_schema["properties"]["firstName"]["maxLength"] == NAME_MAX_LENGTH
    assert request_schema["properties"]["ssn"]["anyOf"][0]["pattern"] == SSN_PATTERN
    assert request_schema["oneOf"] == [
        {"required": ["ssn"]},
        {"required": ["last4Ssn"]},
    ]
    source_id_schema = schema["components"]["schemas"]["SourceResult"]["properties"]["sourceId"]
    assert source_id_schema["type"] == "string"
    assert source_id_schema["minLength"] == 1
    assert "enum" not in source_id_schema
    assert f"{API_ROOT}/health" not in schema["paths"]


def test_openapi_documentation_endpoint(client: Client) -> None:
    response = client.get(f"{API_ROOT}/docs")

    assert response.status_code == 200
