"""The application's registry of configured income source adapters.

Settings declare adapters under `INCOME_SOURCE_ADAPTERS`; the module-level
`registry` instance is the process-wide singleton, rebuilt at startup.
"""

import logging
from collections.abc import Mapping
from importlib import metadata
from types import MappingProxyType
from typing import Self

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from ivaas_core import IncomeSourceAdapter

logger = logging.getLogger(__name__)

# The settings name adapters are declared under
INCOME_SOURCE_ADAPTERS = "INCOME_SOURCE_ADAPTERS"


class AdapterRegistry:
    """The enabled adapters, keyed by their settings declaration name."""

    def __init__(self) -> None:
        self._adapters: dict[str, IncomeSourceAdapter] = {}

    @classmethod
    def from_settings(cls) -> Self:
        """Instantiate and validate every adapter enabled in `INCOME_SOURCE_ADAPTERS`."""
        adapters_settings = getattr(settings, INCOME_SOURCE_ADAPTERS, {})
        if not isinstance(adapters_settings, Mapping):
            raise ImproperlyConfigured(f"{INCOME_SOURCE_ADAPTERS} must be a mapping")

        registry_from_settings = cls()
        seen_source_ids: dict[str, str] = {}
        for name, declaration in adapters_settings.items():
            if not isinstance(declaration, Mapping):
                raise ImproperlyConfigured(f"{name!r} adapter settings must be a mapping")

            enabled = declaration.get("enabled", False)
            if not isinstance(enabled, bool):
                raise ImproperlyConfigured(
                    f"{name!r} adapter settings property 'enabled' must be a bool. "
                    f"Value was {enabled!r}"
                )
            if not enabled:
                logger.debug("income source adapter %r is disabled; skipping", name)
                continue

            dotted_path = declaration.get("class")
            if not isinstance(dotted_path, str) or not dotted_path:
                raise ImproperlyConfigured(
                    f"{name!r} adapter settings must declare a 'class' string"
                )

            # config semantics: omitted or None means no constructor kwargs; a
            # Mapping is passed as kwargs; anything else is a declaration error.
            config = declaration.get("config", None)
            if config is None:
                config = {}
            if not isinstance(config, Mapping):
                raise ImproperlyConfigured(f"{name!r} adapter settings 'config' must be a mapping")
            missing = sorted(key for key, value in config.items() if value is None)
            if missing:
                raise ImproperlyConfigured(
                    f"income source adapter {name!r} is enabled but missing configuration for: "
                    f"{', '.join(missing)} (check the corresponding environment variables)"
                )

            try:
                source_class = import_string(dotted_path)
            except ImportError as error:
                raise ImproperlyConfigured(
                    f"income source adapter {name!r} class {dotted_path!r} cannot be imported"
                ) from error

            try:
                instance = source_class(**config)
            except (TypeError, ValueError) as error:
                raise ImproperlyConfigured(
                    f"income source adapter {name!r} rejected its configuration: {error}"
                ) from error

            if not isinstance(instance, IncomeSourceAdapter):
                raise ImproperlyConfigured(
                    f"income source adapter {name!r} class {dotted_path!r} does not implement "
                    "IncomeSourceAdapter"
                )

            source_id = getattr(type(instance), "source_id", None)
            if not isinstance(source_id, str) or not source_id:
                raise ImproperlyConfigured(
                    f"income source adapter {name!r} class {dotted_path!r} does not declare a "
                    "non-empty source_id string"
                )
            if source_id in seen_source_ids:
                raise ImproperlyConfigured(
                    f"income source adapters {seen_source_ids[source_id]!r} and {name!r} both "
                    f"declare source_id {source_id!r}; source ids must be unique"
                )
            seen_source_ids[source_id] = name

            registry_from_settings._adapters[name] = instance
        return registry_from_settings

    def refresh_from_settings(self) -> None:
        """Build or rebuild this registry from settings. Idempotent."""
        rebuilt = type(self).from_settings()
        self._adapters.clear()
        self._adapters.update(rebuilt._adapters)
        self.log_summary()

    def get_adapter(self, name: str) -> IncomeSourceAdapter:
        try:
            return self._adapters[name]
        except KeyError:
            raise KeyError(
                f"no enabled income source adapter named {name!r}; enabled adapters: "
                f"{sorted(self._adapters) or 'none'}"
            ) from None

    @property
    def adapters(self) -> Mapping[str, IncomeSourceAdapter]:
        """Read-only view of the enabled adapters."""
        return MappingProxyType(self._adapters)

    def log_summary(self) -> None:
        if not self._adapters:
            logger.info("no income source adapters configured")
            return
        try:
            package_map = metadata.packages_distributions()
        except Exception:  # startup logging must never fail
            package_map = {}
        for adapter_settings_key, adapter in self._adapters.items():
            log_adapter_summary(adapter_settings_key, adapter, package_map)


def log_adapter_summary(
    settings_key: str, adapter: IncomeSourceAdapter, package_map: Mapping[str, list[str]]
) -> None:
    """Stateless per-adapter startup line; independent of any registry instance."""
    module = type(adapter).__module__.partition(".")[0]
    distributions = package_map.get(module, [])
    try:
        adapter_wheel_version = metadata.version(distributions[0] if distributions else module)
    except Exception:  # startup logging must never fail
        adapter_wheel_version = "unknown"
    logger.info(
        "Income source adapter initialized: name=%r source_id=%r version=%r",
        settings_key,
        adapter.source_id,
        adapter_wheel_version,
    )


registry = AdapterRegistry()
