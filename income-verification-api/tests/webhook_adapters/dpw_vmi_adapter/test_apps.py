"""Check DPW VMI webhook configuration at startup."""

from importlib import import_module

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from dpw_vmi_adapter.apps import DpwVmiAdapterConfig


@pytest.mark.parametrize(
    ("api_key", "max_age", "message"),
    [
        ("", 30, "API key"),
        (None, 30, "API key"),
        ("test-key", 0, "timestamp maximum age"),
        ("test-key", "30", "timestamp maximum age"),
    ],
)
def test_invalid_webhook_configuration_fails_startup(
    api_key: object, max_age: object, message: str
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
                    },
                }
            }
        ),
        pytest.raises(ImproperlyConfigured, match=message),
    ):
        app_config.ready()
