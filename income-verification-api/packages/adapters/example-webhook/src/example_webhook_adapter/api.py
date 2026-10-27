"""Expose the example webhook adapter API."""

import hmac
import logging
from collections.abc import Mapping
from typing import override
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from ninja import Body, NinjaAPI
from ninja.security import APIKeyHeader

from example_webhook_adapter.apps import ExampleWebhookAdapterConfig
from income_verification.api import api_authentication
from income_verification.api_errors import register_exception_handlers

logger = logging.getLogger(__name__)


def configured_api_key() -> str:
    app_name = ExampleWebhookAdapterConfig.name
    configuration = settings.WEBHOOK_ADAPTERS[app_name]["config"]
    if not isinstance(configuration, Mapping):
        raise ImproperlyConfigured(f"{app_name} webhook adapter config must be a mapping.")

    api_key = configuration.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        raise ImproperlyConfigured(
            f"{app_name} webhook adapter config 'api_key' must be a non-empty string."
        )
    return api_key


class ExampleWebhookKey(APIKeyHeader):
    """Authenticate inbound events with the configured example key."""

    param_name = "X-Example-Webhook-Key"

    @override
    def authenticate(self, request: HttpRequest, key: str | None) -> str | None:
        expected_key = configured_api_key()
        if key and hmac.compare_digest(key, expected_key):
            return key
        return None


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
