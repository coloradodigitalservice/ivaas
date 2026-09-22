"""Shared builders for authentication tests."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from jwt.types import JWKDict

from income_verification.security import (
    AuthenticationFailure,
    AuthenticationInfrastructureFailure,
    AuthFailureReason,
    AuthorizationFailure,
)
from income_verification.security.authentication import (
    AccessTokenVerifier,
    AgencyAuthenticator,
    ConfiguredAgencyResolver,
    VerifiedClient,
)
from income_verification.security.cognito import CognitoAccessTokenVerifier, SigningKeyProvider

ISSUER = "https://cognito-idp.us-west-2.amazonaws.com/test-pool"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
REQUIRED_SCOPE = "ivaas/income.verify"
TEST_CLIENT_ID = "test-client"
TEST_AGENCY_ID = "test-agency"
TEST_ACCESS_TOKEN = "test-access-token"  # noqa: S105 - deterministic test credential
OAUTH_ENDPOINT = "https://example.invalid/oauth2"

type AuthenticationException = (
    AuthenticationFailure | AuthenticationInfrastructureFailure | AuthorizationFailure
)


class StaticSigningKeyProvider(SigningKeyProvider):
    def __init__(self, signing_key: jwt.PyJWK) -> None:
        self.signing_key = signing_key

    def get_signing_key(self, token: str) -> jwt.PyJWK:
        return self.signing_key


class AcceptingAccessTokenVerifier(AccessTokenVerifier):
    """Return a configured verified client without inspecting the supplied token."""

    def __init__(
        self,
        *,
        client_id: str = TEST_CLIENT_ID,
        scopes: frozenset[str] = frozenset({REQUIRED_SCOPE}),
    ) -> None:
        self.client_id = client_id
        self.scopes = scopes

    def verify(self, token: str) -> VerifiedClient:
        return VerifiedClient(client_id=self.client_id, scopes=self.scopes)


def public_jwk(private_key: rsa.RSAPrivateKey, *, kid: str = "test-key") -> JWKDict:
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return jwk


def access_token(
    private_key: rsa.RSAPrivateKey,
    **claim_overrides: object,
) -> str:
    claims: dict[str, object] = {
        "iss": ISSUER,
        "exp": datetime.now(tz=UTC) + timedelta(minutes=5),
        "token_use": "access",
        "client_id": TEST_CLIENT_ID,
        "scope": f"openid {REQUIRED_SCOPE}",
        "sentinel_custom_claim": "SENTINEL-PRIVATE-JWT-CLAIM",
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def access_token_without_claim(private_key: rsa.RSAPrivateKey, claim: str) -> str:
    claims = jwt.decode(access_token(private_key), options={"verify_signature": False})
    del claims[claim]
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def cognito_authenticator(
    signing_key: jwt.PyJWK,
    *,
    agencies: dict[str, str] | None = None,
) -> AgencyAuthenticator:
    return AgencyAuthenticator(
        token_verifier=CognitoAccessTokenVerifier(
            issuer=ISSUER,
            signing_key_provider=StaticSigningKeyProvider(signing_key),
        ),
        required_scope=REQUIRED_SCOPE,
        agency_resolver=ConfiguredAgencyResolver(
            {TEST_CLIENT_ID: TEST_AGENCY_ID} if agencies is None else agencies
        ),
    )


def agency_authenticator(
    *,
    client_id: str = TEST_CLIENT_ID,
    scopes: frozenset[str] | None = None,
    agencies: dict[str, str] | None = None,
) -> AgencyAuthenticator:
    return AgencyAuthenticator(
        token_verifier=AcceptingAccessTokenVerifier(
            client_id=client_id, scopes=frozenset({REQUIRED_SCOPE}) if scopes is None else scopes
        ),
        required_scope=REQUIRED_SCOPE,
        agency_resolver=ConfiguredAgencyResolver(
            {TEST_CLIENT_ID: TEST_AGENCY_ID} if agencies is None else agencies
        ),
    )


def assert_failure_reason(
    expected_exception: type[AuthenticationException],
    expected_reason: AuthFailureReason,
    function: Callable[[], object],
) -> None:
    with pytest.raises(expected_exception) as caught:
        function()
    failure = cast(AuthenticationException, caught.value)
    assert failure.reason is expected_reason
