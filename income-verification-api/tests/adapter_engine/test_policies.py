import pytest
from django.core.exceptions import ImproperlyConfigured

from adapter_engine.policies import (
    CircuitBreakerPolicy,
    ExponentialBackoff,
    FixedBackoff,
    RetryPolicy,
    parse_circuit_breaker_policy,
    parse_retry_policy,
)


def test_none_retry_policy_is_off() -> None:
    assert parse_retry_policy("stub", None) is None


@pytest.mark.parametrize("raw_value", [False, {}, 0])
def test_other_falsy_retry_policy_is_invalid(raw_value: object) -> None:
    with pytest.raises(
        ImproperlyConfigured,
        match="income source adapter 'stub' retry_policy is invalid",
    ):
        parse_retry_policy("stub", raw_value)


def test_parses_fixed_retry_policy() -> None:
    assert parse_retry_policy(
        "stub",
        {
            "max_attempts": 3,
            "backoff": {"strategy": "fixed", "seconds": 0},
        },
    ) == RetryPolicy(max_attempts=3, backoff=FixedBackoff(seconds=0.0))


def test_parses_exponential_retry_policy() -> None:
    assert parse_retry_policy(
        "stub",
        {
            "max_attempts": 4,
            "backoff": {
                "strategy": "exponential",
                "initial_seconds": 0.5,
                "max_seconds": 4,
            },
        },
    ) == RetryPolicy(
        max_attempts=4,
        backoff=ExponentialBackoff(initial_seconds=0.5, max_seconds=4.0),
    )


@pytest.mark.parametrize(
    ("raw_value", "expected_message"),
    [
        ("invalid", "mapping"),
        (
            {"max_attempts": True, "backoff": {"strategy": "fixed", "seconds": 0}},
            "max_attempts",
        ),
        (
            {"max_attempts": 0, "backoff": {"strategy": "fixed", "seconds": 0}},
            "max_attempts",
        ),
        ({"backoff": {"strategy": "fixed", "seconds": 0}}, "max_attempts"),
        ({"max_attempts": 1}, "backoff"),
        ({"max_attempts": 1, "backoff": []}, "mapping"),
        ({"max_attempts": 1, "backoff": {"strategy": "unknown"}}, "unknown"),
        ({"max_attempts": 1, "backoff": {"strategy": "fixed"}}, "seconds"),
        (
            {"max_attempts": 1, "backoff": {"strategy": "fixed", "seconds": -1}},
            "seconds",
        ),
        (
            {
                "max_attempts": 1,
                "backoff": {
                    "strategy": "exponential",
                    "initial_seconds": 0,
                    "max_seconds": 1,
                },
            },
            "initial_seconds",
        ),
        (
            {
                "max_attempts": 1,
                "backoff": {
                    "strategy": "exponential",
                    "initial_seconds": 2,
                    "max_seconds": 1,
                },
            },
            "max_seconds",
        ),
        (
            {
                "max_attempts": 1,
                "backoff": {"strategy": "fixed", "seconds": 0, "typo": True},
            },
            "typo",
        ),
        (
            {
                "max_attempts": 1,
                "backoff": {"strategy": "fixed", "seconds": 0},
                "typo": True,
            },
            "typo",
        ),
    ],
)
def test_rejects_invalid_retry_policy(raw_value: object, expected_message: str) -> None:
    with pytest.raises(ImproperlyConfigured, match=expected_message):
        parse_retry_policy("stub", raw_value)


def test_none_circuit_breaker_is_off() -> None:
    assert parse_circuit_breaker_policy("stub", None) is None


@pytest.mark.parametrize("raw_value", [False, {}, 0])
def test_other_falsy_circuit_breaker_is_invalid(raw_value: object) -> None:
    with pytest.raises(
        ImproperlyConfigured,
        match="income source adapter 'stub' circuit_breaker is invalid",
    ):
        parse_circuit_breaker_policy("stub", raw_value)


def test_parses_circuit_breaker_policy() -> None:
    assert parse_circuit_breaker_policy(
        "stub",
        {"failure_threshold": 5, "reset_timeout_seconds": 30},
    ) == CircuitBreakerPolicy(failure_threshold=5, reset_timeout_seconds=30.0)


@pytest.mark.parametrize(
    ("raw_value", "expected_message"),
    [
        ("invalid", "mapping"),
        ({"failure_threshold": True, "reset_timeout_seconds": 1}, "failure_threshold"),
        ({"failure_threshold": 0, "reset_timeout_seconds": 1}, "failure_threshold"),
        ({"reset_timeout_seconds": 1}, "failure_threshold"),
        ({"failure_threshold": 1}, "reset_timeout_seconds"),
        ({"failure_threshold": 1, "reset_timeout_seconds": False}, "reset_timeout_seconds"),
        ({"failure_threshold": 1, "reset_timeout_seconds": 0}, "reset_timeout_seconds"),
        (
            {"failure_threshold": 1, "reset_timeout_seconds": 1, "typo": True},
            "typo",
        ),
    ],
)
def test_rejects_invalid_circuit_breaker_policy(raw_value: object, expected_message: str) -> None:
    with pytest.raises(ImproperlyConfigured, match=expected_message):
        parse_circuit_breaker_policy("stub", raw_value)
