"""Expose the DPW VMI webhook endpoint."""

from collections.abc import Mapping
from typing import cast

from django.conf import settings
from django.http import HttpRequest
from ninja import NinjaAPI

api = NinjaAPI(urls_namespace="dpw_vmi", docs_url=None, openapi_url=None)
config = cast(Mapping[str, str], settings.WEBHOOK_ADAPTERS["dpw_vmi_adapter"]["config"])


@api.post(config["webhook_path"], response={200: dict[str, bool]})
def receive_income_report(request: HttpRequest) -> dict[str, bool]:
    """Acknowledge a DPW webhook request."""
    return {"received": True}
