from collections.abc import Awaitable, Callable
from inspect import iscoroutinefunction, markcoroutinefunction
from typing import cast

from django.http import HttpRequest, HttpResponse, HttpResponseBase

SyncGetResponse = Callable[[HttpRequest], HttpResponseBase]
AsyncGetResponse = Callable[[HttpRequest], Awaitable[HttpResponseBase]]


class HealthCheckMiddleware:
    """Answers ALB health checks before host validation"""

    PATH = "/healthz"
    sync_capable = True
    async_capable = True

    def __init__(self, get_response: SyncGetResponse | AsyncGetResponse) -> None:
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def _is_health_check(self, request: HttpRequest) -> bool:
        return request.path == self.PATH and request.method == "GET"

    def _health_response(self) -> HttpResponse:
        response = HttpResponse("ok", content_type="text/plain")
        response["Cache-Control"] = "max-age=0, no-cache, no-store, must-revalidate, private"
        return response

    def __call__(self, request: HttpRequest) -> HttpResponseBase | Awaitable[HttpResponseBase]:
        if self.async_mode:
            return self._async_call(request)

        if self._is_health_check(request):
            return self._health_response()

        return cast(SyncGetResponse, self.get_response)(request)

    async def _async_call(self, request: HttpRequest) -> HttpResponseBase:
        if self._is_health_check(request):
            return self._health_response()

        return await cast(AsyncGetResponse, self.get_response)(request)
