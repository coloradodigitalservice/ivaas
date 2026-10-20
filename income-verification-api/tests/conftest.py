import pytest

from income_verification.security.authentication import (
    AuthenticationFailure,
    AuthFailureReason,
    ConfiguredProgramResolver,
    ProgramAuthenticator,
    VerifiedClient,
)
from tests.income_verification.security.authentication_test_support import (
    REQUIRED_SCOPE,
    TEST_ACCESS_TOKEN,
    TEST_CLIENT_ID,
    TEST_PROGRAM_ID,
)


class StaticAccessTokenVerifier:
    """Deterministic provider substitute at the token-verification boundary."""

    def __init__(self, scopes: frozenset[str] = frozenset({REQUIRED_SCOPE})) -> None:
        self.scopes = scopes

    def verify(self, token: str) -> VerifiedClient:
        if token != TEST_ACCESS_TOKEN:
            raise AuthenticationFailure(AuthFailureReason.INVALID_TOKEN)
        return VerifiedClient(client_id=TEST_CLIENT_ID, scopes=self.scopes)


@pytest.fixture
def configured_api_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep endpoint tests independent from local machines and external identity providers."""
    from income_verification.api import api_authentication

    monkeypatch.setattr(
        api_authentication,
        "authenticator",
        ProgramAuthenticator(
            token_verifier=StaticAccessTokenVerifier(),
            required_scope=REQUIRED_SCOPE,
            program_resolver=ConfiguredProgramResolver({TEST_CLIENT_ID: TEST_PROGRAM_ID}),
        ),
    )
