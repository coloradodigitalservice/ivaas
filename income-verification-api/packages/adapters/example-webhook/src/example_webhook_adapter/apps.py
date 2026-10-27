"""Configure the example webhook adapter Django app."""

from typing import override

from django.apps import AppConfig


class ExampleWebhookAdapterConfig(AppConfig):
    """Validate the example webhook adapter when Django enables it."""

    name = "example_webhook_adapter"

    @override
    def ready(self) -> None:
        from example_webhook_adapter.api import configured_api_key

        configured_api_key()
