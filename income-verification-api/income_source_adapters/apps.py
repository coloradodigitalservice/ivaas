from django.apps import AppConfig


class IncomeSourceAdaptersConfig(AppConfig):
    name = "income_source_adapters"

    def ready(self) -> None:
        """Assemble the adapter registry from settings.

        Runs in every process that loads settings (runserver, migrate,
        collectstatic, shells), so instantiation must stay cheap and
        offline — the contract forbids adapter constructors from
        authenticating or touching the network. Idempotent: re-entry
        rebuilds the registry from settings rather than appending.
        """
        from django.core import checks

        from income_source_adapters.checks import unreferenced_adapter_wheels
        from income_source_adapters.registry import registry

        checks.register(unreferenced_adapter_wheels)
        registry.refresh_from_settings()
