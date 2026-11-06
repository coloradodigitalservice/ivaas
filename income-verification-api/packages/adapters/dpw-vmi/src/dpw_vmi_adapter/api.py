"""Expose the DPW VMI webhook endpoint."""

import json
import logging
from collections.abc import Mapping
from enum import StrEnum
from typing import cast
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI

from dpw_vmi_adapter.apps import DpwVmiAdapterConfig
from dpw_vmi_adapter.forwarding import forward_webhook
from dpw_vmi_adapter.security import DpwVmiAuthenticationError, DpwVmiSignature
from income_verification.request_context import set_webhook_request_id

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
            "event.name": "dpw_vmi.webhook.response_returned",
            "http.response.status_code": response.status_code,
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
        body = json.loads(request.body)
    except ValueError, RecursionError:
        body = None
    if not isinstance(body, dict):
        logger.warning(
            "Rejected DPW VMI webhook because its body is not a JSON object.",
            extra={
                "event.name": "dpw_vmi.webhook.invalid_body",
                "error.type": "invalid_body",
                "http.response.status_code": 400,
            },
        )
        return api.create_response(
            request,
            {
                "error_code": "VALIDATION_ERROR",
                "message": "Webhook body must be a JSON object.",
            },
            status=400,
        )

    try:
        event_type = DpwVmiEventType(body.get("event_type", DpwVmiEventType.REPORT_SUBMISSION))
    except ValueError:
        event_type = None
    match event_type:
        case DpwVmiEventType.REPORT_SUBMISSION:
            return _forward_to_program(request, webhook_request_id=webhook_request_id)
        case DpwVmiEventType.TRANSMISSION_COMPLETE:
            # Use the sole program until confirmation-code routing supports multiple programs.
            return _forward_to_program(request, webhook_request_id=webhook_request_id)
        case _:
            logger.warning(
                "Ignored unsupported DPW VMI webhook event type.",
                extra={
                    "event.name": "dpw_vmi.webhook.unsupported_event_type",
                    "error.type": "unsupported_event_type",
                    "http.response.status_code": 200,
                },
            )
            response = HttpResponse(status=200)
            del response.headers["Content-Type"]
            return response


@api.post(config["webhook_path"], auth=DpwVmiSignature())
def receive_income_report(request: HttpRequest) -> HttpResponse:
    """Forward an authenticated DPW webhook and return the program's response."""
    webhook_request_id = str(uuid4())
    set_webhook_request_id(webhook_request_id)
    logger.info(
        "Authenticated DPW VMI webhook received.",
        extra={"event.name": "dpw_vmi.webhook.received"},
    )
    return _return_response_to_vmi(_handle_webhook(request, webhook_request_id=webhook_request_id))
