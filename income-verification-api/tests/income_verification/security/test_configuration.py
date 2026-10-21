from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured

from income_verification.security.configuration import (
    AuthenticationConfig,
    build_api_authentication,
)
from tests.income_verification.security.authentication_test_support import (
    ISSUER,
    JWKS_URL,
    OAUTH_ENDPOINT,
    REQUIRED_SCOPE,
    TEST_CLIENT_ID,
    TEST_PROGRAM_ID,
)


def authentication_configuration(**overrides: object) -> dict[str, object]:
    configuration: dict[str, object] = {
        "ISSUER": ISSUER,
        "JWKS_URL": JWKS_URL,
        "TOKEN_URL": OAUTH_ENDPOINT,
        "REQUIRED_SCOPE": REQUIRED_SCOPE,
        "CLIENT_PROGRAM_MAP": {TEST_CLIENT_ID: TEST_PROGRAM_ID},
        "JWKS_CACHE_SECONDS": 300,
        "JWKS_TIMEOUT_SECONDS": 5,
    }
    configuration.update(overrides)
    return configuration


def test_configuration_requires_an_onboarded_client() -> None:
    with pytest.raises(
        ImproperlyConfigured,
        match=r"API_AUTHENTICATION\.CLIENT_PROGRAM_MAP",
    ):
        AuthenticationConfig.from_mapping(authentication_configuration(CLIENT_PROGRAM_MAP={}))


@pytest.mark.parametrize("key", ["ISSUER", "JWKS_URL", "TOKEN_URL", "REQUIRED_SCOPE"])
def test_configuration_requires_endpoint_and_scope_strings(key: str) -> None:
    with pytest.raises(ImproperlyConfigured, match=f"API_AUTHENTICATION.{key}"):
        AuthenticationConfig.from_mapping(authentication_configuration(**{key: ""}))


@pytest.mark.parametrize(
    ("setting_name", "setting_value"),
    [("JWKS_CACHE_SECONDS", 0), ("JWKS_TIMEOUT_SECONDS", -1)],
)
def test_configuration_requires_positive_jwks_durations(
    setting_name: str,
    setting_value: int,
) -> None:
    with pytest.raises(ImproperlyConfigured, match=setting_name):
        AuthenticationConfig.from_mapping(
            authentication_configuration(**{setting_name: setting_value})
        )


def test_build_wires_explicit_jwks_configuration() -> None:
    with patch(
        "income_verification.security.configuration.CognitoJwksKeyProvider"
    ) as provider_class:
        authentication = build_api_authentication(authentication_configuration())

    provider_class.assert_called_once_with(JWKS_URL, cache_seconds=300.0, timeout_seconds=5.0)
    assert authentication.required_scope == REQUIRED_SCOPE
