import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings


def test_missing_webhook_adapter_setting_fails_startup() -> None:
    # To isolate the example webhook adapter for this test, install only non-adapter apps,
    # then manually set up the example_webhook_adapter in isolation
    installed_apps = [
        app for app in settings.INSTALLED_APPS if app not in settings.WEBHOOK_ADAPTERS
    ]
    with (
        override_settings(
            WEBHOOK_ADAPTERS={
                "example_webhook_adapter": {
                    "enabled": True,
                    "config": {"api_key": None},
                },
            }
        ),
        pytest.raises(ImproperlyConfigured, match="config 'api_key'"),
        override_settings(INSTALLED_APPS=[*installed_apps, "example_webhook_adapter"]),
    ):
        pass
