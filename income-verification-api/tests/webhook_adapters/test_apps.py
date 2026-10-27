import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings


def test_missing_webhook_adapter_setting_fails_startup() -> None:
    with (
        override_settings(
            WEBHOOK_ADAPTERS={
                "example_webhook_adapter": {
                    "enabled": True,
                    "config": {"api_key": None},
                }
            }
        ),
        pytest.raises(ImproperlyConfigured),
        override_settings(INSTALLED_APPS=[*settings.INSTALLED_APPS, "example_webhook_adapter"]),
    ):
        pass
