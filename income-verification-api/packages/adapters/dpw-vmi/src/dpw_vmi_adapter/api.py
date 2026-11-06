"""Expose the DPW VMI webhook endpoint."""

from collections.abc import Mapping
from typing import cast

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI

from dpw_vmi_adapter.security import DpwVmiAuthenticationError, DpwVmiSignature

api = NinjaAPI(urls_namespace="dpw_vmi", docs_url=None, openapi_url=None)
config = cast(Mapping[str, str], settings.WEBHOOK_ADAPTERS["dpw_vmi_adapter"]["config"])


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


@api.post(config["webhook_path"], auth=DpwVmiSignature(), response={200: dict[str, bool]})
def receive_income_report(request: HttpRequest) -> dict[str, bool]:
    """Acknowledge a DPW webhook request."""
    return {"received": True}
