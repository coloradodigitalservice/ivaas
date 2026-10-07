import asyncio
from inspect import iscoroutinefunction
from unittest.mock import AsyncMock, Mock

import pytest
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.test import Client, RequestFactory
from pytest_django.fixtures import Settings

from income_verification.health_check import HealthCheckMiddleware

HEALTH_PATH = HealthCheckMiddleware.PATH
OTHER_PATH = "/api/health"
MIDDLEWARE_PATH = "income_verification.health_check.HealthCheckMiddleware"
TEST_ALLOWED_HOST = "example.com"
TEST_OTHER_HOST = "test.example.com"


def call_sync(middleware: HealthCheckMiddleware, request: HttpRequest) -> HttpResponse:
    response = middleware(request)
    assert isinstance(response, HttpResponse)
    return response


def call_async(middleware: HealthCheckMiddleware, request: HttpRequest) -> HttpResponse:
    result = middleware(request)
    assert not isinstance(result, HttpResponseBase)

    async def wait() -> HttpResponseBase:
        return await result

    response = asyncio.run(wait())
    assert isinstance(response, HttpResponse)
    return response


@pytest.fixture
def get_response() -> Mock:
    return Mock(return_value=HttpResponse("downstream"))


@pytest.fixture
def async_get_response() -> AsyncMock:
    return AsyncMock(return_value=HttpResponse("downstream"))


@pytest.fixture
def middleware(get_response: Mock) -> HealthCheckMiddleware:
    return HealthCheckMiddleware(get_response)


@pytest.fixture
def async_middleware(async_get_response: AsyncMock) -> HealthCheckMiddleware:
    return HealthCheckMiddleware(async_get_response)


class TestHealthCheckResponse:
    def test_get_returns_200_ok(
        self, rf: RequestFactory, middleware: HealthCheckMiddleware, get_response: Mock
    ) -> None:
        response = call_sync(middleware, rf.get(HEALTH_PATH))

        assert response.status_code == 200
        assert response["Content-Type"] == "text/plain"
        assert response.content == b"ok"
        get_response.assert_not_called()

    def test_response_is_not_cacheable(
        self, rf: RequestFactory, middleware: HealthCheckMiddleware, get_response: Mock
    ) -> None:
        response = call_sync(middleware, rf.get(HEALTH_PATH))

        assert (
            response["Cache-Control"] == "max-age=0, no-cache, no-store, must-revalidate, private"
        )

    def test_query_string_is_ignored(
        self, rf: RequestFactory, middleware: HealthCheckMiddleware, get_response: Mock
    ) -> None:
        response = call_sync(middleware, rf.get(HEALTH_PATH, {"query": "1"}))

        assert response.status_code == 200
        get_response.assert_not_called()


class TestPassThrough:
    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete", "options", "head"])
    def test_other_methods_pass_through(
        self, rf: RequestFactory, middleware: HealthCheckMiddleware, get_response: Mock, method: str
    ) -> None:
        request: HttpRequest = getattr(rf, method)(HEALTH_PATH)

        response = call_sync(middleware, request)

        get_response.assert_called_once_with(request)
        assert response.content == b"downstream"

    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/other",
            HEALTH_PATH + "/",
            HEALTH_PATH + "z",
            "/api" + HEALTH_PATH,
            HEALTH_PATH.upper(),
        ],
    )
    def test_other_paths_pass_through(
        self, rf: RequestFactory, middleware: HealthCheckMiddleware, get_response: Mock, path: str
    ) -> None:
        request = rf.get(path)
        response = call_sync(middleware, request)

        get_response.assert_called_once_with(request)
        assert response.content == b"downstream"


class TestAsyncMode:
    def test_marked_as_coroutine_only_for_async_chain(
        self, middleware: HealthCheckMiddleware, async_middleware: HealthCheckMiddleware
    ) -> None:
        assert not iscoroutinefunction(middleware)
        assert iscoroutinefunction(async_middleware)

    def test_health_check_is_answered(
        self,
        rf: RequestFactory,
        async_middleware: HealthCheckMiddleware,
        async_get_response: AsyncMock,
    ) -> None:
        response = call_async(async_middleware, rf.get(HEALTH_PATH, HTTP_HOST=TEST_OTHER_HOST))

        assert response.status_code == 200
        assert response.content == b"ok"
        async_get_response.assert_not_called()

    def test_other_paths_pass_through(
        self,
        rf: RequestFactory,
        async_middleware: HealthCheckMiddleware,
        async_get_response: AsyncMock,
    ) -> None:
        request = rf.get(OTHER_PATH)

        response = call_async(async_middleware, request)

        async_get_response.assert_awaited_once_with(request)
        assert response.content == b"downstream"


@pytest.fixture
def production_like(settings: Settings) -> None:
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = [TEST_ALLOWED_HOST]


@pytest.mark.usefixtures("production_like")
class TestFullStack:
    def test_middleware_is_first(self, settings: Settings) -> None:
        assert settings.MIDDLEWARE[0] == MIDDLEWARE_PATH

    def test_middleware_other_host_succeeds(self) -> None:
        response = Client().get(HEALTH_PATH, HTTP_HOST=TEST_OTHER_HOST)

        assert response.status_code == 200
        assert response.content == b"ok"

    def test_other_path_rejects_other_host(self) -> None:
        response = Client().get(OTHER_PATH, HTTP_HOST=TEST_OTHER_HOST)

        assert response.status_code == 400
