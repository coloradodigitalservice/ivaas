"""Registry behavior: enablement, fail-fast validation, idempotency, and the
settings-to-contract-exception runtime path."""

import asyncio
from collections.abc import Iterator

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from ivaas_core import IncomeSourceAdapter, SubjectNotFound, VerificationRequest

from income_source_adapters import registry

STUB = "tests.income_source_adapters.fixtures.StubSource"


def declaration(**overrides: object) -> dict[str, dict[str, object]]:
    entry: dict[str, object] = {"class": STUB, "enabled": True, "config": {"greeting": "hi"}}
    entry.update(overrides)
    return {"stub": entry}


@pytest.fixture(autouse=True)
def isolated_registry() -> Iterator[None]:
    """Give every test a registry built from real settings, and restore it
    afterwards even when the test body raises."""
    registry.refresh_from_settings()
    yield
    registry.refresh_from_settings()


class TestBuildRegistry:
    def test_disabled_entries_are_skipped(self) -> None:
        assert registry.build_registry(declaration(enabled=False)) == {}

    def test_enabled_entry_is_instantiated_with_config(self) -> None:
        built = registry.build_registry(declaration())

        source = built["stub"]
        assert isinstance(source, IncomeSourceAdapter)
        assert getattr(source, "greeting", None) == "hi"

    def test_missing_config_value_fails_fast_naming_the_key(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="greeting"):
            registry.build_registry(declaration(config={"greeting": None}))

    def test_unimportable_class_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="cannot be imported"):
            registry.build_registry(declaration(**{"class": "nowhere.Nothing"}))

    def test_missing_class_declaration_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="'class'"):
            registry.build_registry({"stub": {"enabled": True}})

    def test_non_income_source_class_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="does not implement IncomeSourceAdapter"):
            registry.build_registry(
                declaration(**{"class": "tests.income_source_adapters.fixtures.NotASource"})
            )

    def test_missing_source_id_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="source_id"):
            registry.build_registry(
                declaration(
                    **{"class": "tests.income_source_adapters.fixtures.MissingSourceId"}, config={}
                )
            )

    def test_non_mapping_declaration_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="must be a mapping"):
            registry.build_registry({"stub": "cdle_adapter.CdleAdapter"})  # type: ignore[dict-item]

    def test_non_bool_enabled_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="'enabled' must be a bool"):
            registry.build_registry(declaration(enabled="false"))

    @pytest.mark.parametrize("config", [[], "", 0])
    def test_non_mapping_config_fails_fast(self, config: object) -> None:
        with pytest.raises(ImproperlyConfigured, match="'config' must be a mapping"):
            registry.build_registry(declaration(config=config))

    def test_rejected_constructor_config_names_the_source(self) -> None:
        with pytest.raises(ImproperlyConfigured, match=r"stub.*rejected its configuration"):
            registry.build_registry(declaration(config={"unexpected_kwarg": 1}))

    def test_duplicate_source_ids_fail_fast(self) -> None:
        entries = {
            "one": {"class": STUB, "enabled": True, "config": {}},
            "two": {"class": STUB, "enabled": True, "config": {}},
        }

        with pytest.raises(ImproperlyConfigured, match="source ids must be unique"):
            registry.build_registry(entries)


class TestProcessRegistry:
    def test_refresh_is_idempotent(self) -> None:
        with override_settings(INCOME_SOURCE_ADAPTERS=declaration()):
            registry.refresh_from_settings()
            registry.refresh_from_settings()

            assert sorted(registry.enabled_adapters()) == ["stub"]

    def test_unknown_name_raises_helpfully(self) -> None:
        with pytest.raises(KeyError, match="no enabled income source adapter"):
            registry.get_adapter("nope")

    def test_runtime_smoke_settings_to_contract_exception(
        self, verification_request: VerificationRequest
    ) -> None:
        """The WP3 gate: load via settings, call it, catch the contract type."""
        with override_settings(INCOME_SOURCE_ADAPTERS=declaration()):
            registry.refresh_from_settings()
            source = registry.get_adapter("stub")

            assert isinstance(source, IncomeSourceAdapter)
            with pytest.raises(SubjectNotFound):
                asyncio.run(source.verify(verification_request))

    def test_default_settings_enable_nothing_without_env(self) -> None:
        registry.refresh_from_settings()

        assert dict(registry.enabled_adapters()) == {}
