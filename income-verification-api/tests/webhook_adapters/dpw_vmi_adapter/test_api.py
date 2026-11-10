"""Check DPW VMI webhook authentication, body validation, and forwarding."""

import json
import logging
from collections.abc import Iterator
from unittest.mock import Mock
from uuid import UUID

import pytest
from django.conf import settings
from django.test import Client, override_settings
from dpw_vmi_adapter.forwarding import ProgramResponse
from dpw_vmi_adapter.signing import sign

from income_verification.request_context import JsonLogFormatter

WEBHOOK_PATH = "/dpw-vmi/v1/income-report"
WEBHOOK_URL = f"/api{WEBHOOK_PATH}"
WEBHOOK_KEY = "dpw-vmi-test-key"
SIGNED_AT = 1_700_000_000
BODY = (
    b'{"event_type":"ReportSubmission","report_metadata":{"confirmation_code":"report-123"},'
    b'"employment_records":42}'
)
AUTHENTICATION_ERROR = {
    "error_code": "WEBHOOK_AUTHENTICATION_FAILED",
    "message": "Webhook authentication failed. Check headers, timestamp, and signature.",
}
PROGRAMS = {
    "test-program": {
        "dpw_vmi": {
            "webhook_url": "https://program.example/webhook",
            "webhook_signing_key": "test-webhook-signing-key",
        },
    },
}


def signed_headers(
    *,
    body: bytes = BODY,
    timestamp: str = str(SIGNED_AT),
    key: str = WEBHOOK_KEY,
    confirmation_code: str | None = "report-123",
) -> dict[str, str]:
    headers = {
        "X-VMI-Timestamp": timestamp,
        "X-VMI-Signature": sign(body, key=key, timestamp=timestamp),
    }
    if confirmation_code is not None:
        headers["X-VMI-Confirmation-Code"] = confirmation_code
    return headers


@pytest.fixture(autouse=True)
def forward_webhook_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock(return_value=ProgramResponse(200, b"", None))
    monkeypatch.setattr("dpw_vmi_adapter.api.forward_webhook", mock)
    return mock


@pytest.fixture
def dpw_vmi_adapter() -> Iterator[None]:
    with (
        override_settings(
            ROOT_URLCONF="tests.webhook_adapters.dpw_vmi_adapter.urls",
            WEBHOOK_ADAPTERS={
                "dpw_vmi_adapter": {
                    "enabled": True,
                    "config": {
                        "webhook_path": WEBHOOK_PATH,
                        "webhook_api_key": WEBHOOK_KEY,
                        "webhook_timestamp_max_age_seconds": 300,
                        "program_timeout_seconds": 10,
                    },
                }
            },
            PROGRAMS=PROGRAMS,
        ),
        override_settings(
            INSTALLED_APPS=list(dict.fromkeys([*settings.INSTALLED_APPS, "dpw_vmi_adapter"]))
        ),
    ):
        yield


@pytest.mark.usefixtures("dpw_vmi_adapter")
@pytest.mark.parametrize("received_at", [SIGNED_AT - 5, SIGNED_AT + 300])
def test_webhook_is_acknowledged(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    forward_webhook_mock: Mock,
    received_at: int,
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: received_at)
    log_context_mock = Mock()
    monkeypatch.setattr("dpw_vmi_adapter.api.set_webhook_request_id", log_context_mock)
    with caplog.at_level(logging.INFO, logger="dpw_vmi_adapter.api"):
        response = client.post(
            WEBHOOK_URL, data=BODY, content_type="application/json", headers=signed_headers()
        )

    assert response.status_code == 200
    assert response.content == b""
    assert "Content-Type" not in response.headers
    assert forward_webhook_mock.call_args.args == (BODY,)
    assert forward_webhook_mock.call_args.kwargs["timeout_seconds"] == 10
    assert forward_webhook_mock.call_args.kwargs["vmi_timestamp"] == str(SIGNED_AT)
    events = {record.__dict__.get("event.name"): record for record in caplog.records}
    assert "dpw_vmi.webhook.received" in events
    assert events["dpw_vmi.webhook.response_returned"].__dict__["http.response.status_code"] == 200
    generated_id = log_context_mock.call_args.args[0]
    assert str(UUID(generated_id)) == generated_id
    assert forward_webhook_mock.call_args.kwargs["webhook_request_id"] == generated_id
    assert "X-IVaaS-Webhook-Request-Id" not in response.headers


@pytest.mark.usefixtures("dpw_vmi_adapter")
def test_webhook_returns_program_response(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    forward_webhook_mock: Mock,
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT)
    forward_webhook_mock.return_value = ProgramResponse(
        422,
        b'{"error_code":"INVALID_REPORT"}',
        "application/problem+json",
    )
    response = client.post(
        WEBHOOK_URL,
        data=BODY,
        content_type="application/json",
        headers=signed_headers(),
    )

    assert response.status_code == 422
    assert response.content == b'{"error_code":"INVALID_REPORT"}'
    assert response.headers["Content-Type"] == "application/problem+json"
    assert forward_webhook_mock.call_args.kwargs["confirmation_code"] == "report-123"


@pytest.mark.usefixtures("dpw_vmi_adapter")
@pytest.mark.parametrize(
    "body",
    [
        b'{"event_type":"TransmissionComplete","confirmation_code":"report-123"}',
        b'{"report_metadata":{"confirmation_code":"report-123"}}',
    ],
)
def test_webhook_forwards_other_supported_event_shapes(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    forward_webhook_mock: Mock,
    body: bytes,
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT)

    response = client.post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        headers=signed_headers(body=body),
    )

    assert response.status_code == 200
    assert forward_webhook_mock.call_args.args == (body,)


@pytest.mark.usefixtures("dpw_vmi_adapter")
@pytest.mark.parametrize(
    "body",
    [
        b'{"event_type":"FutureEvent"}',
        b'{"event_type":"reportsubmission"}',
        b'{"event_type":null}',
        b'{"event_type":[]}',
    ],
)
def test_webhook_ignores_unsupported_event_type(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    forward_webhook_mock: Mock,
    body: bytes,
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT)

    with caplog.at_level(logging.WARNING, logger="dpw_vmi_adapter.api"):
        response = client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            headers=signed_headers(body=body),
        )

    assert response.status_code == 200
    assert response.content == b""
    assert "Content-Type" not in response.headers
    ignored = next(
        record
        for record in caplog.records
        if record.__dict__.get("event.name") == "dpw_vmi.webhook.unsupported_event_type"
    )
    assert ignored.__dict__["error.type"] == "unsupported_event_type"
    assert ignored.levelno == logging.WARNING
    forward_webhook_mock.assert_not_called()


@pytest.mark.usefixtures("dpw_vmi_adapter")
def test_webhook_rejects_json_that_exceeds_parser_depth(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    forward_webhook_mock: Mock,
) -> None:
    body = b"{}"
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT)

    with monkeypatch.context() as parser:
        parser.setattr("dpw_vmi_adapter.api.json.loads", Mock(side_effect=RecursionError))
        response = client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            headers=signed_headers(body=body),
        )

    assert response.status_code == 400
    assert response.json()["errors"] == [{"field": "body", "reason": "Must be valid JSON."}]
    forward_webhook_mock.assert_not_called()


@pytest.mark.usefixtures("dpw_vmi_adapter")
@pytest.mark.parametrize(
    ("body", "header_code", "field", "reason"),
    [
        (b"{", "report-123", "body", "Must be valid JSON."),
        (b"not-json", "report-123", "body", "Must be valid JSON."),
        (b"\xff", "report-123", "body", "Must be valid JSON."),
        (
            b'{"report_metadata":{"confirmation_code":"report-123"},"value":NaN}',
            "report-123",
            "body",
            "Must be valid JSON.",
        ),
        (b"[]", "report-123", "body", "Must be a JSON object."),
        (b"{}", "report-123", "report_metadata", "Must be a JSON object."),
        (b'{"report_metadata":[]}', "report-123", "report_metadata", "Must be a JSON object."),
        (
            b'{"report_metadata":{}}',
            "report-123",
            "report_metadata.confirmation_code",
            "Must be a non-empty string.",
        ),
        (
            b'{"report_metadata":{"confirmation_code":123}}',
            "report-123",
            "report_metadata.confirmation_code",
            "Must be a non-empty string.",
        ),
        (
            b'{"event_type":"TransmissionComplete"}',
            "report-123",
            "confirmation_code",
            "Must be a non-empty string.",
        ),
        (
            b'{"event_type":"TransmissionComplete","confirmation_code":"report-123"}',
            "different",
            "confirmation_code",
            "Must match X-VMI-Confirmation-Code.",
        ),
        (
            b'{"report_metadata":{"confirmation_code":"report-123"}}',
            "different",
            "report_metadata.confirmation_code",
            "Must match X-VMI-Confirmation-Code.",
        ),
    ],
)
def test_invalid_body_returns_field_error(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    forward_webhook_mock: Mock,
    body: bytes,
    header_code: str | None,
    field: str,
    reason: str,
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT)
    response = client.post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        headers=signed_headers(body=body, confirmation_code=header_code),
    )

    assert response.status_code == 400
    assert response.json() == {
        "error_code": "VALIDATION_ERROR",
        "message": "The request body failed validation.",
        "errors": [{"field": field, "reason": reason}],
    }
    failure = next(
        record
        for record in caplog.records
        if record.__dict__.get("event.name") == "dpw_vmi.webhook.body_validation_failed"
    )
    log = json.loads(JsonLogFormatter().format(failure))
    assert log["level"] == "ERROR"
    assert log["event.name"] == "dpw_vmi.webhook.body_validation_failed"
    assert log["http.response.status_code"] == 400
    assert field in log["message"]
    assert reason in log["message"]
    assert "report-123" not in log["message"]
    forward_webhook_mock.assert_not_called()


@pytest.mark.usefixtures("dpw_vmi_adapter")
@pytest.mark.parametrize(
    ("headers", "detail", "reason"),
    [
        ({"X-VMI-Signature": "a" * 128}, "Missing X-VMI-Timestamp", "missing_timestamp"),
        (signed_headers(timestamp="not-seconds"), "must be Unix seconds", "invalid_timestamp"),
        (signed_headers(timestamp="9" * 21), "must be Unix seconds", "invalid_timestamp"),
        ({"X-VMI-Timestamp": str(SIGNED_AT)}, "Missing X-VMI-Signature", "missing_signature"),
        (
            signed_headers(confirmation_code=None),
            "Missing X-VMI-Confirmation-Code",
            "missing_confirmation_code",
        ),
        (
            {**signed_headers(), "X-VMI-Signature": "invalid"},
            "128 lowercase hex characters",
            "invalid_signature",
        ),
        (signed_headers(body=b"different"), "does not match", "signature_mismatch"),
        (signed_headers(key="wrong-key"), "does not match", "signature_mismatch"),
        (signed_headers(timestamp=str(SIGNED_AT + 6)), "in the future", "future_timestamp"),
        (signed_headers(timestamp=str(SIGNED_AT - 301)), "too old", "expired_timestamp"),
    ],
)
def test_webhook_rejects_invalid_headers(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    headers: dict[str, str],
    detail: str,
    reason: str,
    forward_webhook_mock: Mock,
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT)

    with caplog.at_level(logging.WARNING, logger="dpw_vmi_adapter.security"):
        response = client.post(
            WEBHOOK_URL, data=BODY, content_type="application/json", headers=headers
        )

    assert response.status_code == 401
    assert response.json() == AUTHENTICATION_ERROR
    failure = next(record for record in caplog.records if record.name == "dpw_vmi_adapter.security")
    assert failure.levelno == logging.ERROR
    assert failure.__dict__["auth.failure.reason"] == reason
    assert detail in failure.getMessage()
    assert BODY.decode() not in failure.getMessage()
    assert WEBHOOK_KEY not in failure.getMessage()
    forward_webhook_mock.assert_not_called()


@pytest.mark.usefixtures("dpw_vmi_adapter")
def test_webhook_signature_covers_exact_body_bytes(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    forward_webhook_mock: Mock,
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT)
    response = client.post(
        WEBHOOK_URL,
        data=b'{ "event_type": "ReportSubmission" }',
        content_type="application/json",
        headers=signed_headers(),
    )

    assert response.status_code == 401
    assert response.json() == AUTHENTICATION_ERROR
    forward_webhook_mock.assert_not_called()


@pytest.mark.usefixtures("dpw_vmi_adapter")
def test_webhook_timestamp_window_is_configurable(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT + 301)
    with (
        override_settings(
            WEBHOOK_ADAPTERS={
                "dpw_vmi_adapter": {
                    "enabled": True,
                    "config": {
                        "webhook_path": WEBHOOK_PATH,
                        "webhook_api_key": WEBHOOK_KEY,
                        "webhook_timestamp_max_age_seconds": 600,
                        "program_timeout_seconds": 10,
                    },
                }
            }
        ),
        override_settings(INSTALLED_APPS=settings.INSTALLED_APPS),
    ):
        response = client.post(
            WEBHOOK_URL, data=BODY, content_type="application/json", headers=signed_headers()
        )

    assert response.status_code == 200
