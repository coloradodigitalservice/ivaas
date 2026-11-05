"""Configure the DPW VMI webhook adapter."""

from collections.abc import Mapping
from typing import override

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DpwVmiAdapterConfig(AppConfig):
    """Validate the DPW VMI webhook adapter when Django enables it."""

    name = "dpw_vmi_adapter"

    @override
    def ready(self) -> None:
        configuration = settings.WEBHOOK_ADAPTERS[self.name]["config"]
        if not isinstance(configuration, Mapping):
            raise ImproperlyConfigured("DPW VMI webhook config must be a mapping.")

        api_key = configuration.get("webhook_api_key")
        max_age = configuration.get("webhook_timestamp_max_age_seconds")
        if not isinstance(api_key, str) or not api_key:
            raise ImproperlyConfigured("DPW VMI webhook API key must be a non-empty string.")
        if not isinstance(max_age, int) or max_age <= 0:
            raise ImproperlyConfigured("DPW VMI webhook timestamp maximum age must be positive.")
        self.webhook_api_key = api_key
        self.webhook_timestamp_max_age_seconds = max_age
