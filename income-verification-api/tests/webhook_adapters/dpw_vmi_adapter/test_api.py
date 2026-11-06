"""Check DPW VMI webhook signature and timestamp validation."""

import hashlib
import hmac
import logging
from collections.abc import Iterator

import pytest
from django.conf import settings
from django.test import Client, override_settings

WEBHOOK_PATH = "/dpw-vmi/v1/income-report"
WEBHOOK_URL = f"/api{WEBHOOK_PATH}"
WEBHOOK_KEY = "dpw-vmi-test-key"
SIGNED_AT = 1_700_000_000
BODY = b'{"event_type":"ReportSubmission"}'
AUTHENTICATION_ERROR = {
    "error_code": "WEBHOOK_AUTHENTICATION_FAILED",
    "message": "Webhook authentication failed. Check headers, timestamp, and signature.",
}
PROGRAMS = {
    "test-program": {
        "dpw_vmi": {
            "webhook_api_key": "test-webhook-api-key",
        },
    },
}


def signed_headers(
    *, body: bytes = BODY, timestamp: str = str(SIGNED_AT), key: str = WEBHOOK_KEY
) -> dict[str, str]:
    signature = hmac.new(key.encode(), timestamp.encode() + b":" + body, hashlib.sha512).hexdigest()
    return {"X-VMI-Timestamp": timestamp, "X-VMI-Signature": signature}


@pytest.fixture
def dpw_vmi_adapter() -> Iterator[None]:
    with (
        override_settings(
            ROOT_URLCONF="tests.webhook_adapters.dpw_vmi_adapter.urls",
            WEBHOOK_ADAPTERS={
                "dpw_vmi_adapter": {
                    "enabled": True,
                    "config": {
                        "webhook_path": WEBHOOK_PATH,
                        "webhook_api_key": WEBHOOK_KEY,
                        "webhook_timestamp_max_age_seconds": 300,
                    },
                }
            },
            PROGRAMS=PROGRAMS,
        ),
        override_settings(
            INSTALLED_APPS=list(dict.fromkeys([*settings.INSTALLED_APPS, "dpw_vmi_adapter"]))
        ),
    ):
        yield


@pytest.mark.usefixtures("dpw_vmi_adapter")
@pytest.mark.parametrize("received_at", [SIGNED_AT - 300, SIGNED_AT + 300])
def test_webhook_is_acknowledged(
    client: Client, monkeypatch: pytest.MonkeyPatch, received_at: int
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: received_at)
    response = client.post(
        WEBHOOK_URL, data=BODY, content_type="application/json", headers=signed_headers()
    )

    assert response.status_code == 200
    assert response.json() == {"received": True}


@pytest.mark.usefixtures("dpw_vmi_adapter")
@pytest.mark.parametrize(
    ("headers", "detail", "reason"),
    [
        ({"X-VMI-Signature": "a" * 128}, "Missing X-VMI-Timestamp", "missing_timestamp"),
        (signed_headers(timestamp="not-seconds"), "must be Unix seconds", "invalid_timestamp"),
        (signed_headers(timestamp="9" * 21), "must be Unix seconds", "invalid_timestamp"),
        ({"X-VMI-Timestamp": str(SIGNED_AT)}, "Missing X-VMI-Signature", "missing_signature"),
        (
            {**signed_headers(), "X-VMI-Signature": "invalid"},
            "128 lowercase hex characters",
            "invalid_signature",
        ),
        (signed_headers(body=b"different"), "does not match", "signature_mismatch"),
        (signed_headers(key="wrong-key"), "does not match", "signature_mismatch"),
        (signed_headers(timestamp=str(SIGNED_AT + 301)), "in the future", "future_timestamp"),
        (signed_headers(timestamp=str(SIGNED_AT - 301)), "too old", "expired_timestamp"),
    ],
)
def test_webhook_rejects_invalid_headers(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    headers: dict[str, str],
    detail: str,
    reason: str,
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT)

    with caplog.at_level(logging.WARNING, logger="dpw_vmi_adapter.security"):
        response = client.post(
            WEBHOOK_URL, data=BODY, content_type="application/json", headers=headers
        )

    assert response.status_code == 401
    assert response.json() == AUTHENTICATION_ERROR
    failure = next(record for record in caplog.records if record.name == "dpw_vmi_adapter.security")
    assert failure.__dict__["auth.failure.reason"] == reason
    assert detail in failure.getMessage()
    assert BODY.decode() not in failure.getMessage()
    assert WEBHOOK_KEY not in failure.getMessage()


@pytest.mark.usefixtures("dpw_vmi_adapter")
def test_webhook_signature_covers_exact_body_bytes(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT)
    response = client.post(
        WEBHOOK_URL,
        data=b'{ "event_type": "ReportSubmission" }',
        content_type="application/json",
        headers=signed_headers(),
    )

    assert response.status_code == 401
    assert response.json() == AUTHENTICATION_ERROR


@pytest.mark.usefixtures("dpw_vmi_adapter")
def test_webhook_timestamp_window_is_configurable(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dpw_vmi_adapter.security.time.time", lambda: SIGNED_AT + 301)
    with (
        override_settings(
            WEBHOOK_ADAPTERS={
                "dpw_vmi_adapter": {
                    "enabled": True,
                    "config": {
                        "webhook_path": WEBHOOK_PATH,
                        "webhook_api_key": WEBHOOK_KEY,
                        "webhook_timestamp_max_age_seconds": 600,
                    },
                }
            }
        ),
        override_settings(INSTALLED_APPS=settings.INSTALLED_APPS),
    ):
        response = client.post(
            WEBHOOK_URL, data=BODY, content_type="application/json", headers=signed_headers()
        )

    assert response.status_code == 200
