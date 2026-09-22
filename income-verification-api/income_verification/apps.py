from django.apps import AppConfig


class IncomeVerificationConfig(AppConfig):
    name = "income_verification"

    def ready(self) -> None:
        """Validate authentication configuration as Django finishes app initialization.

        Django invokes ready() after the app registry is populated. Building the cached
        authentication object here makes invalid configuration fail at startup while avoiding
        network access; JWKS retrieval remains lazy until the first authenticated request.
        """
        from income_verification.security import get_api_authentication

        get_api_authentication()
