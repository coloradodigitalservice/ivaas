import pytest
from django.test import RequestFactory

from income_verification.security import (
    AgencyOAuth2ClientCredentials,
    AuthenticatedAgency,
    AuthenticationFailure,
    AuthFailureReason,
    AuthorizationFailure,
)
from tests.income_verification.security.authentication_test_support import (
    AGENCY_ID,
    CLIENT_ID,
    OAUTH_ENDPOINT,
    REQUIRED_SCOPE,
    TEST_ACCESS_TOKEN,
    agency_authenticator,
    assert_failure_reason,
)


def test_agency_authenticator_resolves_verified_client() -> None:
    principal = agency_authenticator().authenticate(TEST_ACCESS_TOKEN)

    assert principal == AuthenticatedAgency(
        client_id=CLIENT_ID,
        agency_id=AGENCY_ID,
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
def test_agency_authorization_requires_exact_scope(scopes: frozenset[str]) -> None:
    assert_failure_reason(
        AuthorizationFailure,
        AuthFailureReason.INSUFFICIENT_SCOPE,
        lambda: agency_authenticator(scopes=scopes).authenticate(TEST_ACCESS_TOKEN),
    )


def test_agency_authorization_rejects_unknown_client() -> None:
    assert_failure_reason(
        AuthorizationFailure,
        AuthFailureReason.UNKNOWN_CLIENT,
        lambda: agency_authenticator(client_id="unknown-client").authenticate(TEST_ACCESS_TOKEN),
    )


@pytest.mark.parametrize("authorization", [None, "Basic value", "Bearer", "Bearer one two"])
def test_bearer_boundary_rejects_missing_or_malformed_header(
    authorization: str | None,
) -> None:
    authentication = AgencyOAuth2ClientCredentials(
        agency_authenticator(),
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
