"""Runs income verification calls through each adapter's retry and circuit breaker policies."""

import pybreaker
from ivaas_core import SourceIncome, SourceUnavailable, VerificationRequest

from adapter_engine.policies import InitializedAdapter
from adapter_engine.registry import AdapterRegistry, registry


class AdapterEngine:
    """Run adapter calls through their configured execution policies."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def verify(self, name: str, request: VerificationRequest) -> SourceIncome:
        """Verify income through one registered adapter, retrying as necessary."""
        initialized_adapter = self._registry.get_adapter(name)
        try:
            if initialized_adapter.retrying is not None:
                return initialized_adapter.retrying(
                    _attempt_verification_request, initialized_adapter, request
                )
            return _attempt_verification_request(initialized_adapter, request)
        except pybreaker.CircuitBreakerError:
            raise SourceUnavailable(
                f"income source adapter {name!r} circuit breaker is open"
            ) from None


def _attempt_verification_request(
    initialized_adapter: InitializedAdapter, request: VerificationRequest
) -> SourceIncome:
    """Make one call to the adapter, through its circuit breaker when it has one."""
    if initialized_adapter.circuit_breaker is not None:
        # PyBreaker holds a lock for the whole call, so one call per breaker at a time.
        # Revisit if calling view becomes async.
        return initialized_adapter.circuit_breaker.call(initialized_adapter.adapter.verify, request)
    return initialized_adapter.adapter.verify(request)


engine = AdapterEngine(registry)
