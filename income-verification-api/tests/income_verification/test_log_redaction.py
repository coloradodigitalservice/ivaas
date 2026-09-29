import json
import logging
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel

from income_verification.request_context import JsonLogFormatter, LogField
from income_verification.schemas import VerificationRequest


def _record(message: object, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        "adapter_engine.test", logging.WARNING, __file__, 1, message, args, None
    )


@pytest.mark.parametrize(
    ("message", "args", "expected"),
    [
        (
            "adapter %r attempt %d of %d failed: %s: %s",
            ("stub", 1, 3, "SourceTimeout", RuntimeError("Source lookup timed out after 3s")),
            "adapter 'stub' attempt 1 of 3 failed: SourceTimeout: Source lookup timed out after 3s",
        ),
        (
            "failure: %r",
            (RuntimeError("Source returned HTTP 422"),),
            "failure: RuntimeError('Source returned HTTP 422')",
        ),
        ("SSN %s%s%s", ("123", "45", "6789"), "SSN [REDACTED]"),
        ("SSN %09d", (123456789,), "SSN [REDACTED]"),
        ("SSN %s", ("123456789",), "SSN [REDACTED]"),
        ("SSN %s", ("123-45-6789",), "SSN [REDACTED]"),
        (
            "failure: %s",
            (RuntimeError("lookup failed for SSN 123-45-6789"),),
            "failure: lookup failed for SSN [REDACTED]",
        ),
        ("contact %s", ("user@example.com",), "contact [REDACTED]"),
        ("Authorization: %s", ("Bearer synthetic-token",), "Authorization: [REDACTED]"),
        ("phone %s", ("+1 415-555-2671",), "phone [REDACTED]"),
        ("token %s", ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature",), "token [REDACTED]"),
        ("password=synthetic-secret", (), "[REDACTED]"),
    ],
)
def test_redacts_final_message_and_preserves_safe_diagnostics(
    message: str, args: tuple[object, ...], expected: str
) -> None:
    record = _record(message, *args)

    assert json.loads(JsonLogFormatter().format(record))["message"] == expected
    assert record.msg == message
    assert record.args == args


@pytest.mark.parametrize("as_message", [False, True])
def test_redacts_nested_known_fields_without_mutating_input(as_message: bool) -> None:
    payload = {
        "subject": [
            {
                "first_name": "SensitiveGivenName",
                "LAST-NAME": "SensitiveFamilyName",
                "last4Ssn": "9876",
                "ssn": "123456789",
            }
        ],
        "raw_income": {"unknownVendorField": "SensitiveIncomeValue"},
        "password": "SensitivePassword",
        "status": "UNAVAILABLE",
    }
    record = _record(payload) if as_message else _record("payload: %s", payload)

    output = JsonLogFormatter().format(record)

    for value in (
        "SensitiveGivenName",
        "SensitiveFamilyName",
        "9876",
        "123456789",
        "SensitiveIncomeValue",
        "SensitivePassword",
    ):
        assert value not in output
    assert "UNAVAILABLE" in output
    assert "SensitiveGivenName" in str(payload)


def test_redacts_named_arguments_and_preserves_context() -> None:
    arguments = {"firstName": "SensitiveGivenName", "attempt": 2}
    record = _record("name %(firstName)s attempt %(attempt)d", arguments)
    correlation_id = "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31:APP-2026-004471"
    setattr(record, LogField.CORRELATION_ID.value, correlation_id)
    setattr(record, LogField.APPLICATION_ID.value, "APP-123456789")

    output = json.loads(JsonLogFormatter().format(record))

    assert output["message"] == "name [REDACTED] attempt 2"
    assert output[LogField.CORRELATION_ID.value] == correlation_id
    assert output[LogField.APPLICATION_ID.value] == "APP-123456789"
    assert arguments == {"firstName": "SensitiveGivenName", "attempt": 2}


@pytest.mark.parametrize(
    ("identity_key", "identity_value"), [("last4Ssn", "9876"), ("ssn", "123456789")]
)
def test_redacts_api_and_core_request_objects(identity_key: str, identity_value: str) -> None:
    request = VerificationRequest.model_validate(
        {
            "applicationId": "TEST-APPLICATION",
            "firstName": "SensitiveGivenName",
            "lastName": "SensitiveFamilyName",
            identity_key: identity_value,
            "lookbackPeriod": {"startDate": "2026-01-01", "endDate": "2026-06-30"},
        }
    )
    core_request = request.to_envelope("test-correlation", agency_id="test-agency").core_request

    for value in (request, core_request, {"envelope": [core_request]}):
        output = JsonLogFormatter().format(_record("request: %s", value))
        assert "SensitiveGivenName" not in output
        assert "SensitiveFamilyName" not in output
        assert identity_value not in output
        assert "[REDACTED]" in output


def test_response_fields_are_derived_from_schemas() -> None:
    metadata = {
        "verificationId": "test-verification",
        "sourceId": "test-source",
        "status": "OK",
        "retrievedAt": "2026-09-28T12:00:00Z",
    }
    payload = {
        **metadata,
        "rawIncome": {"unknownVendorField": "SensitiveIncomeValue"},
        "sources": [{"unknownVendorField": "SensitiveResponseValue"}],
        "lookbackPeriod": {"startDate": "SensitiveLookupValue"},
    }

    output = JsonLogFormatter().format(_record("result: %s", payload))

    for value in ("SensitiveIncomeValue", "SensitiveResponseValue", "SensitiveLookupValue"):
        assert value not in output
    for value in metadata.values():
        assert value in output


def test_unrecognized_model_fields_default_to_sensitive() -> None:
    @dataclass
    class AdapterResponse:
        newly_added_field: str
        status: str

    class ApiResponse(BaseModel):
        newly_added_field: str
        status: str

    for value in (
        AdapterResponse("SensitiveNewValue", "OK"),
        ApiResponse(newly_added_field="SensitiveNewValue", status="OK"),
    ):
        output = JsonLogFormatter().format(_record("result: %s", value))
        assert "SensitiveNewValue" not in output
        assert "OK" in output


def test_incompatible_sensitive_numeric_argument_fails_closed() -> None:
    output = JsonLogFormatter().format(_record("SSN %(ssn)d", {"ssn": 123456789}))

    assert "123456789" not in output
    assert json.loads(output)["message"] == "[REDACTED: log message could not be safely formatted]"


def test_redaction_failure_emits_no_original_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_redaction(*args: Any, **kwargs: Any) -> object:
        raise RuntimeError("SensitiveFailureDetail")

    monkeypatch.setattr("income_verification.log_redaction._TEXT_REDACTOR.redact", fail_redaction)
    record = _record("SensitiveOriginalMessage")

    output = json.loads(JsonLogFormatter().format(record))

    assert output["message"] == "[REDACTED: log message could not be safely formatted]"
    assert output["level"] == "WARNING"
    assert record.msg == "SensitiveOriginalMessage"


def test_cyclic_container_fails_closed() -> None:
    payload: dict[str, object] = {"firstName": "SensitiveGivenName"}
    payload["loop"] = payload

    output = JsonLogFormatter().format(_record("payload: %s", payload))

    assert "SensitiveGivenName" not in output
    assert json.loads(output)["message"] == "[REDACTED: log message could not be safely formatted]"
