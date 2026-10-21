import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from io import StringIO

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.test import Client

from income_verification.api import api_authentication
from income_verification.api_error_codes import ERRORS, ErrorCode
from income_verification.request_context import JsonLogFormatter, RequestContextFilter
from income_verification.security import (
    AuthFailureReason,
    get_api_authentication,
)
from income_verification.security.authentication import (
    ConfiguredProgramResolver,
    ProgramAuthenticator,
)
from income_verification.security.cognito import (
    CognitoAccessTokenVerifier,
    SigningKeyUnavailableError,
)
from tests.income_verification.security.authentication_test_support import (
    ISSUER,
    REQUIRED_SCOPE,
    TEST_ACCESS_TOKEN,
    TEST_CLIENT_ID,
    TEST_PROGRAM_ID,
    access_token,
    cognito_authenticator,
    program_authenticator,
)

pytestmark = pytest.mark.usefixtures("configured_api_authentication")

API_ROOT = "/api"
INCOME_VERIFICATION_PATH = f"{API_ROOT}/{settings.API_VERSION}/income-verification"
TEST_CONNECTION_PATH = f"{API_ROOT}/{settings.API_VERSION}/test-connection"
CORRELATION_ID = "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31:auth-test"


def _authenticated_headers(**headers: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TEST_ACCESS_TOKEN}",
        "Correlation-Id": CORRELATION_ID,
        **headers,
    }


def _valid_request() -> dict[str, object]:
    return {
        "applicationId": "APP-AUTH-TEST",
        "firstName": "Test",
        "lastName": "Applicant",
        "last4Ssn": "1234",
        "lookbackPeriod": {"startDate": "2026-01-01", "endDate": "2026-06-30"},
    }


@contextmanager
def capture_api_logs() -> Generator[StringIO]:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("income_verification")
    original_handlers = logger.handlers
    logger.handlers = [handler]
    try:
        yield stream
    finally:
        logger.handlers = original_handlers


def test_income_verification_rejects_missing_auth_and_echoes_valid_correlation(
    client: Client,
) -> None:
    response = client.post(
        INCOME_VERIFICATION_PATH,
        data=json.dumps(_valid_request()),
        content_type="application/json",
        headers={"Correlation-Id": CORRELATION_ID},
    )

    definition = ERRORS[ErrorCode.AUTHENTICATION_REQUIRED]
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {
        "code": ErrorCode.AUTHENTICATION_REQUIRED.value,
        "message": definition.message,
    }
    assert response.headers["Correlation-Id"] == CORRELATION_ID
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="income-verification-api"'


def test_test_connection_returns_resolved_program_and_environment(client: Client) -> None:
    with capture_api_logs() as stream:
        response = client.get(TEST_CONNECTION_PATH, headers=_authenticated_headers())

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "authenticatedAs": TEST_PROGRAM_ID,
        "environment": settings.DEPLOYMENT_ENVIRONMENT,
    }
    assert response.headers["Correlation-Id"] == CORRELATION_ID
    record = json.loads(stream.getvalue())
    assert record["level"] == "INFO"
    assert record["message"] == "test connection request accepted"
    assert record["event.name"] == "test_connection.request.accepted"
    assert record["http.request.method"] == "GET"
    assert record["url.path"] == TEST_CONNECTION_PATH
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert record["auth.client.id"] == TEST_CLIENT_ID
    assert record["ivaas.program.id"] == TEST_PROGRAM_ID


def test_api_reuses_authentication_initialized_at_application_startup() -> None:
    assert get_api_authentication() is api_authentication


def test_test_connection_rejects_missing_authentication(client: Client) -> None:
    response = client.get(
        TEST_CONNECTION_PATH,
        headers={"Correlation-Id": CORRELATION_ID},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {
        "code": ErrorCode.AUTHENTICATION_REQUIRED.value,
        "message": ERRORS[ErrorCode.AUTHENTICATION_REQUIRED].message,
    }


def test_test_connection_rejects_invalid_access_token(client: Client) -> None:
    response = client.get(
        TEST_CONNECTION_PATH,
        headers={
            "Authorization": "Bearer invalid-access-token",
            "Correlation-Id": CORRELATION_ID,
        },
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {
        "code": ErrorCode.INVALID_AUTHENTICATION.value,
        "message": ERRORS[ErrorCode.INVALID_AUTHENTICATION].message,
    }
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="income-verification-api"'


def test_endpoint_returns_forbidden_for_insufficient_scope(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_authentication,
        "authenticator",
        program_authenticator(scopes=frozenset({"openid"})),
    )
    response = client.get(
        TEST_CONNECTION_PATH,
        headers={
            "Authorization": f"Bearer {TEST_ACCESS_TOKEN}",
            "Correlation-Id": CORRELATION_ID,
        },
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json() == {
        "code": ErrorCode.FORBIDDEN.value,
        "message": ERRORS[ErrorCode.FORBIDDEN].message,
    }
    assert response.headers["Correlation-Id"] == CORRELATION_ID


def test_unknown_client_log_includes_verified_client_id_but_response_does_not(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unknown_client_id = "unknown-client"
    monkeypatch.setattr(
        api_authentication,
        "authenticator",
        program_authenticator(client_id=unknown_client_id),
    )

    with capture_api_logs() as stream:
        response = client.get(TEST_CONNECTION_PATH, headers=_authenticated_headers())

    record = json.loads(stream.getvalue())
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json() == {
        "code": ErrorCode.FORBIDDEN.value,
        "message": ERRORS[ErrorCode.FORBIDDEN].message,
    }
    assert record["auth.failure.reason"] == AuthFailureReason.UNKNOWN_CLIENT
    assert record["auth.client.id"] == unknown_client_id
    assert unknown_client_id not in response.content.decode()


def test_auth_failure_logging_excludes_credentials_and_untrusted_data(client: Client) -> None:
    malformed_header = (
        "SENTINEL-MALFORMED-AUTHORIZATION "
        "SENTINEL-BEARER-TOKEN SENTINEL-CLIENT-SECRET SENTINEL-JWT-CLAIM"
    )
    with capture_api_logs() as stream:
        response = client.get(
            TEST_CONNECTION_PATH,
            headers={"Authorization": malformed_header, "Correlation-Id": CORRELATION_ID},
        )

    emitted = stream.getvalue()
    record = json.loads(emitted)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {
        "code": ErrorCode.INVALID_AUTHENTICATION.value,
        "message": ERRORS[ErrorCode.INVALID_AUTHENTICATION].message,
    }
    assert record["event.name"] == "income_verification.request.rejected"
    assert record["auth.failure.reason"] == AuthFailureReason.MALFORMED_CREDENTIALS
    assert record["error.code"] == ErrorCode.INVALID_AUTHENTICATION
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert set(record) == {
        "timestamp",
        "level",
        "logger",
        "message",
        "event.name",
        "error.type",
        "error.code",
        "auth.failure.reason",
        "http.request.method",
        "http.response.status_code",
        "url.path",
        "ivaas.correlation.id",
    }
    for sentinel in (
        "SENTINEL-MALFORMED-AUTHORIZATION",
        "SENTINEL-BEARER-TOKEN",
        "SENTINEL-CLIENT-SECRET",
        "SENTINEL-JWT-CLAIM",
    ):
        assert sentinel not in emitted


def test_raw_jwt_exception_message_cannot_reach_logs(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_exception = "SENTINEL-RAW-JWT-EXCEPTION"

    class FailingSigningKeyProvider:
        def get_signing_key(self, token: str) -> jwt.PyJWK:
            raise jwt.DecodeError(raw_exception)

    authenticator = ProgramAuthenticator(
        token_verifier=CognitoAccessTokenVerifier(
            issuer=ISSUER,
            signing_key_provider=FailingSigningKeyProvider(),
        ),
        required_scope=REQUIRED_SCOPE,
        program_resolver=ConfiguredProgramResolver({TEST_CLIENT_ID: TEST_PROGRAM_ID}),
    )
    monkeypatch.setattr(api_authentication, "authenticator", authenticator)
    with capture_api_logs() as stream:
        response = client.get(
            TEST_CONNECTION_PATH,
            headers={
                "Authorization": "Bearer SENTINEL-OPAQUE-JWT",
                "Correlation-Id": CORRELATION_ID,
            },
        )

    emitted = stream.getvalue()
    record = json.loads(emitted)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {
        "code": ErrorCode.INVALID_AUTHENTICATION.value,
        "message": ERRORS[ErrorCode.INVALID_AUTHENTICATION].message,
    }
    assert record["auth.failure.reason"] == AuthFailureReason.MALFORMED_CREDENTIALS
    assert raw_exception not in emitted
    assert "SENTINEL-OPAQUE-JWT" not in emitted


def test_expired_access_token_returns_specific_safe_response(
    client: Client,
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key, signing_key = rsa_keys
    authenticator = cognito_authenticator(signing_key)
    encoded_token = access_token(
        private_key,
        exp=datetime.now(tz=UTC) - timedelta(seconds=1),
        sentinel_custom_claim="SENTINEL-EXPIRED-TOKEN-CLAIM",
    )
    monkeypatch.setattr(api_authentication, "authenticator", authenticator)
    with capture_api_logs() as stream:
        response = client.get(
            TEST_CONNECTION_PATH,
            headers={
                "Authorization": f"Bearer {encoded_token}",
                "Correlation-Id": CORRELATION_ID,
            },
        )

    emitted = stream.getvalue()
    record = json.loads(emitted)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {
        "code": ErrorCode.ACCESS_TOKEN_EXPIRED.value,
        "message": ERRORS[ErrorCode.ACCESS_TOKEN_EXPIRED].message,
    }
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="income-verification-api"'
    assert record["auth.failure.reason"] == AuthFailureReason.EXPIRED_TOKEN
    assert record["error.code"] == ErrorCode.ACCESS_TOKEN_EXPIRED
    assert "auth.client.id" not in record
    assert encoded_token not in emitted
    assert "SENTINEL-EXPIRED-TOKEN-CLAIM" not in emitted


def test_jwks_unavailability_returns_safe_service_unavailable(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_exception = "SENTINEL-JWKS-CONNECTION-DETAIL"

    class UnavailableSigningKeyProvider:
        def get_signing_key(self, token: str) -> jwt.PyJWK:
            raise SigningKeyUnavailableError(raw_exception)

    authenticator = ProgramAuthenticator(
        token_verifier=CognitoAccessTokenVerifier(
            issuer=ISSUER,
            signing_key_provider=UnavailableSigningKeyProvider(),
        ),
        required_scope=REQUIRED_SCOPE,
        program_resolver=ConfiguredProgramResolver({TEST_CLIENT_ID: TEST_PROGRAM_ID}),
    )
    monkeypatch.setattr(api_authentication, "authenticator", authenticator)
    with capture_api_logs() as stream:
        response = client.get(
            TEST_CONNECTION_PATH,
            headers={
                "Authorization": "Bearer SENTINEL-OPAQUE-JWT",
                "Correlation-Id": CORRELATION_ID,
            },
        )

    emitted = stream.getvalue()
    record = json.loads(emitted)
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json() == {
        "code": ErrorCode.SERVICE_UNAVAILABLE.value,
        "message": ERRORS[ErrorCode.SERVICE_UNAVAILABLE].message,
    }
    assert response.headers["Correlation-Id"] == CORRELATION_ID
    assert "WWW-Authenticate" not in response.headers
    assert record["event.name"] == "income_verification.request.failed"
    assert record["auth.failure.reason"] == AuthFailureReason.JWKS_UNAVAILABLE
    assert record["ivaas.correlation.id"] == CORRELATION_ID
    assert raw_exception not in emitted
    assert "SENTINEL-OPAQUE-JWT" not in emitted


def test_decoded_jwt_claims_and_token_cannot_reach_logs(
    client: Client,
    rsa_keys: tuple[rsa.RSAPrivateKey, jwt.PyJWK],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key, signing_key = rsa_keys
    authenticator = cognito_authenticator(signing_key)
    encoded_token = access_token(
        private_key,
        scope="openid",
        sentinel_custom_claim="SENTINEL-DECODED-PRIVATE-CLAIM",
    )
    monkeypatch.setattr(api_authentication, "authenticator", authenticator)
    with capture_api_logs() as stream:
        response = client.get(
            TEST_CONNECTION_PATH,
            headers={
                "Authorization": f"Bearer {encoded_token}",
                "Correlation-Id": CORRELATION_ID,
            },
        )

    emitted = stream.getvalue()
    record = json.loads(emitted)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert record["auth.failure.reason"] == AuthFailureReason.INSUFFICIENT_SCOPE
    assert record["auth.client.id"] == TEST_CLIENT_ID
    assert "SENTINEL-DECODED-PRIVATE-CLAIM" not in emitted
    assert encoded_token not in emitted


def test_auth_failure_discards_malformed_correlation_before_authentication(client: Client) -> None:
    malformed_correlation = "SENTINEL-MALFORMED-CORRELATION"
    with capture_api_logs() as stream:
        response = client.get(
            TEST_CONNECTION_PATH,
            headers={
                "Authorization": "Bearer wrong-token",
                "Correlation-Id": malformed_correlation,
            },
        )

    record = json.loads(stream.getvalue())
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert "Correlation-Id" not in response.headers
    assert "ivaas.correlation.id" not in record
    assert malformed_correlation not in stream.getvalue()
