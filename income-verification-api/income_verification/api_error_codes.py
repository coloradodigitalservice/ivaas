"""Stable error codes exposed by the IVaaS API."""

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum
from http import HTTPStatus


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"

    MISSING_IDENTITY_IDENTIFIER = "MISSING_IDENTITY_IDENTIFIER"
    MULTIPLE_IDENTITY_IDENTIFIERS = "MULTIPLE_IDENTITY_IDENTIFIERS"

    INVALID_SSN_FORMAT = "INVALID_SSN_FORMAT"
    INVALID_LAST4_SSN_FORMAT = "INVALID_LAST4_SSN_FORMAT"

    INVALID_FIRST_NAME = "INVALID_FIRST_NAME"
    INVALID_LAST_NAME = "INVALID_LAST_NAME"

    MISSING_CORRELATION_ID = "MISSING_CORRELATION_ID"
    INVALID_CORRELATION_ID = "INVALID_CORRELATION_ID"
    INVALID_APPLICATION_ID = "INVALID_APPLICATION_ID"
    INVALID_LOOKBACK_PERIOD = "INVALID_LOOKBACK_PERIOD"

    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    ACCESS_TOKEN_EXPIRED = "ACCESS_TOKEN_EXPIRED"  # noqa: S105 - API code, not a token
    INVALID_AUTHENTICATION = "INVALID_AUTHENTICATION"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


@dataclass(frozen=True, slots=True, kw_only=True)
class ErrorDefinition:
    message: str
    status_code: HTTPStatus
    field: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestValidationErrorDefinition(ErrorDefinition):
    status_code: HTTPStatus = dataclass_field(
        default=HTTPStatus.BAD_REQUEST,
        init=False,  # This ensures the status_code cannot be overridden during initialization
    )


ERRORS: dict[ErrorCode, ErrorDefinition] = {
    # Blanket validation errors that cannot be categorized more specifically.
    ErrorCode.INVALID_REQUEST: RequestValidationErrorDefinition(
        message="Request failed validation.",
    ),
    ErrorCode.MISSING_IDENTITY_IDENTIFIER: RequestValidationErrorDefinition(
        message="Either ssn or last4Ssn must be provided.",
    ),
    ErrorCode.MULTIPLE_IDENTITY_IDENTIFIERS: RequestValidationErrorDefinition(
        message="Only one of ssn or last4Ssn may be provided.",
    ),
    ErrorCode.INVALID_SSN_FORMAT: RequestValidationErrorDefinition(
        message="ssn must contain nine digits.",
        field="ssn",
    ),
    ErrorCode.INVALID_LAST4_SSN_FORMAT: RequestValidationErrorDefinition(
        message="last4Ssn must contain four digits.",
        field="last4Ssn",
    ),
    ErrorCode.MISSING_CORRELATION_ID: RequestValidationErrorDefinition(
        message="Correlation-Id header is required.",
    ),
    ErrorCode.INVALID_CORRELATION_ID: RequestValidationErrorDefinition(
        message="Correlation-Id is invalid.",
        field="Correlation-Id",
    ),
    ErrorCode.INVALID_APPLICATION_ID: RequestValidationErrorDefinition(
        message="applicationId is invalid.",
        field="applicationId",
    ),
    ErrorCode.INVALID_FIRST_NAME: RequestValidationErrorDefinition(
        message="firstName is invalid.",
        field="firstName",
    ),
    ErrorCode.INVALID_LAST_NAME: RequestValidationErrorDefinition(
        message="lastName is invalid.",
        field="lastName",
    ),
    ErrorCode.INVALID_LOOKBACK_PERIOD: RequestValidationErrorDefinition(
        message="lookbackPeriod is invalid.",
        field="lookbackPeriod",
    ),
    ErrorCode.INTERNAL_ERROR: ErrorDefinition(
        message="An internal server error occurred.",
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
    ),
    ErrorCode.AUTHENTICATION_REQUIRED: ErrorDefinition(
        message="A Bearer access token is required.",
        status_code=HTTPStatus.UNAUTHORIZED,
    ),
    ErrorCode.ACCESS_TOKEN_EXPIRED: ErrorDefinition(
        message="The Bearer access token has expired.",
        status_code=HTTPStatus.UNAUTHORIZED,
    ),
    ErrorCode.INVALID_AUTHENTICATION: ErrorDefinition(
        message="The supplied authentication credentials are invalid.",
        status_code=HTTPStatus.UNAUTHORIZED,
    ),
    ErrorCode.UNAUTHORIZED: ErrorDefinition(
        message="Authentication is required.",
        status_code=HTTPStatus.UNAUTHORIZED,
    ),
    ErrorCode.FORBIDDEN: ErrorDefinition(
        message="The authenticated client is not authorized to perform this request.",
        status_code=HTTPStatus.FORBIDDEN,
    ),
    ErrorCode.SERVICE_UNAVAILABLE: ErrorDefinition(
        message="The service is temporarily unavailable.",
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
    ),
}

FIELD_ERROR_CODES: dict[str, ErrorCode] = {
    definition.field: code
    for code, definition in ERRORS.items()
    if isinstance(definition, RequestValidationErrorDefinition) and definition.field is not None
}
