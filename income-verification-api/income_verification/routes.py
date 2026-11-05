"""Version-neutral routes for the program-facing IVaaS API."""

import logging
from http import HTTPStatus
from typing import Annotated

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from ninja import Header, Router

from adapter_engine.engine import engine
from income_verification.api_error_codes import ERRORS
from income_verification.correlation_id import (
    CORRELATION_ID_HEADER_NAME,
    CORRELATION_ID_MAX_LENGTH,
    CORRELATION_ID_PATTERN,
)
from income_verification.request_context import LogField, set_verification_log_context
from income_verification.schemas import (
    Error,
    TestConnectionResponse,
    VerificationRequest,
    VerificationResponse,
)
from income_verification.security import (
    ProgramOAuth2ClientCredentials,
    get_api_authentication,
    get_authenticated_program,
)

logger = logging.getLogger(__name__)

# Tags here for the API documentation
router = Router(tags=["Income verification"])

CORRELATION_ID_RESPONSE_HEADER = {
    "description": "Echo of a valid request Correlation-Id header.",
    "required": True,
    "schema": {
        "type": "string",
        "maxLength": CORRELATION_ID_MAX_LENGTH,
        "pattern": CORRELATION_ID_PATTERN,
    },
}
# Error responses cannot echo an ID when the request omitted it or supplied a malformed one.
OPTIONAL_CORRELATION_ID_RESPONSE_HEADER = {
    **CORRELATION_ID_RESPONSE_HEADER,
    "required": False,
}
_ERROR_RESPONSE_SUMMARIES = {
    HTTPStatus.BAD_REQUEST: "Request validation failed.",
    HTTPStatus.UNAUTHORIZED: (
        "Authentication failed because the Bearer token is missing, expired, malformed, has "
        "missing or invalid required claims, has an invalid signature or signing key, was "
        "issued by the wrong issuer, or has a token_use other than access."
    ),
    HTTPStatus.FORBIDDEN: (
        "The authenticated token lacks the required scope, or its client_id is not mapped "
        "to an IVaaS program."
    ),
    HTTPStatus.INTERNAL_SERVER_ERROR: "An unexpected internal server error occurred.",
    HTTPStatus.SERVICE_UNAVAILABLE: (
        "Authentication could not proceed because trusted token-signing keys were unavailable."
    ),
}
ERROR_RESPONSE_MODELS = {status.value: Error for status in _ERROR_RESPONSE_SUMMARIES}


def _error_response_description(status: HTTPStatus, summary: str) -> str:
    codes = "\n".join(
        f"- `{code.value}`: {definition.message}"
        for code, definition in ERRORS.items()
        if definition.status_code == status
    )
    return (
        f"{summary}\n\nError codes defined for this HTTP status "
        f"(not every operation produces every code):\n{codes}"
    )


ERROR_OPENAPI_RESPONSES: dict[int, dict[str, object]] = {
    status.value: {
        "description": _error_response_description(status, summary),
        "headers": {CORRELATION_ID_HEADER_NAME: OPTIONAL_CORRELATION_ID_RESPONSE_HEADER},
    }
    for status, summary in _ERROR_RESPONSE_SUMMARIES.items()
}


def _openapi_responses(success_description: str) -> dict[int, dict[str, object]]:
    """Return common response documentation plus an operation-specific success response."""
    return {
        200: {
            "description": success_description,
            "headers": {CORRELATION_ID_HEADER_NAME: CORRELATION_ID_RESPONSE_HEADER},
        },
        **ERROR_OPENAPI_RESPONSES,
    }


# Django Ninja 1.6 generates the OAuth2 scheme correctly but leaves operation scopes empty and
# does not expose a dedicated operation-scope argument. openapi_extra is therefore documentation
# metadata only: runtime authentication is still enforced by the API's auth object. A tuple makes
# Ninja replace the generated security array instead of merging a weaker, empty-scope alternative.
OAUTH2_OPENAPI_SECURITY_REQUIREMENT = (
    {
        ProgramOAuth2ClientCredentials.__name__: [
            get_api_authentication().required_scope,
        ]
    },
)

CorrelationId = Annotated[
    str,
    Header(
        alias=CORRELATION_ID_HEADER_NAME,
        max_length=CORRELATION_ID_MAX_LENGTH,
        pattern=CORRELATION_ID_PATTERN,
        description=(
            "A version-4 UUID, optionally followed by `:` and a program reference using letters, "
            "digits, `.`, `_`, `~`, `/`, or `-`, with at most 128 characters in total. IVaaS "
            "logs it and echoes it on the response; error responses echo it only when it is "
            "valid. It may be reused across retries of the same request, is distinct from the "
            "access token's `jti`, and must not contain PII or credentials. Authentication is "
            "evaluated first: when both authentication and this header are invalid, the "
            "authentication error is returned and the invalid identifier is discarded."
        ),
    ),
]


@router.post(
    "/income-verification",
    response={
        200: VerificationResponse,
        **ERROR_RESPONSE_MODELS,
    },
    summary="Verify an individual's income.",
    description="Creates a verification, returning its result in the same exchange.",
    by_alias=True,
    openapi_extra={
        "security": OAUTH2_OPENAPI_SECURITY_REQUIREMENT,
        "responses": _openapi_responses("Verification completed."),
    },
)
def income_verification(
    request: HttpRequest,
    response: HttpResponse,
    payload: VerificationRequest,
    correlation_id: CorrelationId,
) -> VerificationResponse:
    program = get_authenticated_program(request)
    envelope = payload.to_envelope(correlation_id, program_id=program.program_id)
    response[CORRELATION_ID_HEADER_NAME] = envelope.context.correlation_id
    set_verification_log_context(
        application_id=envelope.context.application_id,
        verification_id=str(envelope.context.verification_id),
    )
    logger.info(
        "income verification request accepted",
        extra={
            LogField.EVENT_NAME.value: "income_verification.request.accepted",
            LogField.HTTP_REQUEST_METHOD.value: request.method or "UNKNOWN",
            LogField.URL_PATH.value: request.path,
        },
    )

    # TODO: derive the HTTP status from the overall adapter results (every source failed is an
    #       error; a fallback source succeeding after failures is a success). Always 200 for now.
    return VerificationResponse.model_validate(
        {
            "verificationId": envelope.context.verification_id,
            "sources": engine.verify(envelope.request, envelope.context),
        },
    )


@router.get(
    "/test-connection",
    response={
        200: TestConnectionResponse,
        **ERROR_RESPONSE_MODELS,
    },
    summary="Verify authenticated connectivity.",
    description=(
        "Confirms authentication and environment configuration without claimant data or a "
        "verification attempt."
    ),
    by_alias=True,
    openapi_extra={
        "security": OAUTH2_OPENAPI_SECURITY_REQUIREMENT,
        "responses": _openapi_responses("Authentication and connectivity confirmed."),
    },
)
def test_connection(
    request: HttpRequest,
    response: HttpResponse,
    correlation_id: CorrelationId,
) -> TestConnectionResponse:
    principal = get_authenticated_program(request)
    response[CORRELATION_ID_HEADER_NAME] = correlation_id
    logger.info(
        "test connection request accepted",
        extra={
            LogField.EVENT_NAME.value: "test_connection.request.accepted",
            LogField.HTTP_REQUEST_METHOD.value: request.method or "UNKNOWN",
            LogField.URL_PATH.value: request.path,
        },
    )
    return TestConnectionResponse.model_validate(
        {
            "authenticatedAs": principal.program_id,
            "environment": settings.DEPLOYMENT_ENVIRONMENT,
        }
    )
