"""AWS Cognito access-token and signing-key verification."""

from typing import Protocol

import jwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidIssuerError,
    InvalidSignatureError,
    MissingRequiredClaimError,
    PyJWKClientError,
    PyJWKSetError,
    PyJWTError,
)

from income_verification.security.authentication import (
    AuthenticationFailure,
    AuthenticationInfrastructureFailure,
    AuthFailureReason,
    VerifiedClient,
)


class SigningKeyProvider(Protocol):
    """Resolve the signing key for an encoded JWT."""

    def get_signing_key(self, token: str) -> jwt.PyJWK: ...


class SigningKeyNotFoundError(Exception):
    """The token names a key that the trusted provider does not publish."""


class SigningKeyUnavailableError(Exception):
    """The trusted signing-key provider could not supply a usable key set."""


class CognitoJwksKeyProvider:
    """Retrieve and cache Cognito signing keys through PyJWT's JWKS client."""

    def __init__(self, jwks_url: str, cache_seconds: float, timeout_seconds: float) -> None:
        self._client = jwt.PyJWKClient(
            jwks_url,
            # The document cache alone gives removed keys a bounded trust lifetime. PyJWT's
            # per-key LRU cache does not expire, so it is intentionally disabled.
            cache_keys=False,
            cache_jwk_set=True,
            lifespan=cache_seconds,
            timeout=timeout_seconds,
        )

    def get_signing_key(self, token: str) -> jwt.PyJWK:
        header = jwt.get_unverified_header(token)
        key_id = header.get("kid")
        if not isinstance(key_id, str) or not key_id:
            raise DecodeError("token header must contain a non-empty kid")

        signing_key = jwt.PyJWKClient.match_kid(self._get_signing_keys(), key_id)
        if signing_key is not None:
            return signing_key

        # A new key ID is expected during normal rotation. Refresh once before rejecting it.
        signing_key = jwt.PyJWKClient.match_kid(
            self._get_signing_keys(refresh=True),
            key_id,
        )
        if signing_key is None:
            raise SigningKeyNotFoundError("token signing key is not published")
        return signing_key

    def _get_signing_keys(self, *, refresh: bool = False) -> list[jwt.PyJWK]:
        try:
            return self._client.get_signing_keys(refresh=refresh)
        except (PyJWKClientError, PyJWKSetError, TypeError, ValueError) as exc:
            # Raw provider errors can contain unsafe upstream content.
            raise SigningKeyUnavailableError("signing key provider is unavailable") from exc


class CognitoAccessTokenVerifier:
    """Verify an AWS Cognito access token into a provider-neutral client."""

    def __init__(self, *, issuer: str, signing_key_provider: SigningKeyProvider) -> None:
        self._issuer = issuer
        self._signing_key_provider = signing_key_provider

    def verify(self, token: str) -> VerifiedClient:
        try:
            signing_key = self._signing_key_provider.get_signing_key(token)
        except SigningKeyUnavailableError as exc:
            raise AuthenticationInfrastructureFailure(AuthFailureReason.JWKS_UNAVAILABLE) from exc
        except SigningKeyNotFoundError as exc:
            raise AuthenticationFailure(AuthFailureReason.INVALID_TOKEN) from exc
        except (DecodeError, TypeError, ValueError) as exc:
            raise AuthenticationFailure(AuthFailureReason.MALFORMED_CREDENTIALS) from exc

        try:
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={
                    "require": ["exp", "iss", "token_use", "client_id"],
                    # Cognito client-credentials access tokens do not necessarily carry aud.
                    "verify_aud": False,
                },
            )
        except ExpiredSignatureError as exc:
            raise AuthenticationFailure(AuthFailureReason.EXPIRED_TOKEN) from exc
        except InvalidIssuerError as exc:
            raise AuthenticationFailure(AuthFailureReason.INVALID_ISSUER) from exc
        except InvalidSignatureError as exc:
            raise AuthenticationFailure(AuthFailureReason.INVALID_TOKEN) from exc
        except (DecodeError, MissingRequiredClaimError) as exc:
            raise AuthenticationFailure(AuthFailureReason.MALFORMED_CREDENTIALS) from exc
        except (PyJWTError, TypeError, ValueError) as exc:
            raise AuthenticationFailure(AuthFailureReason.INVALID_TOKEN) from exc

        if claims.get("token_use") != "access":
            raise AuthenticationFailure(AuthFailureReason.INVALID_TOKEN_USE)

        client_id = claims.get("client_id")
        scope_claim = claims.get("scope")
        if not isinstance(client_id, str) or not client_id:
            raise AuthenticationFailure(AuthFailureReason.MALFORMED_CREDENTIALS)
        if scope_claim is None:
            scopes = frozenset[str]()
        elif isinstance(scope_claim, str):
            scopes = frozenset(scope_claim.split())
        else:
            raise AuthenticationFailure(AuthFailureReason.MALFORMED_CREDENTIALS)

        return VerifiedClient(client_id=client_id, scopes=scopes)
