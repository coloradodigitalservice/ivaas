"""Public authentication facade for the income verification application."""

from income_verification.security.authentication import (
    AuthenticatedProgram,
    AuthenticationFailure,
    AuthenticationInfrastructureFailure,
    AuthFailureReason,
    AuthorizationFailure,
    ProgramOAuth2ClientCredentials,
    get_authenticated_program,
)
from income_verification.security.configuration import get_api_authentication

__all__ = [
    "AuthFailureReason",
    "AuthenticatedProgram",
    "AuthenticationFailure",
    "AuthenticationInfrastructureFailure",
    "AuthorizationFailure",
    "ProgramOAuth2ClientCredentials",
    "get_api_authentication",
    "get_authenticated_program",
]
