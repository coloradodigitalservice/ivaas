import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import PyJWKClientError, PyJWKSetError

from income_verification.security import (
    AuthenticatedAgency,
    AuthenticationFailure,
    AuthenticationInfrastructureFailure,
    AuthFailureReason,
    AuthorizationFailure,
)
from income_verification.security.authentication import (
    AgencyAuthenticator,
    ConfiguredAgencyResolver,
)
from income_verification.security.cognito import (
    CognitoAccessTokenVerifier,
    CognitoJwksKeyProvider,
    SigningKeyNotFoundError,
    SigningKeyUnavailableError,
)
from tests.income_verification.security.authentication_test_support import (
    AGENCY_ID,
    CLIENT_ID,
    ISSUER,
    JWKS_URL,
    REQUIRED_SCOPE,
    access_token,
    access_token_without_claim,
    assert_failure_reason,
    cognito_authenticator,
    public_jwk,
)


def test_valid_cognito_access_token_resolves_known_agency(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
) -> None:
    private_key, signing_key = rsa_keys

    principal = cognito_authenticator(signing_key).authenticate(access_token(private_key))

    assert principal == AuthenticatedAgency(
        client_id=CLIENT_ID,
        agency_id=AGENCY_ID,
        scopes=frozenset({"openid", REQUIRED_SCOPE}),
    )


def test_cognito_jwks_provider_uses_expected_url_and_cache() -> None:
    with patch("income_verification.security.cognito.jwt.PyJWKClient") as client_class:
        CognitoJwksKeyProvider(JWKS_URL, cache_seconds=600, timeout_seconds=4.5)

    client_class.assert_called_once_with(
        JWKS_URL,
        cache_keys=False,
        cache_jwk_set=True,
        lifespan=600,
        timeout=4.5,
    )


def test_cognito_jwks_provider_reuses_cached_jwks_document(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
) -> None:
    private_key, _ = rsa_keys
    provider = CognitoJwksKeyProvider(JWKS_URL, cache_seconds=600, timeout_seconds=5)
    encoded_token = access_token(private_key)
    jwks_response = StringIO(json.dumps({"keys": [public_jwk(private_key)]}))
    with patch("urllib.request.urlopen", return_value=jwks_response) as network_call:
        first_key = provider.get_signing_key(encoded_token)
        second_key = provider.get_signing_key(encoded_token)

    assert first_key.key_id == "test-key"
    assert second_key.key_id == "test-key"
    network_call.assert_called_once()


def test_unknown_kid_refreshes_jwks_then_is_unauthorized(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
) -> None:
    private_key, _ = rsa_keys
    claims = jwt.decode(access_token(private_key), options={"verify_signature": False})
    unknown_kid_token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "unknown-key"},
    )
    provider = CognitoJwksKeyProvider(JWKS_URL, cache_seconds=600, timeout_seconds=5)
    authenticator = AgencyAuthenticator(
        token_verifier=CognitoAccessTokenVerifier(
            issuer=ISSUER,
            signing_key_provider=provider,
        ),
        required_scope=REQUIRED_SCOPE,
        agency_resolver=ConfiguredAgencyResolver({CLIENT_ID: AGENCY_ID}),
    )
    with patch.object(
        provider._client,
        "fetch_data",
        return_value={"keys": [public_jwk(private_key)]},
    ) as fetch_data:
        assert_failure_reason(
            AuthenticationFailure,
            AuthFailureReason.INVALID_TOKEN,
            lambda: authenticator.authenticate(unknown_kid_token),
        )

    assert fetch_data.call_count == 2


def test_removed_signing_key_is_not_retained_outside_the_jwks_cache(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
) -> None:
    private_key, original_signing_key = rsa_keys
    replacement_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    replacement_signing_key = jwt.PyJWK.from_dict(
        public_jwk(replacement_private_key, kid="replacement-key")
    )
    provider = CognitoJwksKeyProvider(JWKS_URL, cache_seconds=600, timeout_seconds=5)
    encoded_token = access_token(private_key)

    with patch.object(
        provider._client,
        "get_signing_keys",
        side_effect=[
            [original_signing_key],
            [replacement_signing_key],
            [replacement_signing_key],
        ],
    ):
        assert provider.get_signing_key(encoded_token) is original_signing_key
        with pytest.raises(SigningKeyNotFoundError):
            provider.get_signing_key(encoded_token)


@pytest.mark.parametrize(
    ("claims", "reason"),
    [
        ({"exp": datetime.now(tz=UTC) - timedelta(seconds=1)}, AuthFailureReason.EXPIRED_TOKEN),
        (
            {"iss": "https://sentinel-wrong-issuer.example"},
            AuthFailureReason.INVALID_ISSUER,
        ),
        ({"token_use": "id"}, AuthFailureReason.INVALID_TOKEN_USE),
        ({"scope": 42}, AuthFailureReason.MALFORMED_CREDENTIALS),
    ],
)
def test_cognito_claim_failures_use_owned_reasons(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
    claims: dict[str, object],
    reason: AuthFailureReason,
) -> None:
    private_key, signing_key = rsa_keys
    authenticator = cognito_authenticator(signing_key)

    assert_failure_reason(
        AuthenticationFailure,
        reason,
        lambda: authenticator.authenticate(access_token(private_key, **claims)),
    )


def test_cognito_rejects_missing_client_id(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
) -> None:
    private_key, signing_key = rsa_keys
    authenticator = cognito_authenticator(signing_key)
    missing_client_token = access_token_without_claim(private_key, "client_id")

    assert_failure_reason(
        AuthenticationFailure,
        AuthFailureReason.MALFORMED_CREDENTIALS,
        lambda: authenticator.authenticate(missing_client_token),
    )


def test_cognito_rejects_invalid_signature(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
) -> None:
    _, signing_key = rsa_keys
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    authenticator = cognito_authenticator(signing_key)

    assert_failure_reason(
        AuthenticationFailure,
        AuthFailureReason.INVALID_TOKEN,
        lambda: authenticator.authenticate(access_token(other_private_key)),
    )


@pytest.mark.parametrize("algorithm", ["none", "HS256"])
def test_cognito_allows_only_rs256(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
    algorithm: str,
) -> None:
    private_key, signing_key = rsa_keys
    authenticator = cognito_authenticator(signing_key)
    claims = jwt.decode(access_token(private_key), options={"verify_signature": False})
    wrong_algorithm_token = jwt.encode(
        claims,
        key="" if algorithm == "none" else "symmetric-test-key-at-least-32-bytes",
        algorithm=algorithm,
        headers={"kid": "test-key"},
    )

    assert_failure_reason(
        AuthenticationFailure,
        AuthFailureReason.INVALID_TOKEN,
        lambda: authenticator.authenticate(wrong_algorithm_token),
    )


def test_cognito_treats_missing_scope_as_forbidden(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
) -> None:
    private_key, signing_key = rsa_keys
    authenticator = cognito_authenticator(signing_key)

    assert_failure_reason(
        AuthorizationFailure,
        AuthFailureReason.INSUFFICIENT_SCOPE,
        lambda: authenticator.authenticate(access_token_without_claim(private_key, "scope")),
    )


def test_cognito_jwks_connection_failure_is_infrastructure_failure(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
) -> None:
    private_key, _ = rsa_keys

    class UnavailableSigningKeyProvider:
        def get_signing_key(self, token: str) -> jwt.PyJWK:
            raise SigningKeyUnavailableError("SENTINEL-JWKS-CONNECTION-DETAIL")

    authenticator = AgencyAuthenticator(
        token_verifier=CognitoAccessTokenVerifier(
            issuer=ISSUER,
            signing_key_provider=UnavailableSigningKeyProvider(),
        ),
        required_scope=REQUIRED_SCOPE,
        agency_resolver=ConfiguredAgencyResolver({CLIENT_ID: AGENCY_ID}),
    )

    assert_failure_reason(
        AuthenticationInfrastructureFailure,
        AuthFailureReason.JWKS_UNAVAILABLE,
        lambda: authenticator.authenticate(access_token(private_key)),
    )


@pytest.mark.parametrize(
    "provider_error",
    [
        PyJWKClientError("SENTINEL-INVALID-JWKS-SHAPE"),
        PyJWKSetError("SENTINEL-UNUSABLE-JWKS"),
        json.JSONDecodeError("SENTINEL-MALFORMED-JWKS", "", 0),
    ],
)
def test_cognito_jwks_provider_normalizes_invalid_provider_responses(
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
    provider_error: Exception,
) -> None:
    private_key, _ = rsa_keys
    provider = CognitoJwksKeyProvider(JWKS_URL, cache_seconds=600, timeout_seconds=5)

    with (
        patch.object(provider._client, "get_signing_keys", side_effect=provider_error),
        pytest.raises(SigningKeyUnavailableError),
    ):
        provider.get_signing_key(access_token(private_key))
