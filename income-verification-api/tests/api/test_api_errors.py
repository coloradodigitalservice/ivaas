import json
import logging
from io import StringIO
from typing import Any

import pytest
from pydantic import BaseModel, field_validator
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import PydanticCustomError

from income_verification.api_error_codes import ErrorCode
from income_verification.api_errors import (
    _code_for_validation_error,
    _code_for_validation_errors,
    _sanitized_validation_errors,
)
from income_verification.request_context import JsonLogFormatter

CUSTOM_ERROR_TYPE_SENTINEL = "SENTINEL-PII-CUSTOM-ERROR-TYPE-90210"


class CustomErrorSchema(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def reject_value(cls, value: str) -> str:
        raise PydanticCustomError(
            CUSTOM_ERROR_TYPE_SENTINEL,
            "Rejected sentinel value: {value}",
            {"value": value},
        )


@pytest.mark.parametrize(
    ("location", "error_type", "expected"),
    [
        (("body", "payload", "ssn"), "string_pattern_mismatch", ErrorCode.INVALID_SSN_FORMAT),
        (
            ("body", "payload", "last4_ssn"),
            "string_pattern_mismatch",
            ErrorCode.INVALID_LAST4_SSN_FORMAT,
        ),
        (("body", "payload", "first_name"), "string_too_long", ErrorCode.INVALID_FIRST_NAME),
        (("body", "payload", "lastName"), "missing", ErrorCode.INVALID_LAST_NAME),
        (
            ("header", "Correlation-Id"),
            "string_pattern_mismatch",
            ErrorCode.INVALID_CORRELATION_ID,
        ),
        (("header", "correlation_id"), "string_too_long", ErrorCode.INVALID_CORRELATION_ID),
        (("header", "Correlation-Id"), "missing", None),
        (("body", "payload", "unknown"), "string_type", None),
    ],
)
def test_generic_validation_errors_map_to_owned_error_codes(
    location: tuple[str, ...],
    error_type: str,
    expected: ErrorCode | None,
) -> None:
    error: dict[str, Any] = {"loc": location, "type": error_type}

    assert _code_for_validation_error(error) == expected


def test_custom_validation_error_uses_error_code_directly() -> None:
    error = {
        "loc": ("body", "payload"),
        "type": ErrorCode.MISSING_IDENTITY_IDENTIFIER.value,
    }

    assert _code_for_validation_error(error) is ErrorCode.MISSING_IDENTITY_IDENTIFIER


def test_multiple_validation_errors_use_invalid_request_fallback() -> None:
    errors = [
        {"loc": ("body", "payload", "firstName"), "type": "missing"},
        {"loc": ("body", "payload", "lastName"), "type": "missing"},
    ]

    assert _code_for_validation_errors(errors) is ErrorCode.INVALID_REQUEST


def test_validation_log_metadata_discards_untrusted_error_details() -> None:
    sentinel = "SENTINEL-UNTRUSTED-VALIDATION-DATA"
    errors = [
        {
            "loc": ("body", "payload", sentinel),
            "type": sentinel,
            "msg": sentinel,
            "input": {"ssn": sentinel},
            "ctx": {"error": ValueError(sentinel)},
        }
    ]

    sanitized = _sanitized_validation_errors(errors)

    assert sanitized == [{"field": "request", "reason": "invalid"}]
    assert sentinel not in repr(sanitized)


def test_custom_error_type_cannot_reach_serialized_logs() -> None:
    input_sentinel = "SENTINEL-PII-CUSTOM-ERROR-INPUT-02139"
    with pytest.raises(PydanticValidationError) as caught:
        CustomErrorSchema(value=input_sentinel)

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("income_verification.custom_error_test")
    original_handlers = logger.handlers
    original_propagate = logger.propagate
    logger.handlers = [handler]
    logger.propagate = False
    try:
        logger.warning(
            "request rejected",
            extra={
                "validation_errors": _sanitized_validation_errors(caught.value.errors()),
            },
        )
    finally:
        logger.handlers = original_handlers
        logger.propagate = original_propagate

    serialized = stream.getvalue()
    assert json.loads(serialized)["validation.errors"] == [
        {"field": "request", "reason": "invalid"}
    ]
    assert CUSTOM_ERROR_TYPE_SENTINEL not in serialized
    assert input_sentinel not in serialized
