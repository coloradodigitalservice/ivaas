from functools import partial

import pybreaker
from ivaas_core import SourceIncome, SourceUnavailable, VerificationRequest

from adapter_engine.registry import AdapterRegistry, registry


class AdapterEngine:
    """Run adapter calls through their configured execution policies."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def verify(self, name: str, request: VerificationRequest) -> SourceIncome:
        """Verify income through one registered adapter."""
        initialized_adapter = self._registry.get_adapter(name)
        if initialized_adapter.circuit_breaker:
            call = partial(
                initialized_adapter.circuit_breaker.call,
                initialized_adapter.adapter.verify,
                request,
            )
        else:
            call = partial(initialized_adapter.adapter.verify, request)
        try:
            if initialized_adapter.retrying:
                return initialized_adapter.retrying(call)
            return call()
        except pybreaker.CircuitBreakerError:
            raise SourceUnavailable(f"{name} circuit breaker is open") from None


engine = AdapterEngine(registry)
