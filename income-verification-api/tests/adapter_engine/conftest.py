from collections.abc import Iterator

import pytest
from django.test import override_settings

from adapter_engine.registry import INCOME_SOURCE_ADAPTERS, registry


@pytest.fixture(autouse=True)
def isolated_registry() -> Iterator[None]:
    """Give every test a deterministic EMPTY registry baseline, independent of
    the machine's environment (local env files may enable real adapters)."""
    with override_settings(**{INCOME_SOURCE_ADAPTERS: {}}):
        registry.refresh_from_settings()
        yield
        registry.refresh_from_settings()
