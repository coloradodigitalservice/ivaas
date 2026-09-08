"""Request-scoped context exposed to application logging."""

import inspect
import json
import logging
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from asgiref.sync import markcoroutinefunction
from django.http import HttpRequest, HttpResponse

from income_verification.correlation_id import (
    CORRELATION_ID_HEADER_NAME,
    validated_correlation_id,
)

@dataclass(frozen=True, slots=True)
class RequestLogContext:
    correlation_id: str | None = None
    application_id: str | None = None
    verification_id: str | None = None


_empty_request_log_context = RequestLogContext()
_request_log_context: ContextVar[RequestLogContext] = ContextVar(
    "ivaas_request_log_context", default=_empty_request_log_context
)

_STRUCTURED_FIELD_NAMES = {
    "event_name": "event.name",
    "error_type": "error.type",
    "error_code": "error.code",
    "validation_error_count": "validation.error.count",
    "validation_errors": "validation.errors",
    "http_request_method": "http.request.method",
    "http_response_status_code": "http.response.status_code",
    "url_path": "url.path",
    "ivaas_correlation_id": "ivaas.correlation.id",
    "ivaas_application_id": "ivaas.application.id",
    "ivaas_verification_id": "ivaas.verification.id",
}

SyncGetResponse = Callable[[HttpRequest], HttpResponse]
AsyncGetResponse = Callable[[HttpRequest], Awaitable[HttpResponse]]


def get_correlation_id() -> str | None:
    """Return the current request correlation ID when one was validated."""
    return _request_log_context.get().correlation_id


def set_verification_log_context(application_id: str, verification_id: str) -> None:
    """Add identifiers that only become available after request validation."""
    current = _request_log_context.get()
    _request_log_context.set(
        RequestLogContext(
            correlation_id=current.correlation_id,
            application_id=application_id,
            verification_id=verification_id,
        )
    )


class RequestContextFilter(logging.Filter):
    """Add allowlisted request context to each application log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = _request_log_context.get()
        if context.correlation_id is not None:
            record.ivaas_correlation_id = context.correlation_id
        if context.application_id is not None:
            record.ivaas_application_id = context.application_id
        if context.verification_id is not None:
            record.ivaas_verification_id = context.verification_id
        return True


class JsonLogFormatter(logging.Formatter):
    """Serialize one enriched Python log record as one JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for record_name, json_name in _STRUCTURED_FIELD_NAMES.items():
            if hasattr(record, record_name):
                payload[json_name] = getattr(record, record_name)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False, separators=(",", ":"))


class RequestContextMiddleware:
    """Bind request logging context for the lifetime of one request."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: SyncGetResponse | AsyncGetResponse) -> None:
        self.get_response = get_response
        self.async_mode = inspect.iscoroutinefunction(get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> HttpResponse | Awaitable[HttpResponse]:
        if self.async_mode:
            return self._async_call(request)

        token = _request_log_context.set(
            RequestLogContext(
                correlation_id=validated_correlation_id(request.headers.get(CORRELATION_ID_HEADER_NAME))
            )
        )
        try:
            return cast(SyncGetResponse, self.get_response)(request)
        finally:
            _request_log_context.reset(token)

    async def _async_call(self, request: HttpRequest) -> HttpResponse:
        token = _request_log_context.set(
            RequestLogContext(
                correlation_id=validated_correlation_id(request.headers.get(CORRELATION_ID_HEADER_NAME))
            )
        )
        try:
            return await cast(AsyncGetResponse, self.get_response)(request)
        finally:
            _request_log_context.reset(token)
