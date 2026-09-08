from http import HTTPStatus
from typing import Any, cast

import pytest

from income_verification.api_error_codes import (
    ERRORS,
    FIELD_ERROR_CODES,
    ErrorCode,
    ErrorDefinition,
    RequestValidationErrorDefinition,
)


def test_general_error_definition_requires_an_explicit_status() -> None:
    constructor = cast(Any, ErrorDefinition)

    with pytest.raises(TypeError):
        constructor(message="Authentication failed.")

    definition = ErrorDefinition(
        message="Authentication failed.",
        status_code=HTTPStatus.UNAUTHORIZED,
    )

    assert definition.status_code is HTTPStatus.UNAUTHORIZED


def test_request_validation_status_cannot_be_overridden() -> None:
    constructor = cast(Any, RequestValidationErrorDefinition)

    with pytest.raises(TypeError):
        constructor(
            message="Request failed validation.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )


def test_request_validation_errors_use_the_locked_bad_request_definition() -> None:
    validation_errors = {
        code: definition
        for code, definition in ERRORS.items()
        if code is not ErrorCode.INTERNAL_ERROR
    }

    assert all(
        isinstance(definition, RequestValidationErrorDefinition)
        for definition in validation_errors.values()
    )
    assert {definition.status_code for definition in validation_errors.values()} == {
        HTTPStatus.BAD_REQUEST
    }


def test_internal_error_has_an_explicit_server_error_definition() -> None:
    definition = ERRORS[ErrorCode.INTERNAL_ERROR]

    assert type(definition) is ErrorDefinition
    assert definition.status_code is HTTPStatus.INTERNAL_SERVER_ERROR
    assert definition.message == "An internal server error occurred."


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
