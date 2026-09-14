"""Exception handling for the program-facing IVaaS API."""

import logging
from collections.abc import Mapping, Sequence
from enum import StrEnum
from http import HTTPStatus
from typing import Any

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import HttpError, ValidationError

from income_verification.api_error_codes import (
    ERRORS,
    FIELD_ERROR_CODES,
    ErrorCode,
    RequestValidationErrorDefinition,
)
from income_verification.correlation_id import CORRELATION_ID_HEADER_NAME
from income_verification.request_context import LogField, get_correlation_id

logger = logging.getLogger(__name__)

# Bound structured log volume while retaining the total error count.
MAX_LOGGED_VALIDATION_ERRORS = 5

_HTTP_ERROR_CODES: dict[int, ErrorCode] = {
    HTTPStatus.BAD_REQUEST: ErrorCode.INVALID_REQUEST,
    HTTPStatus.UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    HTTPStatus.FORBIDDEN: ErrorCode.FORBIDDEN,
    HTTPStatus.INTERNAL_SERVER_ERROR: ErrorCode.INTERNAL_ERROR,
    HTTPStatus.SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
}


class ValidationReason(StrEnum):
    """
    IVaaS-owned vocabulary for validation telemetry. Used to help ensure that a custom
    pydantic validation error won't accidentally leak sensitive information.
    """

    MISSING = "missing"
    INVALID = "invalid"


def _validation_reason(error_type: object) -> ValidationReason:
    """Translate a framework validation type to a stable IVaaS reason."""
    if isinstance(error_type, str) and (
        error_type == "missing" or error_type == ErrorCode.MISSING_IDENTITY_IDENTIFIER.value
    ):
        return ValidationReason.MISSING
    return ValidationReason.INVALID


def _sanitized_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Return validation metadata that is safe to include in application logs."""
    sanitized_errors: list[dict[str, str]] = []
    for error in errors[:MAX_LOGGED_VALIDATION_ERRORS]:
        location: tuple[int | str, ...] = error.get("loc", ())
        field = _field_for_location(location)
        sanitized_errors.append(
            {
                "field": field or "request",
                "reason": _validation_reason(error.get("type")).value,
            }
        )
    return sanitized_errors


def _normalized_field_name(value: str) -> str:
    """Normalize Python, JSON, and HTTP spellings for field matching."""
    return "".join(character.lower() for character in value if character.isalnum())


_NORMALIZED_FIELD_NAMES = {_normalized_field_name(field): field for field in FIELD_ERROR_CODES}


def _field_for_location(location: tuple[int | str, ...]) -> str | None:
    """Return an allowlisted public field name for a validation location."""
    for part in reversed(location):
        if not isinstance(part, str):
            continue
        if field := _NORMALIZED_FIELD_NAMES.get(_normalized_field_name(part)):
            return field
    return None


def _code_for_validation_error(
    error: Mapping[str, Any],
) -> ErrorCode | None:
    """Translate one Ninja/Pydantic validation error to an IVaaS error code."""
    raw_error_type = error.get("type")
    error_type = raw_error_type if isinstance(raw_error_type, str) else ""

    # Custom validators emit stable IVaaS error codes directly.
    try:
        explicit_code = ErrorCode(error_type)
    except ValueError:
        pass
    else:
        if isinstance(ERRORS[explicit_code], RequestValidationErrorDefinition):
            return explicit_code
        return None

    # Generic Pydantic validation errors are mapped using their field location.
    location: tuple[int | str, ...] = error.get("loc", ())
    field = _field_for_location(location)
    if field is None:
        return None

    code = FIELD_ERROR_CODES[field]
    if code is ErrorCode.INVALID_CORRELATION_ID and error_type == "missing":
        return ErrorCode.MISSING_CORRELATION_ID
    return code


def _code_for_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> ErrorCode:
    """Choose the public error code for a set of validation failures."""
    # A single response code cannot represent several independent failures safely.
    if len(errors) != 1:
        return ErrorCode.INVALID_REQUEST

    return _code_for_validation_error(errors[0]) or ErrorCode.INVALID_REQUEST


def _error_response(
    api: NinjaAPI,
    request: HttpRequest,
    code: ErrorCode,
    *,
    error_type: str,
    exception_type: str | None = None,
    validation_errors: Sequence[Mapping[str, Any]] | None = None,
) -> HttpResponse:
    """Create and safely log an IVaaS error response."""
    definition = ERRORS[code]

    response = api.create_response(
        request,
        {
            "code": code,
            "message": definition.message,
        },
        status=definition.status_code,
    )

    # Identify whether it was a client or server error
    is_internal_error = definition.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
    log_message = (
        "income verification request failed"
        if is_internal_error
        else "income verification request rejected"
    )

    # Build safe structured metadata
    attributes: dict[str, object] = {
        LogField.EVENT_NAME.value: (
            "income_verification.request.failed"
            if is_internal_error
            else "income_verification.request.rejected"
        ),
        LogField.ERROR_TYPE.value: error_type,
        LogField.ERROR_CODE.value: code.value,
        LogField.HTTP_REQUEST_METHOD.value: request.method or "UNKNOWN",
        LogField.HTTP_RESPONSE_STATUS_CODE.value: definition.status_code,
        LogField.URL_PATH.value: request.path,
    }

    if validation_errors is not None:
        attributes[LogField.VALIDATION_ERROR_COUNT.value] = len(validation_errors)
        attributes[LogField.VALIDATION_ERRORS.value] = _sanitized_validation_errors(
            validation_errors
        )
    if exception_type is not None:
        attributes[LogField.EXCEPTION_TYPE.value] = exception_type

    log_method = logger.error if is_internal_error else logger.warning
    log_method(log_message, extra=attributes)

    correlation_id = get_correlation_id()
    if correlation_id is not None:
        response[CORRELATION_ID_HEADER_NAME] = correlation_id

    return response


def register_exception_handlers(api: NinjaAPI) -> None:
    """Register IVaaS exception handling policy with the Ninja API."""

    @api.exception_handler(ValidationError)
    def validation_error(
        request: HttpRequest,
        exc: ValidationError,
    ) -> HttpResponse:
        # Determine the appropriate error code for the validation errors.
        code = _code_for_validation_errors(exc.errors)

        return _error_response(
            api,
            request,
            code,
            error_type="validation_error",
            validation_errors=exc.errors,
        )

    @api.exception_handler(HttpError)
    def http_error(
        request: HttpRequest,
        exc: HttpError,
    ) -> HttpResponse:
        code = _HTTP_ERROR_CODES.get(exc.status_code)
        if code is None:
            code = ErrorCode.INTERNAL_ERROR
            error_type = "unexpected_http_error"
        elif code is ErrorCode.INVALID_REQUEST:
            error_type = "bad_request"
        elif code is ErrorCode.INTERNAL_ERROR:
            error_type = "internal_error"
        else:
            error_type = "http_error"

        return _error_response(
            api,
            request,
            code,
            error_type=error_type,
            exception_type=type(exc).__name__,
        )

    @api.exception_handler(Exception)
    def unexpected_exception(
        request: HttpRequest,
        exc: Exception,
    ) -> HttpResponse:
        return _error_response(
            api,
            request,
            ErrorCode.INTERNAL_ERROR,
            error_type="internal_error",
            exception_type=type(exc).__name__,
        )
