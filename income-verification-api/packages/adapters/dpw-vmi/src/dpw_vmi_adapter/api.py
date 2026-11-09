"""Expose the DPW VMI webhook endpoint."""

import json
import logging
from collections.abc import Mapping
from enum import StrEnum
from typing import NoReturn, cast
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI

from dpw_vmi_adapter.apps import DpwVmiAdapterConfig
from dpw_vmi_adapter.forwarding import forward_webhook
from dpw_vmi_adapter.security import DpwVmiAuthenticationError, DpwVmiSignature
from income_verification.request_context import LogField, set_webhook_request_id

logger = logging.getLogger(__name__)
api = NinjaAPI(urls_namespace="dpw_vmi", docs_url=None, openapi_url=None)
config = cast(Mapping[str, str], settings.WEBHOOK_ADAPTERS["dpw_vmi_adapter"]["config"])


class DpwVmiEventType(StrEnum):
    """DPW VMI webhook event types handled by IVaaS."""

    REPORT_SUBMISSION = "ReportSubmission"
    TRANSMISSION_COMPLETE = "TransmissionComplete"


def _return_response_to_vmi(response: HttpResponse) -> HttpResponse:
    logger.info(
        "Returning DPW VMI webhook response.",
        extra={
            LogField.EVENT_NAME.value: "dpw_vmi.webhook.response_returned",
            LogField.HTTP_RESPONSE_STATUS_CODE.value: response.status_code,
        },
    )
    return response


@api.exception_handler(DpwVmiAuthenticationError)
def authentication_error(request: HttpRequest, exc: DpwVmiAuthenticationError) -> HttpResponse:
    return api.create_response(
        request,
        {
            "error_code": "WEBHOOK_AUTHENTICATION_FAILED",
            "message": "Webhook authentication failed. Check headers, timestamp, and signature.",
        },
        status=401,
    )


def _reject_non_json_constant(_: str) -> NoReturn:
    """Make json.loads reject NaN and Infinity, which are not valid JSON."""
    raise ValueError("Invalid JSON constant.")


def _validation_error(request: HttpRequest, field: str, reason: str) -> HttpResponse:
    logger.warning(
        "DPW VMI webhook body validation failed: %s: %s",
        field,
        reason,
        extra={
            LogField.EVENT_NAME.value: "dpw_vmi.webhook.body_validation_failed",
            LogField.HTTP_RESPONSE_STATUS_CODE.value: 400,
        },
    )
    return api.create_response(
        request,
        {
            "error_code": "VALIDATION_ERROR",
            "message": "The request body failed validation.",
            "errors": [{"field": field, "reason": reason}],
        },
        status=400,
    )


def _validate_webhook_body(
    request: HttpRequest, body: dict[str, object], event_type: DpwVmiEventType
) -> HttpResponse | None:
    """Validate only the fields IVaaS reads for supported events."""
    if event_type is DpwVmiEventType.REPORT_SUBMISSION:
        metadata = body.get("report_metadata")
        if not isinstance(metadata, dict):
            return _validation_error(request, "report_metadata", "Must be a JSON object.")
        field = "report_metadata.confirmation_code"
        confirmation_code = metadata.get("confirmation_code")
    else:
        field = "confirmation_code"
        confirmation_code = body.get("confirmation_code")

    if not isinstance(confirmation_code, str) or not confirmation_code:
        return _validation_error(request, field, "Must be a non-empty string.")
    if confirmation_code != request.headers.get("X-VMI-Confirmation-Code"):
        return _validation_error(request, field, "Must match X-VMI-Confirmation-Code.")
    return None


def _forward_to_program(request: HttpRequest, *, webhook_request_id: str) -> HttpResponse:
    configuration = cast(DpwVmiAdapterConfig, apps.get_app_config("dpw_vmi_adapter"))
    program_response = forward_webhook(
        request.body,
        program=configuration.program,
        timeout_seconds=configuration.program_timeout_seconds,
        vmi_timestamp=request.headers["X-VMI-Timestamp"],
        confirmation_code=request.headers.get("X-VMI-Confirmation-Code"),
        webhook_request_id=webhook_request_id,
    )
    response = HttpResponse(program_response.body, status=program_response.status_code)
    if program_response.content_type is None:
        del response.headers["Content-Type"]
    else:
        response.headers["Content-Type"] = program_response.content_type
    return response


def _handle_webhook(request: HttpRequest, *, webhook_request_id: str) -> HttpResponse:
    try:
        body = json.loads(request.body, parse_constant=_reject_non_json_constant)
    except ValueError, RecursionError:
        return _validation_error(request, "body", "Must be valid JSON.")
    if not isinstance(body, dict):
        return _validation_error(request, "body", "Must be a JSON object.")

    try:
        event_type = DpwVmiEventType(body.get("event_type", DpwVmiEventType.REPORT_SUBMISSION))
    except ValueError, TypeError:
        event_type = None
    if event_type is None:
        logger.warning(
            "Ignored unsupported DPW VMI webhook event type.",
            extra={
                LogField.EVENT_NAME.value: "dpw_vmi.webhook.unsupported_event_type",
                LogField.ERROR_TYPE.value: "unsupported_event_type",
                LogField.HTTP_RESPONSE_STATUS_CODE.value: 200,
            },
        )
        response = HttpResponse(status=200)
        del response.headers["Content-Type"]
        return response

    error = _validate_webhook_body(request, body, event_type)
    if error is not None:
        return error
    return _forward_to_program(request, webhook_request_id=webhook_request_id)


@api.post(config["webhook_path"], auth=DpwVmiSignature())
def receive_income_report(request: HttpRequest) -> HttpResponse:
    """Forward a validated DPW webhook and return the program's response."""
    webhook_request_id = str(uuid4())
    set_webhook_request_id(webhook_request_id)
    logger.info(
        "Authenticated DPW VMI webhook received.",
        extra={LogField.EVENT_NAME.value: "dpw_vmi.webhook.received"},
    )
    return _return_response_to_vmi(_handle_webhook(request, webhook_request_id=webhook_request_id))
