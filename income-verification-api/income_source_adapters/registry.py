"""Builds and holds the process-wide registry of configured income sources.

Settings declare sources under ``INCOME_SOURCE_ADAPTERS``:

Disabled entries are skipped entirely, so commands in environments that never
enable a source (CI, migrate, collectstatic) load settings without that
source's environment variables. Enabled entries fail fast and loudly at
startup when misconfigured.
"""

import logging
from collections.abc import Mapping
from types import MappingProxyType

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from ivaas_core import IncomeSourceAdapter

logger = logging.getLogger(__name__)

_registry: dict[str, IncomeSourceAdapter] = {}


def build_registry(
    declarations: Mapping[str, Mapping[str, object]],
) -> dict[str, IncomeSourceAdapter]:
    """Instantiate every enabled declaration, validating as we go."""
    registry: dict[str, IncomeSourceAdapter] = {}
    seen_source_ids: dict[str, str] = {}
    for name, declaration in declarations.items():
        if not isinstance(declaration, Mapping):
            raise ImproperlyConfigured(f"INCOME_SOURCE_ADAPTERS[{name!r}] must be a mapping")

        enabled = declaration.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ImproperlyConfigured(
                f"INCOME_SOURCE_ADAPTERS[{name!r}] 'enabled' must be a bool, got {enabled!r}"
            )
        if not enabled:
            logger.debug("income source %r is disabled; skipping", name)
            continue

        dotted_path = declaration.get("class")
        if not isinstance(dotted_path, str) or not dotted_path:
            raise ImproperlyConfigured(
                f"INCOME_SOURCE_ADAPTERS[{name!r}] must declare a 'class' string"
            )

        config = declaration.get("config", None)
        if config is None:
            config = {}
        if not isinstance(config, Mapping):
            raise ImproperlyConfigured(
                f"INCOME_SOURCE_ADAPTERS[{name!r}] 'config' must be a mapping"
            )
        missing = sorted(key for key, value in config.items() if value is None)
        if missing:
            raise ImproperlyConfigured(
                f"income source {name!r} is enabled but missing configuration for: "
                f"{', '.join(missing)} (check the corresponding environment variables)"
            )

        try:
            source_class = import_string(dotted_path)
        except ImportError as error:
            raise ImproperlyConfigured(
                f"income source {name!r} class {dotted_path!r} cannot be imported"
            ) from error

        try:
            instance = source_class(**config)
        except (TypeError, ValueError) as error:
            raise ImproperlyConfigured(
                f"income source {name!r} rejected its configuration: {error}"
            ) from error

        if not isinstance(instance, IncomeSourceAdapter):
            raise ImproperlyConfigured(
                f"income source {name!r} class {dotted_path!r} does not implement "
                "IncomeSourceAdapter"
            )
        source_id = getattr(type(instance), "source_id", None)
        if not isinstance(source_id, str) or not source_id:
            raise ImproperlyConfigured(
                f"income source {name!r} class {dotted_path!r} does not declare a "
                "non-empty source_id string"
            )
        if source_id in seen_source_ids:
            raise ImproperlyConfigured(
                f"income sources {seen_source_ids[source_id]!r} and {name!r} both declare "
                f"source_id {source_id!r}; source ids must be unique"
            )
        seen_source_ids[source_id] = name

        registry[name] = instance
        logger.info("income source %r ready (source_id=%s)", name, source_id)
    return registry


def refresh_from_settings() -> None:
    """Rebuild the process-wide registry from settings. Idempotent."""
    declarations = getattr(settings, "INCOME_SOURCE_ADAPTERS", {})
    rebuilt = build_registry(declarations)
    _registry.clear()
    _registry.update(rebuilt)


def get_adapter(name: str) -> IncomeSourceAdapter:
    try:
        return _registry[name]
    except KeyError:
        raise KeyError(
            f"no enabled income source named {name!r}; enabled sources: "
            f"{sorted(_registry) or 'none'}"
        ) from None


def enabled_adapters() -> Mapping[str, IncomeSourceAdapter]:
    """Read-only view of the registry."""
    return MappingProxyType(_registry)
