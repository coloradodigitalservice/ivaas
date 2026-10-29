import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from django.test import override_settings
from ivaas_core import (
    IncomeSourceAdapter,
    IncomeSourceError,
    SourceIncome,
    SourceResponseInvalid,
    SourceStatus,
    SourceTimeout,
    SourceUnavailable,
    SubjectNotFound,
    VerificationContext,
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
from income_verification.request_context import LogField
from income_verification.schemas import SourceResult


class ScriptedAdapter(IncomeSourceAdapter):
    source_id = "SCRIPTED_1_0"

    def __init__(self, outcomes: list[SourceIncome | IncomeSourceError]) -> None:
        self._outcomes = iter(outcomes)
        self.call_count = 0

    def verify(self, request: VerificationRequest, context: VerificationContext) -> SourceIncome:
        self.call_count += 1
        outcome = next(self._outcomes)
        if isinstance(outcome, IncomeSourceError):
            raise outcome
        return outcome


def _source_income() -> SourceIncome:
    return SourceIncome(retrieved_at=datetime.now(tz=UTC), raw_income={"records": 1})


def _ok(income: SourceIncome) -> SourceResult:
    return SourceResult(
        source_id=ScriptedAdapter.source_id,
        status=SourceStatus.OK,
        retrieved_at=income.retrieved_at,
        raw_income=income.raw_income,
    )


def _engine(
    outcomes: list[SourceIncome | IncomeSourceError],
    *,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker: CircuitBreakerPolicy | None = None,
) -> tuple[AdapterEngine, ScriptedAdapter, InitializedAdapter]:
    adapter = ScriptedAdapter(outcomes)
    initialized_adapter = InitializedAdapter(
        adapter,
        retry_policy.build("stub") if retry_policy else None,
        circuit_breaker.build() if circuit_breaker else None,
    )
    registry_mock = MagicMock(spec=AdapterRegistry)
    registry_mock.adapters = {"stub": initialized_adapter}
    return AdapterEngine(registry_mock), adapter, initialized_adapter


def _only_status(
    adapter_engine: AdapterEngine, request: VerificationRequest, context: VerificationContext
) -> SourceStatus:
    [result] = adapter_engine.verify(request, context)
    return result.status


def test_without_policies_calls_adapter_once(
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_logger = MagicMock()
    monkeypatch.setattr("adapter_engine.engine.logger", mock_logger)
    expected = _source_income()
    adapter_engine, adapter, _initialized_adapter = _engine([expected])

    assert adapter_engine.verify(verification_request, verification_context) == [_ok(expected)]
    assert adapter.call_count == 1


@pytest.mark.parametrize(
    ("error", "status", "level"),
    [
        (SubjectNotFound("no records"), SourceStatus.NO_DATA, logging.INFO),
        (SourceTimeout("timed out"), SourceStatus.UNAVAILABLE, logging.ERROR),
        (SourceUnavailable("refused"), SourceStatus.UNAVAILABLE, logging.ERROR),
        (SourceResponseInvalid("unparseable"), SourceStatus.ERROR, logging.ERROR),
        (IncomeSourceError("other"), SourceStatus.ERROR, logging.ERROR),
    ],
)
def test_contract_exception_becomes_the_source_status(
    error: IncomeSourceError,
    status: SourceStatus,
    level: int,
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_logger = MagicMock()
    monkeypatch.setattr("adapter_engine.engine.logger", mock_logger)
    adapter_engine, adapter, _initialized_adapter = _engine([error])

    [result] = adapter_engine.verify(verification_request, verification_context)

    assert result.source_id == ScriptedAdapter.source_id
    assert result.status is status
    assert result.raw_income is None
    assert result.retrieved_at is None
    assert adapter.call_count == 1
    mock_logger.log.assert_called_once()
    assert mock_logger.log.call_args.args[0] == level


def test_non_contract_exception_propagates(
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_engine, adapter, _initialized_adapter = _engine([])
    monkeypatch.setattr(adapter, "verify", MagicMock(side_effect=RuntimeError("adapter bug")))

    with pytest.raises(RuntimeError, match="adapter bug"):
        adapter_engine.verify(verification_request, verification_context)


@pytest.mark.parametrize("error_type", [SourceTimeout, SourceUnavailable])
def test_retries_retryable_errors_until_success(
    error_type: type[IncomeSourceError],
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_logger = MagicMock()
    monkeypatch.setattr("adapter_engine.policies.logger", mock_logger)
    expected = _source_income()
    policy = RetryPolicy(3, FixedBackoff(0))
    first_error, second_error = error_type("first"), error_type("second")
    adapter_engine, adapter, _initialized_adapter = _engine(
        [first_error, second_error, expected], retry_policy=policy
    )

    assert adapter_engine.verify(verification_request, verification_context) == [_ok(expected)]
    assert adapter.call_count == 3
    logged_attempts = [call.args[1:] for call in mock_logger.warning.call_args_list]
    assert logged_attempts == [
        ("stub", 1, 3, error_type.__name__, first_error),
        ("stub", 2, 3, error_type.__name__, second_error),
    ]


@pytest.mark.parametrize("error_type", [SourceTimeout, SourceUnavailable])
def test_retry_exhaustion_reports_unavailable(
    error_type: type[IncomeSourceError],
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
) -> None:
    policy = RetryPolicy(2, FixedBackoff(0))
    adapter_engine, adapter, _initialized_adapter = _engine(
        [error_type("first"), error_type("last")],
        retry_policy=policy,
    )

    assert (
        _only_status(adapter_engine, verification_request, verification_context)
        is SourceStatus.UNAVAILABLE
    )
    assert adapter.call_count == 2


@pytest.mark.parametrize(
    ("error_type", "status"),
    [(SubjectNotFound, SourceStatus.NO_DATA), (SourceResponseInvalid, SourceStatus.ERROR)],
)
def test_final_errors_are_not_retried_or_counted_by_breaker(
    error_type: type[IncomeSourceError],
    status: SourceStatus,
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
) -> None:
    expected = _source_income()
    adapter_engine, adapter, _initialized_adapter = _engine(
        [error_type(), expected],
        retry_policy=RetryPolicy(3, FixedBackoff(0)),
        circuit_breaker=CircuitBreakerPolicy(1, 30),
    )

    assert _only_status(adapter_engine, verification_request, verification_context) is status
    assert adapter_engine.verify(verification_request, verification_context) == [_ok(expected)]
    assert adapter.call_count == 2


def test_tripping_call_reports_open_breaker_and_logs_the_cause(
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_logger = MagicMock()
    monkeypatch.setattr("adapter_engine.engine.logger", mock_logger)
    first_error, tripping_error = SourceTimeout("first"), SourceTimeout("second")
    adapter_engine, adapter, _initialized_adapter = _engine(
        [first_error, tripping_error],
        circuit_breaker=CircuitBreakerPolicy(2, 30),
    )

    assert (
        _only_status(adapter_engine, verification_request, verification_context)
        is SourceStatus.UNAVAILABLE
    )
    assert (
        _only_status(adapter_engine, verification_request, verification_context)
        is SourceStatus.UNAVAILABLE
    )

    assert adapter.call_count == 2
    # Each call ends with a completion log naming the error; the second call also logs the
    # breaker opening, with the tripping error as the cause.
    first_failure, second_failure = mock_logger.log.call_args_list
    for failure in (first_failure, second_failure):
        assert failure.args[1] == "income source adapter %r completed without returning income data"
    assert first_failure.kwargs["extra"][LogField.EXCEPTION_TYPE.value] == "SourceTimeout"
    assert second_failure.kwargs["extra"][LogField.EXCEPTION_TYPE.value] == "SourceUnavailable"
    mock_logger.warning.assert_called_once()
    assert mock_logger.warning.call_args.args[0] == (
        "income source adapter %r circuit breaker opened by %s: %s"
    )
    assert mock_logger.warning.call_args.args[2:] == ("SourceTimeout", tripping_error)


def test_open_breaker_stops_retry_without_calling_adapter(
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
) -> None:
    adapter_engine, adapter, _initialized_adapter = _engine(
        [SourceUnavailable("failure")],
        retry_policy=RetryPolicy(3, FixedBackoff(0)),
        circuit_breaker=CircuitBreakerPolicy(1, 30),
    )

    assert (
        _only_status(adapter_engine, verification_request, verification_context)
        is SourceStatus.UNAVAILABLE
    )
    assert (
        _only_status(adapter_engine, verification_request, verification_context)
        is SourceStatus.UNAVAILABLE
    )
    assert adapter.call_count == 1


def test_success_in_half_open_closes_breaker(
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
) -> None:
    expected = _source_income()
    adapter_engine, adapter, initialized_adapter = _engine(
        [SourceUnavailable("failure"), expected],
        circuit_breaker=CircuitBreakerPolicy(1, 0.01),
    )
    circuit_breaker = initialized_adapter.circuit_breaker
    assert circuit_breaker is not None

    assert (
        _only_status(adapter_engine, verification_request, verification_context)
        is SourceStatus.UNAVAILABLE
    )
    assert circuit_breaker.current_state == "open"
    circuit_breaker.half_open()

    assert adapter_engine.verify(verification_request, verification_context) == [_ok(expected)]
    assert circuit_breaker.current_state == "closed"
    assert adapter.call_count == 2


def test_failure_in_half_open_reopens_breaker(
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
) -> None:
    adapter_engine, adapter, initialized_adapter = _engine(
        [SourceUnavailable("first failure"), SourceUnavailable("half-open failure")],
        circuit_breaker=CircuitBreakerPolicy(1, 30),
    )
    circuit_breaker = initialized_adapter.circuit_breaker
    assert circuit_breaker is not None

    assert (
        _only_status(adapter_engine, verification_request, verification_context)
        is SourceStatus.UNAVAILABLE
    )
    circuit_breaker.half_open()

    assert (
        _only_status(adapter_engine, verification_request, verification_context)
        is SourceStatus.UNAVAILABLE
    )
    assert circuit_breaker.current_state == "open"
    assert adapter.call_count == 2


def test_fixed_backoff_sleeps_the_configured_seconds_between_attempts(
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    expected = _source_income()
    adapter_engine, adapter, _initialized_adapter = _engine(
        [SourceTimeout("timeout"), SourceTimeout("timeout"), expected],
        retry_policy=RetryPolicy(3, FixedBackoff(1.5)),
    )

    assert adapter_engine.verify(verification_request, verification_context) == [_ok(expected)]
    assert adapter.call_count == 3
    assert sleeps == [1.5, 1.5]


def test_exponential_backoff_grows_within_bounds_between_attempts(
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    expected = _source_income()
    adapter_engine, adapter, _initialized_adapter = _engine(
        [SourceTimeout("timeout"), SourceTimeout("timeout"), SourceTimeout("timeout"), expected],
        retry_policy=RetryPolicy(4, ExponentialBackoff(1, 3)),
    )

    assert adapter_engine.verify(verification_request, verification_context) == [_ok(expected)]
    assert adapter.call_count == 4
    # tenacity: min(initial * 2**n + jitter, max), jitter in [0, 1], n from 0
    first_sleep, second_sleep, third_sleep = sleeps
    assert 1 <= first_sleep <= 2
    assert 2 <= second_sleep <= 3
    assert third_sleep == 3


def test_django_engine_uses_refreshed_registry(
    verification_request: VerificationRequest,
    verification_context: VerificationContext,
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
        [result] = engine.verify(verification_request, verification_context)

    assert result.source_id == "STUB_1_0"
    assert result.status is SourceStatus.NO_DATA


def test_uses_the_first_enabled_adapter(
    verification_request: VerificationRequest, verification_context: VerificationContext
) -> None:
    expected = _source_income()
    first_adapter = ScriptedAdapter([expected])
    second_adapter = ScriptedAdapter([_source_income()])
    registry_mock = MagicMock(spec=AdapterRegistry)
    registry_mock.adapters = {
        "first": InitializedAdapter(first_adapter, None, None),
        "second": InitializedAdapter(second_adapter, None, None),
    }

    assert AdapterEngine(registry_mock).verify(verification_request, verification_context) == [
        _ok(expected)
    ]
    assert first_adapter.call_count == 1
    assert second_adapter.call_count == 0


def test_no_enabled_adapters_is_an_error(
    verification_request: VerificationRequest, verification_context: VerificationContext
) -> None:
    with pytest.raises(LookupError, match="no income source adapters are enabled"):
        engine.verify(verification_request, verification_context)
