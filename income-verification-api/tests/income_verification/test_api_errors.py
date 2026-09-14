import json
import logging
from collections.abc import Iterator
from http import HTTPStatus
from io import StringIO
from typing import Any

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.errors import ValidationError as NinjaValidationError
from pydantic import BaseModel, field_validator
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import PydanticCustomError

from income_verification.api_error_codes import ERRORS, ErrorCode
from income_verification.api_errors import register_exception_handlers
from income_verification.request_context import (
    JsonLogFormatter,
    RequestContextFilter,
    RequestContextMiddleware,
)

CUSTOM_ERROR_TYPE_SENTINEL = "SENTINEL-PII-CUSTOM-ERROR-TYPE-90210"
INTERNAL_VALIDATOR_SENTINEL = "PII_SENTINEL_INTERNAL_VALIDATOR_123456789"
CORRELATION_ID = "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31:error-test"
ERROR_PATH = "/api/v1/income-verification"


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


class InternalErrorCodeSchema(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def reject_value(cls, value: str) -> str:
        raise PydanticCustomError(
            ErrorCode.INTERNAL_ERROR.value,
            INTERNAL_VALIDATOR_SENTINEL,
            {"value": value},
        )


@pytest.fixture
def captured_api_error_logs() -> Iterator[StringIO]:
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


def _dispatch_exception(exc: Exception) -> HttpResponse:
    api = NinjaAPI()
    register_exception_handlers(api)
    request = RequestFactory().get(
        ERROR_PATH,
        headers={"Correlation-Id": CORRELATION_ID},
    )

    def get_response(current_request: HttpRequest) -> HttpResponse:
        return api.on_exception(current_request, exc)

    response = RequestContextMiddleware(get_response)(request)
    assert isinstance(response, HttpResponse)
    return response


def _dispatch_validation_errors(errors: list[dict[str, Any]]) -> HttpResponse:
    """Drive validation errors through the registered handler as Ninja would."""
    return _dispatch_exception(NinjaValidationError(errors))


def test_json_formatter_discards_exception_text_and_raw_stack_info(
    captured_api_error_logs: StringIO,
) -> None:
    sentinel = "PII_SENTINEL_SSN_123456789"
    logger = logging.getLogger("income_verification.exception_formatter_test")

    try:
        raise ValueError(sentinel)
    except ValueError:
        logger.error(
            "safe application error",
            exc_info=True,
            stack_info=True,
        )

    serialized = captured_api_error_logs.getvalue()
    record = json.loads(serialized)
    assert record["exception.type"] == "ValueError"
    assert "stack" not in record
    assert "Traceback" not in serialized
    assert sentinel not in serialized


def test_unexpected_exception_returns_and_logs_controlled_internal_error(
    captured_api_error_logs: StringIO,
) -> None:
    sentinel = "PII_SENTINEL_UNEXPECTED_EXCEPTION_MESSAGE"

    response = _dispatch_exception(ValueError(sentinel))

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert json.loads(response.content) == {
        "code": ErrorCode.INTERNAL_ERROR,
        "message": ERRORS[ErrorCode.INTERNAL_ERROR].message,
    }
    assert response.headers["Correlation-Id"] == CORRELATION_ID
    serialized = captured_api_error_logs.getvalue()
    record = json.loads(serialized)
    assert record["level"] == "ERROR"
    assert record["event.name"] == "income_verification.request.failed"
    assert record["error.code"] == ErrorCode.INTERNAL_ERROR
    assert record["error.type"] == "internal_error"
    assert record["exception.type"] == "ValueError"
    assert record["http.request.method"] == "GET"
    assert record["http.response.status_code"] == HTTPStatus.INTERNAL_SERVER_ERROR
    assert record["url.path"] == ERROR_PATH
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert sentinel not in response.content.decode()
    assert sentinel not in serialized


@pytest.mark.parametrize(
    ("framework_status", "expected_code", "expected_level"),
    [
        (HTTPStatus.BAD_REQUEST, ErrorCode.INVALID_REQUEST, "WARNING"),
        (HTTPStatus.UNAUTHORIZED, ErrorCode.UNAUTHORIZED, "WARNING"),
        (HTTPStatus.FORBIDDEN, ErrorCode.FORBIDDEN, "WARNING"),
        (HTTPStatus.INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL_ERROR, "ERROR"),
        (HTTPStatus.SERVICE_UNAVAILABLE, ErrorCode.SERVICE_UNAVAILABLE, "ERROR"),
        (HTTPStatus.IM_A_TEAPOT, ErrorCode.INTERNAL_ERROR, "ERROR"),
    ],
)
def test_http_errors_use_the_stable_error_contract(
    captured_api_error_logs: StringIO,
    framework_status: HTTPStatus,
    expected_code: ErrorCode,
    expected_level: str,
) -> None:
    sentinel = f"PII_SENTINEL_HTTP_{framework_status}_MESSAGE"

    response = _dispatch_exception(HttpError(framework_status, sentinel))

    definition = ERRORS[expected_code]
    assert response.status_code == definition.status_code
    assert json.loads(response.content) == {
        "code": expected_code,
        "message": definition.message,
    }
    assert response.headers["Correlation-Id"] == CORRELATION_ID
    serialized = captured_api_error_logs.getvalue()
    record = json.loads(serialized)
    assert record["level"] == expected_level
    expected_event = (
        "income_verification.request.failed"
        if definition.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
        else "income_verification.request.rejected"
    )
    assert record["event.name"] == expected_event
    assert record["error.code"] == expected_code
    assert record["exception.type"] == "HttpError"
    assert record["http.response.status_code"] == definition.status_code
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert sentinel not in response.content.decode()
    assert sentinel not in serialized


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
    captured_api_error_logs: StringIO,
    location: tuple[str, ...],
    error_type: str,
    expected: ErrorCode | None,
) -> None:
    response = _dispatch_validation_errors([{"loc": location, "type": error_type}])

    expected_code = expected or ErrorCode.INVALID_REQUEST
    assert response.status_code == ERRORS[expected_code].status_code
    assert json.loads(response.content)["code"] == expected_code
    assert json.loads(captured_api_error_logs.getvalue())["error.code"] == expected_code


def test_custom_validation_error_uses_error_code_directly(
    captured_api_error_logs: StringIO,
) -> None:
    error = {
        "loc": ("body", "payload"),
        "type": ErrorCode.MISSING_IDENTITY_IDENTIFIER.value,
    }

    response = _dispatch_validation_errors([error])

    assert json.loads(response.content)["code"] == ErrorCode.MISSING_IDENTITY_IDENTIFIER
    assert (
        json.loads(captured_api_error_logs.getvalue())["error.code"]
        == ErrorCode.MISSING_IDENTITY_IDENTIFIER
    )


def test_non_validation_error_code_cannot_escape_validation_handler(
    captured_api_error_logs: StringIO,
) -> None:
    input_sentinel = "PII_SENTINEL_INTERNAL_VALIDATOR_INPUT"
    with pytest.raises(PydanticValidationError) as caught:
        InternalErrorCodeSchema(value=input_sentinel)

    ninja_errors = [dict(error) for error in caught.value.errors()]
    response = _dispatch_validation_errors(ninja_errors)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert json.loads(response.content) == {
        "code": ErrorCode.INVALID_REQUEST,
        "message": ERRORS[ErrorCode.INVALID_REQUEST].message,
    }
    serialized = captured_api_error_logs.getvalue()
    record = json.loads(serialized)
    assert record["error.code"] == ErrorCode.INVALID_REQUEST
    assert record["validation.errors"] == [{"field": "request", "reason": "invalid"}]
    assert INTERNAL_VALIDATOR_SENTINEL not in response.content.decode()
    assert input_sentinel not in response.content.decode()
    assert INTERNAL_VALIDATOR_SENTINEL not in serialized
    assert input_sentinel not in serialized


def test_multiple_validation_errors_use_invalid_request_fallback(
    captured_api_error_logs: StringIO,
) -> None:
    errors = [
        {"loc": ("body", "payload", "firstName"), "type": "missing"},
        {"loc": ("body", "payload", "lastName"), "type": "missing"},
    ]

    response = _dispatch_validation_errors(errors)

    assert json.loads(response.content)["code"] == ErrorCode.INVALID_REQUEST
    assert json.loads(captured_api_error_logs.getvalue())["error.code"] == ErrorCode.INVALID_REQUEST


def test_validation_log_metadata_discards_untrusted_error_details(
    captured_api_error_logs: StringIO,
) -> None:
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

    _dispatch_validation_errors(errors)

    serialized = captured_api_error_logs.getvalue()
    assert json.loads(serialized)["validation.errors"] == [
        {"field": "request", "reason": "invalid"}
    ]
    assert sentinel not in serialized


def test_custom_error_type_cannot_reach_serialized_logs(
    captured_api_error_logs: StringIO,
) -> None:
    input_sentinel = "SENTINEL-PII-CUSTOM-ERROR-INPUT-02139"
    with pytest.raises(PydanticValidationError) as caught:
        CustomErrorSchema(value=input_sentinel)

    _dispatch_validation_errors([dict(error) for error in caught.value.errors()])

    serialized = captured_api_error_logs.getvalue()
    assert json.loads(serialized)["validation.errors"] == [
        {"field": "request", "reason": "invalid"}
    ]
    assert CUSTOM_ERROR_TYPE_SENTINEL not in serialized
    assert input_sentinel not in serialized
