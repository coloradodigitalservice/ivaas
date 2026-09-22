from http import HTTPStatus

import pytest

from income_verification.api_error_codes import (
    ERRORS,
    FIELD_ERROR_CODES,
    ErrorCode,
    ErrorDefinition,
    RequestValidationErrorDefinition,
)


def test_request_validation_errors_use_the_locked_bad_request_definition() -> None:
    validation_errors = {
        code: definition
        for code, definition in ERRORS.items()
        if isinstance(definition, RequestValidationErrorDefinition)
    }

    assert all(
        isinstance(definition, RequestValidationErrorDefinition)
        for definition in validation_errors.values()
    )
    assert {definition.status_code for definition in validation_errors.values()} == {
        HTTPStatus.BAD_REQUEST
    }


@pytest.mark.parametrize(
    ("code", "status", "message"),
    [
        (
            ErrorCode.AUTHENTICATION_REQUIRED,
            HTTPStatus.UNAUTHORIZED,
            "A Bearer access token is required.",
        ),
        (
            ErrorCode.ACCESS_TOKEN_EXPIRED,
            HTTPStatus.UNAUTHORIZED,
            "The Bearer access token has expired.",
        ),
        (
            ErrorCode.INVALID_AUTHENTICATION,
            HTTPStatus.UNAUTHORIZED,
            "The supplied authentication credentials are invalid.",
        ),
        (
            ErrorCode.FORBIDDEN,
            HTTPStatus.FORBIDDEN,
            "The authenticated client is not authorized to perform this request.",
        ),
        (
            ErrorCode.INTERNAL_ERROR,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "An internal server error occurred.",
        ),
        (
            ErrorCode.SERVICE_UNAVAILABLE,
            HTTPStatus.SERVICE_UNAVAILABLE,
            "The service is temporarily unavailable.",
        ),
    ],
)
def test_api_level_errors_have_explicit_general_definitions(
    code: ErrorCode,
    status: HTTPStatus,
    message: str,
) -> None:
    definition = ERRORS[code]

    assert type(definition) is ErrorDefinition
    assert definition.status_code is status
    assert definition.message == message


def test_field_error_codes_are_derived_from_error_definitions() -> None:
    expected = {
        definition.field: code
        for code, definition in ERRORS.items()
        if isinstance(definition, RequestValidationErrorDefinition) and definition.field is not None
    }

    assert expected == FIELD_ERROR_CODES
    assert all(
        isinstance(ERRORS[code], RequestValidationErrorDefinition)
        for code in FIELD_ERROR_CODES.values()
    )
    assert FIELD_ERROR_CODES["ssn"] is ErrorCode.INVALID_SSN_FORMAT
