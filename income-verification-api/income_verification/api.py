import logging

from django.conf import settings
from django.http import HttpRequest
from ninja import NinjaAPI

from income_verification.api_errors import register_exception_handlers
from income_verification.routes import router

logger = logging.getLogger(__name__)

api = NinjaAPI(
    title="IVaaS API",
    version=settings.API_VERSION,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Register exception handlers with the API
register_exception_handlers(api)

# NOTE: Health endpoint not versioned
@api.get("/health", include_in_schema=False)
def health(request: HttpRequest) -> dict[str, str]:
    return {"status": "ok"}

# Versioned API endpoints
api.add_router(f"/{settings.API_VERSION}", router)
