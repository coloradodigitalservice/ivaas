"""Runs income verification calls through each adapter's retry and circuit breaker policies."""

import logging

import pybreaker
from ivaas_core import (
    IncomeSourceError,
    SourceIncome,
    SourceStatus,
    SourceUnavailable,
    VerificationRequest,
)

from adapter_engine.policies import InitializedAdapter
from adapter_engine.registry import AdapterRegistry, registry
from income_verification.request_context import LogField
from income_verification.schemas import SourceResult

logger = logging.getLogger(__name__)


class AdapterEngine:
    """Run adapter calls through their configured execution policies."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def verify(self, request: VerificationRequest) -> list[SourceResult]:
        """Verify income through adapters, retrying as configured."""
        # TODO: Call adapters via clientId configuration. For now, get the first configured adapter.
        if not self._registry.adapters:
            raise LookupError("no income source adapters are enabled")
        name, initialized_adapter = next(iter(self._registry.adapters.items()))
        source_id = initialized_adapter.adapter.source_id
        logger.info(
            "Adapter '%s' invoked to handle request",
            name,
            extra={
                LogField.EVENT_NAME.value: "adapter_engine.adapter.invoked",
                LogField.SOURCE_ID.value: source_id,
            },
        )
        try:
            income = _verify_with_policies(name, initialized_adapter, request)
        except IncomeSourceError as error:
            # No data is an ordinary answer; every other status is a failure worth attention.
            logger.log(
                logging.INFO if error.status is SourceStatus.NO_DATA else logging.WARNING,
                "income source adapter %r completed without returning income data",
                name,
                extra={
                    LogField.EVENT_NAME.value: "adapter_engine.adapter.completed",
                    LogField.EXCEPTION_TYPE.value: type(error).__name__,
                    LogField.SOURCE_ID.value: source_id,
                },
            )
            return [SourceResult(source_id=source_id, status=error.status)]
        logger.info(
            "adapter '%s' invocation completed successfully",
            name,
            extra={
                LogField.EVENT_NAME.value: "adapter_engine.adapter.completed",
                LogField.SOURCE_ID.value: source_id,
            },
        )
        return [
            SourceResult(
                source_id=source_id,
                status=SourceStatus.OK,
                retrieved_at=income.retrieved_at,
                raw_income=income.raw_income,
            )
        ]


def _verify_with_policies(
    name: str, initialized_adapter: InitializedAdapter, request: VerificationRequest
) -> SourceIncome:
    """Call the adapter, retrying as configured; an open circuit breaker is SourceUnavailable."""
    try:
        if initialized_adapter.retrying is not None:
            return initialized_adapter.retrying(
                _attempt_verification_request, initialized_adapter, request
            )
        return _attempt_verification_request(initialized_adapter, request)
    except pybreaker.CircuitBreakerError as error:
        # On the call that trips the breaker, pybreaker raises its own error with the
        # adapter's exception as __context__; a call rejected while already open has none.
        cause = error.__context__
        if cause is not None:
            # TODO: use static string with structured keys for dynamic context
            logger.warning(
                "income source adapter %r circuit breaker opened by %s: %s",
                name,
                type(cause).__name__,
                cause,
            )
        raise SourceUnavailable(
            f"income source adapter {name!r} circuit breaker is open"
        ) from cause


def _attempt_verification_request(
    initialized_adapter: InitializedAdapter, request: VerificationRequest
) -> SourceIncome:
    """Make one call via the adapter, through its circuit breaker as configured."""
    if initialized_adapter.circuit_breaker is not None:
        # PyBreaker holds a lock for the whole call, so one call per breaker at a time.
        # Revisit if calling view becomes async.
        return initialized_adapter.circuit_breaker.call(initialized_adapter.adapter.verify, request)
    return initialized_adapter.adapter.verify(request)


engine = AdapterEngine(registry)
