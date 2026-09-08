"""Exception handling for the program-facing IVaaS API."""

import logging
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import HttpError, ValidationError

from income_verification.api_error_codes import ERRORS, FIELD_ERROR_CODES, ErrorCode
from income_verification.correlation_id import CORRELATION_ID_HEADER_NAME
from income_verification.request_context import get_correlation_id

logger = logging.getLogger(__name__)

MAX_LOGGED_VALIDATION_ERRORS = 5


class ValidationReason(StrEnum):
    """
    IVaaS-owned vocabulary for validation telemetry. Ensures that a cusom pydantic validation
    error won't accidentally leak sensitive information.
    """

    MISSING = "missing"
    INVALID = "invalid"


def _validation_reason(error_type: object) -> ValidationReason:
    """Translate a framework validation type to a stable IVaaS reason."""
    if error_type == "missing" or error_type == ErrorCode.MISSING_IDENTITY_IDENTIFIER.value:
        return ValidationReason.MISSING
    return ValidationReason.INVALID


def _sanitized_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Return validation metadata that is safe to include in application logs."""
    sanitized_errors: list[dict[str, str]] = []
    for error in errors[:MAX_LOGGED_VALIDATION_ERRORS]:
        location = error.get("loc", ())
        field = _field_for_location(location) if isinstance(location, (tuple, list)) else None
        sanitized_errors.append(
            {
                "field": field or "request",
                "reason": _validation_reason(error.get("type")).value,
            }
        )
    return sanitized_errors


def _normalized_field_name(value: object) -> str:
    """Normalize Python, JSON, and HTTP spellings for field matching."""
    return "".join(character.lower() for character in str(value) if character.isalnum())


def _field_for_location(location: tuple[object, ...] | list[object]) -> str | None:
    """Return an allowlisted public field name for a validation location."""
    fields_by_normalized_name = {
        _normalized_field_name(field): field for field in FIELD_ERROR_CODES
    }
    for part in reversed(location):
        if field := fields_by_normalized_name.get(_normalized_field_name(part)):
            return field
    return None


def _code_for_validation_error(
    error: dict[str, Any],
) -> ErrorCode | None:
    """Translate one Ninja/Pydantic validation error to an IVaaS error code."""
    error_type = str(error.get("type", ""))

    # Custom validators emit stable IVaaS error codes directly.
    try:
        return ErrorCode(error_type)
    except ValueError:
        pass

    # Generic Pydantic validation errors are mapped using their field location.
    location = error.get("loc", ())
    if not isinstance(location, (tuple, list)):
        return None

    field = _field_for_location(location)
    if field is None:
        return None

    code = FIELD_ERROR_CODES[field]
    if code is ErrorCode.INVALID_CORRELATION_ID and error_type == "missing":
        # A required header that was not sent is a generic incomplete request.
        # INVALID_CORRELATION_ID is reserved for a supplied malformed value.
        return None
    return code


def _code_for_validation_errors(
    errors: list[dict[str, Any]],
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
    validation_errors: list[dict[str, Any]] | None = None,
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

    attributes: dict[str, object] = {
        "event_name": "income_verification.request.rejected",
        "error_type": error_type,
        "error_code": code.value,
        "http_request_method": request.method or "UNKNOWN",
        "http_response_status_code": definition.status_code,
        "url_path": request.path,
    }

    if validation_errors is not None:
        attributes["validation_error_count"] = len(validation_errors)
        attributes["validation_errors"] = _sanitized_validation_errors(validation_errors)

    logger.warning(
        "income verification request rejected",
        extra=attributes,
    )

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
        if exc.status_code == 400:
            return _error_response(
                api,
                request,
                ErrorCode.INVALID_REQUEST,
                error_type="bad_request",
            )

        logger.warning(
            "API request failed",
            extra={
                "event_name": "api.request.failed",
                "error_type": "http_error",
                "http_request_method": request.method or "UNKNOWN",
                "http_response_status_code": exc.status_code,
                "url_path": request.path,
            },
        )

        return api.create_response(
            request,
            {"detail": exc.message},
            status=exc.status_code,
        )
