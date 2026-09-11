"""Django system checks for the adapter landing zone."""

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core import checks

from adapter_engine.registry import INCOME_SOURCE_ADAPTERS


def unreferenced_adapter_wheels(
    app_configs: Any = None, **kwargs: Any
) -> list[checks.CheckMessage]:
    """Warn about adapter wheels that no INCOME_SOURCE_ADAPTERS entry uses.

    A wheel that was properly placed but never declared in settings usually means a
    half-finished adapter add.
    """
    wheels_dir = Path(settings.BASE_DIR, "custom-adapters", "wheels")
    if not wheels_dir.is_dir():
        return []

    declarations = getattr(settings, INCOME_SOURCE_ADAPTERS, {})
    declared_modules = {
        str(declaration.get("class", "")).split(".")[0]
        for declaration in declarations.values()
        if isinstance(declaration, dict)
    }

    return [
        checks.Warning(
            f"adapter wheel is not declared in {INCOME_SOURCE_ADAPTERS}: {wheel.name}",
            hint=(
                "Half-finished adapter add? Declare it in settings "
                f"({INCOME_SOURCE_ADAPTERS}) or remove the file."
            ),
            id="adapter_engine.W001",
        )
        for wheel in sorted(wheels_dir.glob("*.whl"))
        if wheel.name.split("-")[0] not in declared_modules
    ]
