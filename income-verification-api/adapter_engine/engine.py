"""Runs income verification calls through each adapter's retry and circuit breaker policies."""

import logging

import pybreaker
from ivaas_core import SourceIncome, SourceUnavailable, VerificationRequest

from adapter_engine.policies import InitializedAdapter
from adapter_engine.registry import AdapterRegistry, registry

logger = logging.getLogger(__name__)


class AdapterEngine:
    """Run adapter calls through their configured execution policies."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def verify(self, request: VerificationRequest) -> SourceIncome:
        """Verify income through adapters, retrying as configured."""
        # TODO: Wire up to income request, invoke from Django view
        # TODO: Call adapters via clientId configuration. For now, get the first configured adapter.
        if not self._registry.adapters:
            raise LookupError("no income source adapters are enabled")
        name, initialized_adapter = next(iter(self._registry.adapters.items()))
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
