"""Stable error codes exposed by the IVaaS API."""

from enum import StrEnum
from dataclasses import dataclass


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"

    MISSING_IDENTITY_IDENTIFIER = "MISSING_IDENTITY_IDENTIFIER"
    MULTIPLE_IDENTITY_IDENTIFIERS = "MULTIPLE_IDENTITY_IDENTIFIERS"

    INVALID_SSN_FORMAT = "INVALID_SSN_FORMAT"
    INVALID_LAST4_SSN_FORMAT = "INVALID_LAST4_SSN_FORMAT"

    INVALID_FIRST_NAME = "INVALID_FIRST_NAME"
    INVALID_LAST_NAME = "INVALID_LAST_NAME"

    INVALID_CORRELATION_ID = "INVALID_CORRELATION_ID"
    INVALID_APPLICATION_ID = "INVALID_APPLICATION_ID"
    INVALID_LOOKBACK_PERIOD = "INVALID_LOOKBACK_PERIOD"


@dataclass(frozen=True, slots=True)
class ErrorDefinition:
    message: str
    status_code: int
    field: str | None = None


ERRORS: dict[ErrorCode, ErrorDefinition] = {
    # Blanket validation errors we can't or haven't yet been able to categorize more specifically .
    ErrorCode.INVALID_REQUEST: ErrorDefinition(
        status_code=400,
        message="Request failed validation.",
    ),
    ErrorCode.MISSING_IDENTITY_IDENTIFIER: ErrorDefinition(
        status_code=400,
        message="Either ssn or last4Ssn must be provided.",
    ),
    ErrorCode.MULTIPLE_IDENTITY_IDENTIFIERS: ErrorDefinition(
        status_code=400,
        message="Only one of ssn or last4Ssn may be provided.",
    ),
    ErrorCode.INVALID_SSN_FORMAT: ErrorDefinition(
        status_code=400,
        message="ssn must contain nine digits.",
        field="ssn",
    ),
    ErrorCode.INVALID_LAST4_SSN_FORMAT: ErrorDefinition(
        status_code=400,
        message="last4Ssn must contain four digits.",
        field="last4Ssn",
    ),
    ErrorCode.INVALID_CORRELATION_ID: ErrorDefinition(
        status_code=400,
        message="Correlation-Id is invalid.",
        field="Correlation-Id",
    ),
    ErrorCode.INVALID_APPLICATION_ID: ErrorDefinition(
        status_code=400,
        message="applicationId is invalid.",
        field="applicationId",
    ),
    ErrorCode.INVALID_FIRST_NAME: ErrorDefinition(
        status_code=400,
        message="firstName is invalid.",
        field="firstName",
    ),
    ErrorCode.INVALID_LAST_NAME: ErrorDefinition(
        status_code=400,
        message="lastName is invalid.",
        field="lastName",
    ),
    ErrorCode.INVALID_LOOKBACK_PERIOD: ErrorDefinition(
        status_code=400,
        message="lookbackPeriod is invalid.",
        field="lookbackPeriod",
    ),
}

FIELD_ERROR_CODES = {
    error.field: code
    for code, error in ERRORS.items()
    if error.field is not None
}
