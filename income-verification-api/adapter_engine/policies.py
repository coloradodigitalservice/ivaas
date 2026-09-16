"""Validated policies and adapter records used by the registry."""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

import pybreaker
from django.core.exceptions import ImproperlyConfigured
from ivaas_core import IncomeSourceAdapter, SourceTimeout, SourceUnavailable
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    wait_fixed,
)

logger = logging.getLogger(__name__)

RETRYABLE = (SourceTimeout, SourceUnavailable)


@dataclass(frozen=True)
class FixedBackoff:
    """The same pause before every retry."""

    seconds: float

    def __post_init__(self) -> None:
        if type(self.seconds) not in (int, float) or self.seconds < 0:
            raise ValueError("seconds must be a number greater than or equal to 0")


@dataclass(frozen=True)
class ExponentialBackoff:
    """A pause that doubles after each retry, with jitter (a small random extra), up to a cap."""

    initial_seconds: float
    max_seconds: float

    def __post_init__(self) -> None:
        if type(self.initial_seconds) not in (int, float) or self.initial_seconds <= 0:
            raise ValueError("initial_seconds must be a number greater than 0")
        if type(self.max_seconds) not in (int, float) or self.max_seconds < self.initial_seconds:
            raise ValueError(
                "max_seconds must be a number greater than or equal to initial_seconds"
            )


@dataclass(frozen=True)
class RetryPolicy:
    """How many times to call an adapter and how long to pause between calls."""

    max_attempts: int
    backoff: FixedBackoff | ExponentialBackoff

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("max_attempts must be an integer greater than or equal to 1")

    def build(self, name: str) -> Retrying:
        """Build the retry loop for the adapter named `name`, logging every failed attempt."""

        def log_failed_attempt(retry_state: RetryCallState) -> None:
            failure = retry_state.outcome.exception() if retry_state.outcome is not None else None
            logger.warning(
                "income source adapter %r attempt %d of %d failed: %s: %s",
                name,
                retry_state.attempt_number,
                self.max_attempts,
                type(failure).__name__,
                failure,
            )

        backoff = self.backoff
        wait = (
            wait_fixed(backoff.seconds)
            if isinstance(backoff, FixedBackoff)
            else wait_exponential_jitter(
                initial=backoff.initial_seconds,
                max=backoff.max_seconds,
            )
        )
        return Retrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait,
            retry=retry_if_exception_type(RETRYABLE),
            reraise=True,
            after=log_failed_attempt,
        )


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    """When to stop calling an adapter and when to try it again."""

    failure_threshold: int
    reset_timeout_seconds: float

    def __post_init__(self) -> None:
        if type(self.failure_threshold) is not int or self.failure_threshold < 1:
            raise ValueError("failure_threshold must be an integer greater than or equal to 1")
        if type(self.reset_timeout_seconds) not in (int, float) or self.reset_timeout_seconds <= 0:
            raise ValueError("reset_timeout_seconds must be a number greater than 0")

    def build(self) -> pybreaker.CircuitBreaker:
        return pybreaker.CircuitBreaker(
            fail_max=self.failure_threshold,
            reset_timeout=self.reset_timeout_seconds,
            exclude=[lambda error: not isinstance(error, RETRYABLE)],
        )


@dataclass(frozen=True)
class InitializedAdapter:
    """An enabled adapter with its retry loop and circuit breaker built, or None where off."""

    adapter: IncomeSourceAdapter
    retrying: Retrying | None
    circuit_breaker: pybreaker.CircuitBreaker | None


_BACKOFF_TYPES: dict[str, Callable[..., FixedBackoff | ExponentialBackoff]] = {
    "fixed": FixedBackoff,
    "exponential": ExponentialBackoff,
}


def parse_retry_policy(name: str, raw_value: object) -> RetryPolicy | None:
    """Turn one adapter's retry_policy setting into a RetryPolicy; None means off."""
    if raw_value is None:
        return None
    try:
        values = {**cast(Mapping[str, object], raw_value)}
        backoff_values = {**cast(Mapping[str, object], values.pop("backoff"))}
        backoff_type = _BACKOFF_TYPES[cast(str, backoff_values.pop("strategy"))]
        backoff = backoff_type(**backoff_values)
        return RetryPolicy(backoff=backoff, **values)  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as error:
        raise ImproperlyConfigured(
            f"income source adapter {name!r} retry_policy is invalid: {error}"
        ) from error


def parse_circuit_breaker_policy(name: str, raw_value: object) -> CircuitBreakerPolicy | None:
    """Turn one adapter's circuit_breaker setting into a CircuitBreakerPolicy; None means off."""
    if raw_value is None:
        return None
    try:
        values = {**cast(Mapping[str, object], raw_value)}
        return CircuitBreakerPolicy(**values)  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as error:
        raise ImproperlyConfigured(
            f"income source adapter {name!r} circuit_breaker is invalid: {error}"
        ) from error
