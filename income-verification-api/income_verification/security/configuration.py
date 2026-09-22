"""Authentication configuration validation and object composition."""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from math import isfinite
from types import MappingProxyType

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from income_verification.security.authentication import (
    AgencyAuthenticator,
    AgencyOAuth2ClientCredentials,
    ConfiguredAgencyResolver,
)
from income_verification.security.cognito import CognitoAccessTokenVerifier, CognitoJwksKeyProvider


@dataclass(frozen=True, slots=True)
class AuthenticationConfig:
    """Validated settings needed to construct program-facing authentication."""

    issuer: str
    jwks_url: str
    token_url: str
    required_scope: str
    client_agency_map: Mapping[str, str]
    jwks_cache_seconds: float
    jwks_timeout_seconds: float

    @classmethod
    def from_mapping(cls, value: object) -> AuthenticationConfig:
        """Validate a Django setting mapping into typed immutable configuration."""
        if not isinstance(value, Mapping):
            raise ImproperlyConfigured("API_AUTHENTICATION must be a mapping")

        return cls(
            issuer=_required_string(value, "ISSUER"),
            jwks_url=_required_string(value, "JWKS_URL"),
            token_url=_required_string(value, "TOKEN_URL"),
            required_scope=_required_string(value, "REQUIRED_SCOPE"),
            client_agency_map=MappingProxyType(_agency_mapping(value.get("CLIENT_AGENCY_MAP"))),
            jwks_cache_seconds=_positive_seconds(value, "JWKS_CACHE_SECONDS"),
            jwks_timeout_seconds=_positive_seconds(value, "JWKS_TIMEOUT_SECONDS"),
        )


def _required_string(configuration: Mapping[object, object], key: str) -> str:
    value = configuration.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise ImproperlyConfigured(f"API_AUTHENTICATION.{key} must be configured")


def _agency_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ImproperlyConfigured(
            "API_AUTHENTICATION.CLIENT_AGENCY_MAP must map non-empty client IDs to agency IDs"
        )
    if not all(
        isinstance(client_id, str)
        and bool(client_id.strip())
        and isinstance(agency_id, str)
        and bool(agency_id.strip())
        for client_id, agency_id in value.items()
    ):
        raise ImproperlyConfigured(
            "API_AUTHENTICATION.CLIENT_AGENCY_MAP must map non-empty client IDs to agency IDs"
        )
    return dict(value)


def _positive_seconds(configuration: Mapping[object, object], key: str) -> float:
    value = configuration.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        seconds = float(value)
        if isfinite(seconds) and seconds > 0:
            return seconds
    raise ImproperlyConfigured(f"API_AUTHENTICATION.{key} must be greater than zero")


def build_api_authentication(
    configuration: object | None = None,
) -> AgencyOAuth2ClientCredentials:
    """Build the configured authentication implementation, failing closed."""
    authentication_config = AuthenticationConfig.from_mapping(
        settings.API_AUTHENTICATION if configuration is None else configuration
    )
    token_verifier = CognitoAccessTokenVerifier(
        issuer=authentication_config.issuer,
        signing_key_provider=CognitoJwksKeyProvider(
            authentication_config.jwks_url,
            cache_seconds=authentication_config.jwks_cache_seconds,
            timeout_seconds=authentication_config.jwks_timeout_seconds,
        ),
    )
    authenticator = AgencyAuthenticator(
        token_verifier=token_verifier,
        required_scope=authentication_config.required_scope,
        agency_resolver=ConfiguredAgencyResolver(authentication_config.client_agency_map),
    )
    return AgencyOAuth2ClientCredentials(
        authenticator,
        token_url=authentication_config.token_url,
        required_scope=authentication_config.required_scope,
    )


@cache
def get_api_authentication() -> AgencyOAuth2ClientCredentials:
    """Return the per-process authentication object built during application startup.

    AppConfig.ready() initializes this zero-argument cache eagerly. Later imports by
    the Ninja API and route metadata reuse the same object, including its bounded
    JWKS cache, rather than constructing independent authentication state.
    """
    return build_api_authentication()
