"""Expose the example webhook adapter API."""

import logging
from uuid import uuid4

from django.http import HttpRequest
from ninja import Body, NinjaAPI

from example_webhook_adapter.security import ExampleWebhookKey
from income_verification.api import api_authentication
from income_verification.api_errors import register_exception_handlers

logger = logging.getLogger(__name__)

api = NinjaAPI(
    urls_namespace="example_webhook",
    docs_url=None,
    openapi_url=None,
)
register_exception_handlers(api)


@api.post("/invitations", auth=api_authentication, response={201: dict[str, str]})
def create_invitation(request: HttpRequest) -> dict[str, str]:
    """Create an example invitation for an authenticated program."""
    verification_id = str(uuid4())
    return {
        "url": f"https://example.invalid/invitations/{verification_id}",
        "verification_id": verification_id,
    }


@api.post("/events", auth=ExampleWebhookKey())
def receive_event(request: HttpRequest, payload: Body[dict[str, object]]) -> dict[str, bool]:
    """Accept an example inbound webhook event."""
    logger.info("example webhook event received with %d top-level keys", len(payload))
    return {"received": True}
