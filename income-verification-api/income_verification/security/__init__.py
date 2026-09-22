"""Public authentication facade for the income verification application."""

from income_verification.security.authentication import (
    AgencyOAuth2ClientCredentials,
    AuthenticatedAgency,
    AuthenticationFailure,
    AuthenticationInfrastructureFailure,
    AuthFailureReason,
    AuthorizationFailure,
    get_authenticated_agency,
)
from income_verification.security.configuration import get_api_authentication

__all__ = [
    "AgencyOAuth2ClientCredentials",
    "AuthFailureReason",
    "AuthenticatedAgency",
    "AuthenticationFailure",
    "AuthenticationInfrastructureFailure",
    "AuthorizationFailure",
    "get_api_authentication",
    "get_authenticated_agency",
]
