import json
from collections.abc import Iterator
from uuid import UUID

import pytest
from django.conf import settings
from django.test import Client, override_settings

from tests.income_verification.security.authentication_test_support import TEST_ACCESS_TOKEN

API_ROOT = "/api/example-webhook/v1"
WEBHOOK_KEY = "example-webhook-test-key"
pytestmark = pytest.mark.usefixtures("configured_api_authentication", "example_webhook_adapter")


@pytest.fixture
def example_webhook_adapter() -> Iterator[None]:
    with (
        override_settings(
            ROOT_URLCONF="tests.webhook_adapters.urls", # Alternatively, use clear_url_caches() on setup and teardown
            WEBHOOK_ADAPTERS={
                "example_webhook_adapter": {
                    "enabled": True,
                    "config": {"api_key": WEBHOOK_KEY},
                }
            },
        ),
        # Django rebuilds the app registry before applying sibling overrides.
        override_settings(
            INSTALLED_APPS=[*settings.INSTALLED_APPS, "example_webhook_adapter"],
        ),
    ):
        yield


def test_creates_invitation_for_authenticated_program(client: Client) -> None:
    response = client.post(
        f"{API_ROOT}/invitations",
        headers={"Authorization": f"Bearer {TEST_ACCESS_TOKEN}"},
    )

    assert response.status_code == 201
    body = response.json()
    verification_id = UUID(body["verification_id"])
    assert body["url"] == f"https://example.invalid/invitations/{verification_id}"


def test_rejects_invitation_without_token(client: Client) -> None:
    response = client.post(f"{API_ROOT}/invitations")

    assert response.status_code == 401


def test_accepts_event_with_webhook_key(client: Client) -> None:
    response = client.post(
        f"{API_ROOT}/events",
        data=json.dumps({"event": "example"}),
        content_type="application/json",
        headers={"X-Example-Webhook-Key": WEBHOOK_KEY},
    )

    assert response.status_code == 200
    assert response.json() == {"received": True}


def test_rejects_event_with_wrong_webhook_key(client: Client) -> None:
    response = client.post(
        f"{API_ROOT}/events",
        data=json.dumps({"event": "example"}),
        content_type="application/json",
        headers={"X-Example-Webhook-Key": "wrong-key"},
    )

    assert response.status_code == 401
