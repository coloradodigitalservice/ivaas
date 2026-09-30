from importlib import metadata
from unittest.mock import MagicMock

import pybreaker
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from ivaas_core import (
    IncomeSourceAdapter,
    SubjectNotFound,
    VerificationContext,
    VerificationRequest,
)
from tenacity import Retrying

from adapter_engine.policies import InitializedAdapter
from adapter_engine.registry import (
    INCOME_SOURCE_ADAPTERS,
    AdapterRegistry,
    log_adapter_summary,
    registry,
)
from tests.adapter_engine.fixtures import StubSource

STUB = "tests.adapter_engine.fixtures.StubSource"
LOGGER = "adapter_engine.registry.logger"


def adapter_settings_entry(**overrides: object) -> dict[str, dict[str, object]]:
    entry: dict[str, object] = {
        "class": STUB,
        "enabled": True,
        "retry_policy": None,
        "circuit_breaker": None,
    }
    entry.update(overrides)
    return {"stub": entry}


def build_from_settings(adapter_settings: object) -> AdapterRegistry:
    """Mimic the INCOME_SOURCE_ADAPTERS setting, then build a registry from it."""
    with override_settings(**{INCOME_SOURCE_ADAPTERS: adapter_settings}):
        return AdapterRegistry.from_settings()


class TestFromSettings:
    def test_disabled_entries_are_skipped(self) -> None:
        assert build_from_settings(adapter_settings_entry(enabled=False)).adapters == {}

    def test_enabled_entry_is_instantiated_with_config(self) -> None:
        built = build_from_settings(adapter_settings_entry(config={"greeting": "hi"}))

        initialized_adapter = built.get_adapter("stub")
        assert isinstance(initialized_adapter.adapter, IncomeSourceAdapter)
        assert getattr(initialized_adapter.adapter, "greeting", None) == "hi"
        assert initialized_adapter.retrying is None
        assert initialized_adapter.circuit_breaker is None

    def test_enabled_entry_registers_execution_policies(self) -> None:
        built = build_from_settings(
            adapter_settings_entry(
                retry_policy={
                    "max_attempts": 3,
                    "backoff": {"strategy": "fixed", "seconds": 1},
                },
                circuit_breaker={
                    "failure_threshold": 5,
                    "reset_timeout_seconds": 30,
                },
            )
        )

        initialized_adapter = built.get_adapter("stub")
        assert isinstance(initialized_adapter.retrying, Retrying)
        assert isinstance(initialized_adapter.circuit_breaker, pybreaker.CircuitBreaker)
        assert initialized_adapter.circuit_breaker.fail_max == 5
        assert initialized_adapter.circuit_breaker.reset_timeout == 30

    def test_missing_config_value_fails_fast_naming_the_key(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="greeting"):
            build_from_settings(adapter_settings_entry(config={"greeting": None}))

    def test_unimportable_class_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="cannot be imported"):
            build_from_settings(adapter_settings_entry(**{"class": "nowhere.Nothing"}))

    def test_missing_class_declaration_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="'class'"):
            build_from_settings(
                {
                    "stub": {
                        "enabled": True,
                        "retry_policy": None,
                        "circuit_breaker": None,
                    }
                }
            )

    @pytest.mark.parametrize("policy_name", ["retry_policy", "circuit_breaker"])
    def test_missing_policy_declaration_fails_fast(self, policy_name: str) -> None:
        declaration = adapter_settings_entry()["stub"]
        del declaration[policy_name]

        with pytest.raises(ImproperlyConfigured, match=policy_name):
            build_from_settings({"stub": declaration})

    def test_disabled_adapter_policy_is_still_validated(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="retry_policy"):
            build_from_settings(adapter_settings_entry(enabled=False, retry_policy="invalid"))

    def test_non_income_source_class_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="does not implement IncomeSourceAdapter"):
            build_from_settings(
                adapter_settings_entry(**{"class": "tests.adapter_engine.fixtures.NotASource"})
            )

    def test_missing_source_id_fails_fast(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="source_id"):
            build_from_settings(
                adapter_settings_entry(**{"class": "tests.adapter_engine.fixtures.MissingSourceId"})
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

        assert getattr(built.get_adapter("stub").adapter, "greeting", None) == "hello"

    def test_explicit_none_config_is_treated_as_omitted(self) -> None:
        built = build_from_settings(adapter_settings_entry(config=None))

        assert getattr(built.get_adapter("stub").adapter, "greeting", None) == "hello"

    def test_duplicate_source_ids_fail_fast(self) -> None:
        adapter_settings = {
            "one": adapter_settings_entry()["stub"],
            "two": adapter_settings_entry()["stub"],
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
        self, verification_request: VerificationRequest, verification_context: VerificationContext
    ) -> None:
        """The WP3 gate: load via settings, call it, catch the contract type."""
        with override_settings(**{INCOME_SOURCE_ADAPTERS: adapter_settings_entry()}):
            registry.refresh_from_settings()
            initialized_adapter = registry.get_adapter("stub")

            assert isinstance(initialized_adapter.adapter, IncomeSourceAdapter)
            with pytest.raises(SubjectNotFound):
                initialized_adapter.adapter.verify(verification_request, verification_context)

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
        monkeypatch.setattr(metadata, "version", lambda dist: {"stub-adapter": "1.2.3"}[dist])

        log_adapter_summary(
            "stub", InitializedAdapter(StubSource(), None, None), {"tests": ["stub-adapter"]}
        )

        assert mock_logger.info.call_args.args[3] == "1.2.3"

    def test_version_falls_back_to_the_module_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_logger = MagicMock()
        monkeypatch.setattr(LOGGER, mock_logger)
        monkeypatch.setattr(metadata, "version", lambda dist: {"tests": "9.9.9"}[dist])

        log_adapter_summary("stub", InitializedAdapter(StubSource(), None, None), {})

        assert mock_logger.info.call_args.args[3] == "9.9.9"

    def test_version_degrades_to_unknown_instead_of_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(dist: str) -> str:
            raise metadata.PackageNotFoundError(dist)

        mock_logger = MagicMock()
        monkeypatch.setattr(LOGGER, mock_logger)
        monkeypatch.setattr(metadata, "version", broken)

        log_adapter_summary("stub", InitializedAdapter(StubSource(), None, None), {})

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
