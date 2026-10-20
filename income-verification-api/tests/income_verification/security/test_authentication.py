import pytest
from django.test import RequestFactory

from income_verification.security import (
    AuthenticatedProgram,
    AuthenticationFailure,
    AuthFailureReason,
    AuthorizationFailure,
    ProgramOAuth2ClientCredentials,
)
from tests.income_verification.security.authentication_test_support import (
    OAUTH_ENDPOINT,
    REQUIRED_SCOPE,
    TEST_ACCESS_TOKEN,
    TEST_CLIENT_ID,
    TEST_PROGRAM_ID,
    assert_failure_reason,
    program_authenticator,
)


def test_program_authenticator_resolves_verified_client() -> None:
    principal = program_authenticator().authenticate(TEST_ACCESS_TOKEN)

    assert principal == AuthenticatedProgram(
        client_id=TEST_CLIENT_ID,
        program_id=TEST_PROGRAM_ID,
        scopes=frozenset({REQUIRED_SCOPE}),
    )


@pytest.mark.parametrize(
    "scopes",
    [
        frozenset(),
        frozenset({f"{REQUIRED_SCOPE}-extra"}),
        frozenset({f"prefix-{REQUIRED_SCOPE}"}),
        frozenset({"openid", "profile"}),
    ],
)
def test_program_authorization_requires_exact_scope(scopes: frozenset[str]) -> None:
    assert_failure_reason(
        AuthorizationFailure,
        AuthFailureReason.INSUFFICIENT_SCOPE,
        lambda: program_authenticator(scopes=scopes).authenticate(TEST_ACCESS_TOKEN),
    )


def test_program_authorization_rejects_unknown_client() -> None:
    assert_failure_reason(
        AuthorizationFailure,
        AuthFailureReason.UNKNOWN_CLIENT,
        lambda: program_authenticator(client_id="unknown-client").authenticate(TEST_ACCESS_TOKEN),
    )


@pytest.mark.parametrize("authorization", [None, "Basic value", "Bearer", "Bearer one two"])
def test_bearer_boundary_rejects_missing_or_malformed_header(
    authorization: str | None,
) -> None:
    authentication = ProgramOAuth2ClientCredentials(
        program_authenticator(),
        token_url=OAUTH_ENDPOINT,
        required_scope=REQUIRED_SCOPE,
    )
    headers = {} if authorization is None else {"Authorization": authorization}
    request = RequestFactory().get("/", headers=headers)
    expected_reason = (
        AuthFailureReason.MISSING_CREDENTIALS
        if authorization is None
        else AuthFailureReason.MALFORMED_CREDENTIALS
    )

    assert_failure_reason(
        AuthenticationFailure,
        expected_reason,
        lambda: authentication(request),
    )
