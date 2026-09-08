"""Version-neutral routes for the program-facing IVaaS API."""

import logging
from typing import Annotated

from django.http import HttpRequest, HttpResponse
from ninja import Header, Router

from income_verification.correlation_id import (
    CORRELATION_ID_HEADER_NAME,
    CORRELATION_ID_MAX_LENGTH,
    CORRELATION_ID_PATTERN,
)
from income_verification.request_context import set_verification_log_context
from income_verification.schemas import Error, VerificationRequest, VerificationResponse

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

CorrelationId = Annotated[
    str,
    Header(
        alias=CORRELATION_ID_HEADER_NAME,
        max_length=CORRELATION_ID_MAX_LENGTH,
        pattern=CORRELATION_ID_PATTERN,
    ),
]


@router.post(
    "/income-verification",
    response={200: VerificationResponse, 400: Error},
    summary="Verify an individual's income.",
    description="Creates a verification, returning its result in the same exchange.",
    by_alias=True,
    openapi_extra={
        "responses": {
            200: {
                "description": "Verification completed.",
                "headers": {CORRELATION_ID_HEADER_NAME: CORRELATION_ID_RESPONSE_HEADER},
            },
            400: {
                "description": "Request validation failed.",
                "headers": {CORRELATION_ID_HEADER_NAME: OPTIONAL_CORRELATION_ID_RESPONSE_HEADER},
            },
        }
    },
)
def income_verification(
    request: HttpRequest,
    response: HttpResponse,
    payload: VerificationRequest,
    correlation_id: CorrelationId,
) -> VerificationResponse:
    envelope = payload.to_envelope(correlation_id)
    response[CORRELATION_ID_HEADER_NAME] = envelope.correlation_id
    set_verification_log_context(
        application_id=envelope.application_id,
        verification_id=str(envelope.verification_id),
    )
    logger.info(
        "income verification request accepted",
        extra={
            "event_name": "income_verification.request.accepted",
            "http_request_method": request.method or "UNKNOWN",
            "url_path": request.path,
        },
    )

    return VerificationResponse(verification_id=envelope.verification_id)
