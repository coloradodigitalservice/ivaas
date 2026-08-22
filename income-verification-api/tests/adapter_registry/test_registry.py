"""Registry behavior: enablement, fail-fast validation, idempotency, and the
settings-to-contract-exception runtime path."""

import asyncio
from collections.abc import Iterator
from importlib import metadata
from unittest.mock import MagicMock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from ivaas_core import IncomeSourceAdapter, SubjectNotFound, VerificationRequest

from adapter_registry.registry import (
    INCOME_SOURCE_ADAPTERS,
    AdapterRegistry,
    log_adapter_summary,
    registry,
)
from tests.adapter_registry.fixtures import StubSource

STUB = "tests.adapter_registry.fixtures.StubSource"
LOGGER = "adapter_registry.registry.logger"


def adapter_settings_entry(**overrides: object) -> dict[str, dict[str, object]]:
    entry: dict[str, object] = {"class": STUB, "enabled": True}
    entry.update(overrides)
    return {"stub": entry}


def build_from_settings(adapter_settings: object) -> AdapterRegistry:
    """Mimic the INCOME_SOURCE_ADAPTERS setting, then build a registry from it."""
    with override_settings(**{INCOME_SOURCE_ADAPTERS: adapter_settings}):
        return AdapterRegistry.from_settings()


@pytest.fixture(autouse=True)
def isolated_registry() -> Iterator[None]:
    """Give every test a deterministic EMPTY registry baseline, independent of
    the machine's environment (local env files may enable real adapters)."""
    with override_settings(**{INCOME_SOURCE_ADAPTERS: {}}):
        registry.refresh_from_settings()
        yield
        registry.refresh_from_settings()


class TestFromSettings:
    def test_disabled_entries_are_skipped(self) -> None:
        assert build_from_settings(adapter_settings_entry(enabled=False)).adapters == {}

    def test_enabled_entry_is_instantiated_with_config(self) -> None:
        built = build_from_settings(adapter_settings_entry(config={"greeting": "hi"}))

        source = built.get_adapter("stub")
        assert isinstance(source, IncomeSourceAdapter)
        assert getattr(source, "greeting", None) == "hi"

    def test_missing_config_value_fails_fast_naming_the_key(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="greeting"):
            build_from_settings(adapter_settings_entry(config={"greeting": None}))

    def test_unimportable_class_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="cannot be imported"):
            build_from_settings(adapter_settings_entry(**{"class": "nowhere.Nothing"}))

    def test_missing_class_declaration_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="'class'"):
            build_from_settings({"stub": {"enabled": True}})

    def test_non_income_source_class_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="does not implement IncomeSourceAdapter"):
            build_from_settings(
                adapter_settings_entry(**{"class": "tests.adapter_registry.fixtures.NotASource"})
            )

    def test_missing_source_id_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="source_id"):
            build_from_settings(
                adapter_settings_entry(
                    **{"class": "tests.adapter_registry.fixtures.MissingSourceId"}
                )
            )

    @pytest.mark.parametrize("adapter_settings", [None, [], "cdle"])
    def test_non_mapping_settings_value_fails_fast(self, adapter_settings: object) -> None:
        expected = f"{INCOME_SOURCE_ADAPTERS} must be a mapping"
        with pytest.raises(ImproperlyConfigured, match=expected):
            build_from_settings(adapter_settings)

    def test_non_mapping_declaration_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="must be a mapping"):
            build_from_settings({"stub": "example.Adapter"})

    def test_non_bool_enabled_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="'enabled' must be a bool"):
            build_from_settings(adapter_settings_entry(enabled="false"))

    @pytest.mark.parametrize("config", [[], "", 0])
    def test_non_mapping_config_fails_fast(self, config: object) -> None:
        with pytest.raises(ImproperlyConfigured, match="'config' must be a mapping"):
            build_from_settings(adapter_settings_entry(config=config))

    def test_rejected_constructor_config_names_the_source(self) -> None:
        with pytest.raises(ImproperlyConfigured, match=r"stub.*rejected its configuration"):
            build_from_settings(adapter_settings_entry(config={"unexpected_kwarg": 1}))

    def test_omitted_config_is_valid(self) -> None:
        built = build_from_settings(adapter_settings_entry())

        assert getattr(built.get_adapter("stub"), "greeting", None) == "hello"

    def test_explicit_none_config_is_treated_as_omitted(self) -> None:
        built = build_from_settings(adapter_settings_entry(config=None))

        assert getattr(built.get_adapter("stub"), "greeting", None) == "hello"

    def test_duplicate_source_ids_fail_fast(self) -> None:
        adapter_settings = {
            "one": {"class": STUB, "enabled": True},
            "two": {"class": STUB, "enabled": True},
        }

        with pytest.raises(ImproperlyConfigured, match="source ids must be unique"):
            build_from_settings(adapter_settings)


class TestProcessRegistry:
    def test_refresh_is_idempotent(self) -> None:
        with override_settings(**{INCOME_SOURCE_ADAPTERS: adapter_settings_entry()}):
            registry.refresh_from_settings()
            registry.refresh_from_settings()

            assert sorted(registry.adapters) == ["stub"]

    def test_unknown_name_raises_helpfully(self) -> None:
        with pytest.raises(KeyError, match="no enabled income source adapter"):
            registry.get_adapter("nope")

    def test_runtime_smoke_settings_to_contract_exception(
        self, verification_request: VerificationRequest
    ) -> None:
        """The WP3 gate: load via settings, call it, catch the contract type."""
        with override_settings(**{INCOME_SOURCE_ADAPTERS: adapter_settings_entry()}):
            registry.refresh_from_settings()
            source = registry.get_adapter("stub")

            assert isinstance(source, IncomeSourceAdapter)
            with pytest.raises(SubjectNotFound):
                asyncio.run(source.verify(verification_request))

    def test_empty_declarations_enable_nothing(self) -> None:
        with override_settings(**{INCOME_SOURCE_ADAPTERS: {}}):
            registry.refresh_from_settings()

            assert dict(registry.adapters) == {}

    def test_each_registered_adapter_logs_one_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_logger = MagicMock()
        monkeypatch.setattr(LOGGER, mock_logger)

        with override_settings(**{INCOME_SOURCE_ADAPTERS: adapter_settings_entry()}):
            registry.refresh_from_settings()

        initialized_calls = [
            call.args for call in mock_logger.info.call_args_list if "initialized" in call.args[0]
        ]
        assert len(initialized_calls) == 1
        assert initialized_calls[0][1:] == ("stub", "STUB_1_0", initialized_calls[0][3])

    def test_empty_registry_logs_neutral_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_logger = MagicMock()
        monkeypatch.setattr(LOGGER, mock_logger)

        with override_settings(**{INCOME_SOURCE_ADAPTERS: {}}):
            registry.refresh_from_settings()

        mock_logger.info.assert_called_once_with("no income source adapters configured")
        mock_logger.warning.assert_not_called()

    def test_version_comes_from_the_mapped_distribution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_logger = MagicMock()
        monkeypatch.setattr(LOGGER, mock_logger)
        monkeypatch.setattr(metadata, "version", lambda dist: {"d": "1.2.3"}[dist])

        log_adapter_summary("stub", StubSource(), {"tests": ["d"]})

        assert mock_logger.info.call_args.args[3] == "1.2.3"

    def test_version_falls_back_to_the_module_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_logger = MagicMock()
        monkeypatch.setattr(LOGGER, mock_logger)
        monkeypatch.setattr(metadata, "version", lambda dist: {"tests": "9.9.9"}[dist])

        log_adapter_summary("stub", StubSource(), {})

        assert mock_logger.info.call_args.args[3] == "9.9.9"

    def test_version_degrades_to_unknown_instead_of_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(dist: str) -> str:
            raise metadata.PackageNotFoundError(dist)

        mock_logger = MagicMock()
        monkeypatch.setattr(LOGGER, mock_logger)
        monkeypatch.setattr(metadata, "version", broken)

        log_adapter_summary("stub", StubSource(), {})

        assert mock_logger.info.call_args.args[3] == "unknown"

    def test_logging_survives_a_package_scan_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken_scan() -> dict[str, list[str]]:
            raise OSError("metadata scan failed")

        mock_logger = MagicMock()
        monkeypatch.setattr(LOGGER, mock_logger)
        monkeypatch.setattr(metadata, "packages_distributions", broken_scan)

        with override_settings(**{INCOME_SOURCE_ADAPTERS: adapter_settings_entry()}):
            registry.refresh_from_settings()

        assert any("initialized" in call.args[0] for call in mock_logger.info.call_args_list)
