"""Configure the DPW VMI webhook adapter."""

from collections.abc import Mapping
from typing import override

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from dpw_vmi_adapter.programs import DpwVmiProgram, configured_programs


class DpwVmiAdapterConfig(AppConfig):
    """Validate the DPW VMI webhook adapter when Django enables it.

    Attributes:
        webhook_api_key: Secret used to verify inbound VMI signatures.
        webhook_timestamp_max_age_seconds: Maximum allowed age of a webhook timestamp.
        program_timeout_seconds: Outbound program request timeout in seconds.
        program: Sole program configured to receive forwarded VMI webhooks.
    """

    name = "dpw_vmi_adapter"

    @override
    def ready(self) -> None:
        configuration = settings.WEBHOOK_ADAPTERS[self.name]["config"]
        if not isinstance(configuration, Mapping):
            raise ImproperlyConfigured("DPW VMI webhook config must be a mapping.")

        api_key = configuration.get("webhook_api_key")
        max_age = configuration.get("webhook_timestamp_max_age_seconds")
        timeout = configuration.get("program_timeout_seconds")
        if not isinstance(api_key, str) or not api_key:
            raise ImproperlyConfigured("DPW VMI webhook API key must be a non-empty string.")
        if not isinstance(max_age, int) or max_age <= 0:
            raise ImproperlyConfigured("DPW VMI webhook timestamp maximum age must be positive.")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ImproperlyConfigured("DPW VMI program timeout must be positive.")
        self.webhook_api_key = api_key
        self.webhook_timestamp_max_age_seconds = max_age
        self.program_timeout_seconds = timeout

        programs = configured_programs()
        if not programs:
            raise ImproperlyConfigured(
                "dpw_vmi_adapter requires at least one program with a 'dpw_vmi' "
                "configuration in PROGRAMS."
            )

        # TODO: Once VMI returns program_id in webhook custom attributes, remove this check
        #       and route each request to its identified program.
        if len(programs) > 1:
            raise ImproperlyConfigured(
                "dpw_vmi_adapter currently supports only one program with a 'dpw_vmi' "
                f"configuration in PROGRAMS; found {len(programs)}."
            )
        self.program: DpwVmiProgram = programs[0]
