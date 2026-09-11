import time
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from django.test import override_settings
from ivaas_core import (
    IncomeSourceAdapter,
    IncomeSourceError,
    SourceIncome,
    SourceResponseInvalid,
    SourceTimeout,
    SourceUnavailable,
    SubjectNotFound,
    VerificationRequest,
)

from adapter_engine.engine import AdapterEngine, engine
from adapter_engine.policies import (
    CircuitBreakerPolicy,
    ExponentialBackoff,
    FixedBackoff,
    InitializedAdapter,
    RetryPolicy,
)
from adapter_engine.registry import INCOME_SOURCE_ADAPTERS, AdapterRegistry, registry


class ScriptedAdapter(IncomeSourceAdapter):
    source_id = "SCRIPTED_1_0"

    def __init__(self, outcomes: list[SourceIncome | IncomeSourceError]) -> None:
        self._outcomes = iter(outcomes)
        self.call_count = 0

    def verify(self, request: VerificationRequest) -> SourceIncome:
        self.call_count += 1
        outcome = next(self._outcomes)
        if isinstance(outcome, IncomeSourceError):
            raise outcome
        return outcome


def _source_income() -> SourceIncome:
    return SourceIncome(retrieved_at=datetime.now(tz=UTC), raw_income={})


def _engine(
    outcomes: list[SourceIncome | IncomeSourceError],
    *,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreakerPolicy | None = None,
) -> tuple[AdapterEngine, ScriptedAdapter]:
    adapter = ScriptedAdapter(outcomes)
    initialized_adapter = InitializedAdapter(
        adapter,
        retry_policy.build() if retry_policy else None,
        circuit_breaker.build() if circuit_breaker else None,
    )
    registry_mock = MagicMock(spec=AdapterRegistry)
    registry_mock.get_adapter.return_value = initialized_adapter
    return AdapterEngine(registry_mock), adapter


def test_without_policies_calls_adapter_once(
    verification_request: VerificationRequest,
) -> None:
    expected = _source_income()
    adapter_engine, adapter = _engine([expected])

    assert adapter_engine.verify("stub", verification_request) == expected
    assert adapter.call_count == 1


def test_without_policies_preserves_exception(
    verification_request: VerificationRequest,
) -> None:
    error = SourceTimeout("timed out")
    adapter_engine, adapter = _engine([error])

    with pytest.raises(SourceTimeout) as exc_info:
        adapter_engine.verify("stub", verification_request)

    assert exc_info.value is error
    assert adapter.call_count == 1


@pytest.mark.parametrize("error_type", [SourceTimeout, SourceUnavailable])
def test_retries_retryable_errors_until_success(
    error_type: type[IncomeSourceError],
    verification_request: VerificationRequest,
) -> None:
    expected = _source_income()
    policy = RetryPolicy(3, FixedBackoff(0))
    adapter_engine, adapter = _engine([error_type(), error_type(), expected], retry_policy=policy)

    assert adapter_engine.verify("stub", verification_request) == expected
    assert adapter.call_count == 3


@pytest.mark.parametrize("error_type", [SourceTimeout, SourceUnavailable])
def test_retry_exhaustion_preserves_last_error(
    error_type: type[IncomeSourceError],
    verification_request: VerificationRequest,
) -> None:
    last_error = error_type("last")
    policy = RetryPolicy(2, FixedBackoff(0))
    adapter_engine, adapter = _engine(
        [error_type("first"), last_error],
        retry_policy=policy,
    )

    with pytest.raises(error_type) as exc_info:
        adapter_engine.verify("stub", verification_request)

    assert exc_info.value is last_error
    assert adapter.call_count == 2


@pytest.mark.parametrize("error_type", [SubjectNotFound, SourceResponseInvalid])
def test_final_errors_are_not_retried_or_counted_by_breaker(
    error_type: type[IncomeSourceError],
    verification_request: VerificationRequest,
) -> None:
    expected = _source_income()
    adapter_engine, adapter = _engine(
        [error_type(), expected],
        retry_policy=RetryPolicy(3, FixedBackoff(0)),
        circuit_breaker=CircuitBreakerPolicy(1, 30),
    )

    with pytest.raises(error_type):
        adapter_engine.verify("stub", verification_request)

    assert adapter_engine.verify("stub", verification_request) == expected
    assert adapter.call_count == 2


def test_tripping_call_preserves_adapter_error(
    verification_request: VerificationRequest,
) -> None:
    first_error = SourceUnavailable("first")
    tripping_error = SourceTimeout("second")
    adapter_engine, adapter = _engine(
        [first_error, tripping_error],
        circuit_breaker=CircuitBreakerPolicy(2, 30),
    )

    with pytest.raises(SourceUnavailable) as first_exc:
        adapter_engine.verify("stub", verification_request)
    with pytest.raises(SourceTimeout) as second_exc:
        adapter_engine.verify("stub", verification_request)

    assert first_exc.value is first_error
    assert second_exc.value is tripping_error
    assert adapter.call_count == 2


def test_open_breaker_stops_retry_without_calling_adapter(
    verification_request: VerificationRequest,
) -> None:
    adapter_engine, adapter = _engine(
        [SourceUnavailable("failure")],
        retry_policy=RetryPolicy(3, FixedBackoff(0)),
        circuit_breaker=CircuitBreakerPolicy(1, 30),
    )

    with pytest.raises(SourceUnavailable, match="stub circuit breaker is open"):
        adapter_engine.verify("stub", verification_request)
    with pytest.raises(SourceUnavailable, match="stub circuit breaker is open"):
        adapter_engine.verify("stub", verification_request)

    assert adapter.call_count == 1


def test_success_after_reset_timeout_closes_breaker(
    verification_request: VerificationRequest,
) -> None:
    expected = _source_income()
    adapter_engine, adapter = _engine(
        [SourceUnavailable("failure"), expected],
        circuit_breaker=CircuitBreakerPolicy(1, 0.01),
    )

    with pytest.raises(SourceUnavailable, match="failure"):
        adapter_engine.verify("stub", verification_request)
    time.sleep(0.02)

    assert adapter_engine.verify("stub", verification_request) == expected
    assert adapter.call_count == 2


def test_exponential_backoff_policy_calls_adapter(
    verification_request: VerificationRequest,
) -> None:
    expected = _source_income()
    adapter_engine, adapter = _engine(
        [expected],
        retry_policy=RetryPolicy(2, ExponentialBackoff(0.01, 0.1)),
    )

    assert adapter_engine.verify("stub", verification_request) == expected
    assert adapter.call_count == 1


def test_django_engine_uses_refreshed_registry(
    verification_request: VerificationRequest,
) -> None:
    declarations = {
        "stub": {
            "class": "tests.adapter_engine.fixtures.StubSource",
            "enabled": True,
            "retry_policy": None,
            "circuit_breaker": None,
        }
    }
    with override_settings(**{INCOME_SOURCE_ADAPTERS: declarations}):
        registry.refresh_from_settings()
        with pytest.raises(SubjectNotFound):
            engine.verify("stub", verification_request)

    with override_settings(**{INCOME_SOURCE_ADAPTERS: {}}):
        registry.refresh_from_settings()
