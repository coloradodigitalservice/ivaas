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
        """Verify income through one registered adapter."""
        initialized_adapter = self._registry.get_adapter(name)
        try:
            if initialized_adapter.retrying:
                return initialized_adapter.retrying(
                    self._attempt_verification_request, initialized_adapter, request
                )
            return self._attempt_verification_request(initialized_adapter, request)
        except pybreaker.CircuitBreakerError:
            raise SourceUnavailable(f"{name} circuit breaker is open") from None

    @staticmethod
    def _attempt_verification_request(
        initialized_adapter: InitializedAdapter, request: VerificationRequest
    ) -> SourceIncome:
        if initialized_adapter.circuit_breaker:
            return initialized_adapter.circuit_breaker.call(
                initialized_adapter.adapter.verify, request
            )
        return initialized_adapter.adapter.verify(request)


engine = AdapterEngine(registry)
