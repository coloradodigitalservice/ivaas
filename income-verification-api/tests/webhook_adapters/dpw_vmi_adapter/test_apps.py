"""Check DPW VMI webhook configuration at startup."""

from importlib import import_module
from runpy import run_path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from dpw_vmi_adapter.apps import DpwVmiAdapterConfig

from config import settings as settings_module

PROGRAMS = {
    "test-program": {
        "dpw_vmi": {
            "webhook_url": "https://program.example/webhook",
            "webhook_signing_key": "test-webhook-signing-key",
        },
    },
}


def test_default_webhook_timing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DPW_VMI_WEBHOOK_TIMESTAMP_MAX_AGE_SECONDS", raising=False)
    monkeypatch.delenv("DPW_VMI_PROGRAM_TIMEOUT_SECONDS", raising=False)
    configuration = run_path(settings_module.__file__)["WEBHOOK_ADAPTERS"]["dpw_vmi_adapter"][
        "config"
    ]
    assert configuration["webhook_timestamp_max_age_seconds"] == 300
    assert configuration["program_timeout_seconds"] == 10


@pytest.mark.parametrize(
    ("api_key", "max_age", "timeout", "message"),
    [
        ("", 30, 10, "API key"),
        (None, 30, 10, "API key"),
        ("test-key", 0, 10, "timestamp maximum age"),
        ("test-key", "30", 10, "timestamp maximum age"),
        ("test-key", 30, 0, "program timeout"),
        ("test-key", 30, "10", "program timeout"),
    ],
)
def test_invalid_webhook_configuration_fails_startup(
    api_key: object, max_age: object, timeout: object, message: str
) -> None:
    app_config = DpwVmiAdapterConfig("dpw_vmi_adapter", import_module("dpw_vmi_adapter"))
    with (
        override_settings(
            WEBHOOK_ADAPTERS={
                "dpw_vmi_adapter": {
                    "enabled": True,
                    "config": {
                        "webhook_path": "/dpw-vmi/v1/income-report",
                        "webhook_api_key": api_key,
                        "webhook_timestamp_max_age_seconds": max_age,
                        "program_timeout_seconds": timeout,
                    },
                }
            },
            PROGRAMS=PROGRAMS,
        ),
        pytest.raises(ImproperlyConfigured, match=message),
    ):
        app_config.ready()
