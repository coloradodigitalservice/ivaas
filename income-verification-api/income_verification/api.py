from django.conf import settings
from django.http import HttpRequest
from ninja import NinjaAPI

from income_verification.api_errors import register_exception_handlers
from income_verification.routes import router
from income_verification.security import get_api_authentication

api_authentication = get_api_authentication()

api = NinjaAPI(
    title="IVaaS API",
    version=settings.API_VERSION,
    docs_url="/docs",
    openapi_url="/openapi.json",
    auth=api_authentication,
)

# Register exception handlers with the API
register_exception_handlers(api)


# NOTE: Health endpoint not versioned
@api.get("/health", include_in_schema=False, auth=None)
def health(request: HttpRequest) -> dict[str, str]:
    return {"status": "ok"}


api.add_router(f"/{settings.API_VERSION}", router)
