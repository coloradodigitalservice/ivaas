"""Provider-neutral authentication and IVaaS agency authorization."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from django.http import HttpRequest
from ninja.security.base import AuthBase

from income_verification.request_context import set_agency_log_context


@dataclass(frozen=True, slots=True)
class VerifiedClient:
    """Machine identity and scopes asserted by a trusted token provider."""

    client_id: str
    scopes: frozenset[str]


@dataclass(frozen=True, slots=True)
class AuthenticatedAgency:
    """IVaaS principal resolved from a verified and authorized API client."""

    client_id: str
    agency_id: str
    scopes: frozenset[str]


class AuthFailureReason(StrEnum):
    """IVaaS-owned, credential-safe authentication telemetry vocabulary."""

    MISSING_CREDENTIALS = "missing_credentials"
    MALFORMED_CREDENTIALS = "malformed_credentials"
    INVALID_TOKEN = "invalid_token"  # noqa: S105 - telemetry reason, not a secret
    EXPIRED_TOKEN = "expired_token"  # noqa: S105 - telemetry reason, not a secret
    INVALID_ISSUER = "invalid_issuer"
    INVALID_TOKEN_USE = "invalid_token_use"  # noqa: S105 - telemetry reason, not a secret
    INSUFFICIENT_SCOPE = "insufficient_scope"
    UNKNOWN_CLIENT = "unknown_client"
    JWKS_UNAVAILABLE = "jwks_unavailable"


class AuthenticationFailure(Exception):
    """A credential could not be authenticated."""

    def __init__(self, reason: AuthFailureReason) -> None:
        super().__init__("authentication failed")
        self.reason = reason


class AuthorizationFailure(Exception):
    """An authenticated credential is not authorized to call IVaaS."""

    def __init__(self, reason: AuthFailureReason) -> None:
        super().__init__("authorization failed")
        self.reason = reason


class AuthenticationInfrastructureFailure(Exception):
    """Authentication could not proceed because trusted infrastructure was unavailable."""

    def __init__(self, reason: AuthFailureReason) -> None:
        super().__init__("authentication infrastructure unavailable")
        self.reason = reason


class AccessTokenVerifier(Protocol):
    """Verify an opaque token into a provider identity."""

    def verify(self, token: str) -> VerifiedClient: ...


class AgencyResolver(Protocol):
    """Resolve a verified provider client ID to an onboarded IVaaS agency."""

    def resolve(self, client_id: str) -> str | None: ...


class ConfiguredAgencyResolver:
    """Configuration-backed resolver replaceable by a durable onboarding store."""

    def __init__(self, agencies_by_client_id: Mapping[str, str]) -> None:
        self._agencies_by_client_id = dict(agencies_by_client_id)

    def resolve(self, client_id: str) -> str | None:
        return self._agencies_by_client_id.get(client_id)


class AgencyAuthenticator:
    """Apply IVaaS scope and agency authorization to a verified client."""

    def __init__(
        self,
        *,
        token_verifier: AccessTokenVerifier,
        required_scope: str,
        agency_resolver: AgencyResolver,
    ) -> None:
        self._token_verifier = token_verifier
        self._required_scope = required_scope
        self._agency_resolver = agency_resolver

    def authenticate(self, token: str) -> AuthenticatedAgency:
        client = self._token_verifier.verify(token)
        if self._required_scope not in client.scopes:
            raise AuthorizationFailure(AuthFailureReason.INSUFFICIENT_SCOPE)

        agency_id = self._agency_resolver.resolve(client.client_id)
        if agency_id is None:
            raise AuthorizationFailure(AuthFailureReason.UNKNOWN_CLIENT)

        return AuthenticatedAgency(
            client_id=client.client_id,
            agency_id=agency_id,
            scopes=client.scopes,
        )


class AgencyOAuth2ClientCredentials(AuthBase):
    """Ninja Bearer-token adapter documented as an OAuth2 client-credentials flow."""

    openapi_type = "oauth2"

    def __init__(
        self,
        authenticator: AgencyAuthenticator,
        *,
        token_url: str,
        required_scope: str,
    ) -> None:
        self.authenticator = authenticator
        self.required_scope = required_scope
        self.openapi_description = (
            "Machine-to-machine Bearer access token. The verified client_id is resolved "
            "to an onboarded IVaaS agency."
        )
        self.openapi_flows = {
            "clientCredentials": {
                "tokenUrl": token_url,
                "scopes": {
                    required_scope: "Submit income verification requests.",
                },
            }
        }
        super().__init__()

    def __call__(self, request: HttpRequest) -> AuthenticatedAgency:
        authorization = request.headers.get("Authorization")
        if authorization is None:
            raise AuthenticationFailure(AuthFailureReason.MISSING_CREDENTIALS)

        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
            raise AuthenticationFailure(AuthFailureReason.MALFORMED_CREDENTIALS)

        principal = self.authenticator.authenticate(parts[1])
        set_agency_log_context(principal.agency_id)
        return principal


def get_authenticated_agency(request: HttpRequest) -> AuthenticatedAgency:
    """Return Ninja's provider-neutral principal, failing closed if it is absent."""
    principal = request.__dict__.get("auth")
    if not isinstance(principal, AuthenticatedAgency):
        raise AuthenticationFailure(AuthFailureReason.INVALID_TOKEN)
    return principal
