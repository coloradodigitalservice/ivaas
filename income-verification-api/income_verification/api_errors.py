"""Exception handling for the program-facing IVaaS API."""

import logging
from typing import Any

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import HttpError, ValidationError
from pydantic.alias_generators import to_camel

from income_verification.correlation_id import CORRELATION_ID_HEADER_NAME
from income_verification.api_error_codes import ERRORS, ErrorCode
from income_verification.request_context import get_correlation_id

logger = logging.getLogger(__name__)

MAX_LOGGED_VALIDATION_ERRORS = 5


def _sanitized_validation_errors(
    errors: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Return validation metadata that is safe to include in application logs."""
    return [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "type": str(error.get("type", "unknown")),
        }
        for error in errors[:MAX_LOGGED_VALIDATION_ERRORS]
    ]


def _location_matches_field(
    location: tuple[object, ...] | list[object],
    field: str,
) -> bool:
    """Return whether a validation location refers to a public API field."""
    for part in location:
        part_name = str(part)

        if part_name == field:
            return True

        # Pydantic may report the Python field name rather than its API alias.
        if to_camel(part_name) == field:
            return True

    return False


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

    for code, definition in ERRORS.items():
        if definition.field is None:
            continue

        if _location_matches_field(location, definition.field):
            return code

    return None


def _code_for_validation_errors(
    errors: list[dict[str, Any]],
) -> ErrorCode:
    """Choose the public error code for a set of validation failures."""
    # If there is more than one validation error, we default to a generic invalid request code.
    # we could probably have more sophisticated logic here and use a code for multiple validation errors then return the list of codes
    # in the definition of the error response.
    if len(errors) != 1:
        return ErrorCode.INVALID_REQUEST

    # Otherwise, we have exactly one validation error, so we attempt to map it to a specific error code.
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
        attributes["validation_errors"] = _sanitized_validation_errors(
            validation_errors
        )

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
