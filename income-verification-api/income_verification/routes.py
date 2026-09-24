"""Version-neutral routes for the program-facing IVaaS API."""

import logging
from typing import Annotated

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from ninja import Header, Router

from adapter_engine.engine import engine
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
    AgencyOAuth2ClientCredentials,
    get_api_authentication,
    get_authenticated_agency,
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
ERROR_RESPONSE_MODELS = {
    400: Error,
    401: Error,
    403: Error,
    500: Error,
    503: Error,
}
ERROR_OPENAPI_RESPONSES: dict[int, dict[str, object]] = {
    400: {
        "description": "Request validation failed.",
        "headers": {CORRELATION_ID_HEADER_NAME: OPTIONAL_CORRELATION_ID_RESPONSE_HEADER},
    },
    401: {
        "description": "Authentication failed.",
        "headers": {CORRELATION_ID_HEADER_NAME: OPTIONAL_CORRELATION_ID_RESPONSE_HEADER},
    },
    403: {
        "description": "The authenticated caller is not authorized.",
        "headers": {CORRELATION_ID_HEADER_NAME: OPTIONAL_CORRELATION_ID_RESPONSE_HEADER},
    },
    500: {
        "description": "An internal server error occurred.",
        "headers": {CORRELATION_ID_HEADER_NAME: OPTIONAL_CORRELATION_ID_RESPONSE_HEADER},
    },
    503: {
        "description": "Service unavailable.",
        "headers": {CORRELATION_ID_HEADER_NAME: OPTIONAL_CORRELATION_ID_RESPONSE_HEADER},
    },
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
        AgencyOAuth2ClientCredentials.__name__: [
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
            "Request correlation identifier. Authentication is evaluated before route "
            "validation; when both authentication and this header are invalid, the auth error "
            "takes precedence and the invalid identifier is discarded."
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
    agency = get_authenticated_agency(request)
    envelope = payload.to_envelope(correlation_id, agency_id=agency.agency_id)
    response[CORRELATION_ID_HEADER_NAME] = envelope.correlation_id
    set_verification_log_context(
        application_id=envelope.application_id,
        verification_id=str(envelope.verification_id),
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
            "verificationId": envelope.verification_id,
            "sources": engine.verify(envelope.core_request),
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
    principal = get_authenticated_agency(request)
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
            "authenticatedAs": principal.agency_id,
            "environment": settings.DEPLOYMENT_ENVIRONMENT,
        }
    )
