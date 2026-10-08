"""Request-scoped context exposed to application logging."""

import json
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from inspect import iscoroutinefunction, markcoroutinefunction
from typing import cast

from django.http import HttpRequest, HttpResponseBase

from income_verification.correlation_id import (
    CORRELATION_ID_HEADER_NAME,
    validated_correlation_id,
)
from income_verification.log_redaction import redacted_message


@dataclass(frozen=True, slots=True)
class RequestLogContext:
    correlation_id: str | None = None
    client_id: str | None = None
    agency_id: str | None = None
    application_id: str | None = None
    verification_id: str | None = None


_empty_request_log_context = RequestLogContext()
_request_log_context: ContextVar[RequestLogContext] = ContextVar(
    "ivaas_request_log_context", default=_empty_request_log_context
)

SyncGetResponse = Callable[[HttpRequest], HttpResponseBase]
AsyncGetResponse = Callable[[HttpRequest], Awaitable[HttpResponseBase]]


class LogField(StrEnum):
    """The only structured `extra` keys emitted by the JSON formatter."""

    EVENT_NAME = "event.name"
    ERROR_TYPE = "error.type"
    ERROR_CODE = "error.code"
    VALIDATION_ERROR_COUNT = "validation.error.count"
    VALIDATION_ERRORS = "validation.errors"
    AUTH_FAILURE_REASON = "auth.failure.reason"
    AUTH_CLIENT_ID = "auth.client.id"
    HTTP_REQUEST_METHOD = "http.request.method"
    HTTP_RESPONSE_STATUS_CODE = "http.response.status_code"
    URL_PATH = "url.path"
    EXCEPTION_TYPE = "exception.type"
    EXCEPTION_ORIGIN_MODULE = "exception.origin.module"
    EXCEPTION_ORIGIN_FUNCTION = "exception.origin.function"
    EXCEPTION_ORIGIN_LINE = "exception.origin.line"
    CORRELATION_ID = "ivaas.correlation.id"
    AGENCY_ID = "ivaas.agency.id"
    APPLICATION_ID = "ivaas.application.id"
    VERIFICATION_ID = "ivaas.verification.id"
    SOURCE_ID = "ivaas.source.id"


def get_correlation_id() -> str | None:
    """Return the current request correlation ID when one was validated."""
    return _request_log_context.get().correlation_id


def _update_request_log_context(**changes: str) -> None:
    """Update context only while request middleware owns its lifecycle."""
    context = _request_log_context.get()
    if context is _empty_request_log_context:
        return
    _request_log_context.set(replace(context, **changes))


def set_verification_log_context(application_id: str, verification_id: str) -> None:
    """Add identifiers that only become available after request validation."""
    _update_request_log_context(
        application_id=application_id,
        verification_id=verification_id,
    )


def set_client_log_context(client_id: str) -> None:
    """Add the client identity from a successfully verified access token."""
    _update_request_log_context(client_id=client_id)


def set_agency_log_context(agency_id: str) -> None:
    """Add the non-PII IVaaS agency identity resolved during authentication."""
    _update_request_log_context(agency_id=agency_id)


def _bind_request_log_context(request: HttpRequest) -> Token[RequestLogContext]:
    """Start a fresh request log context; reset it with the returned token."""
    return _request_log_context.set(
        RequestLogContext(
            correlation_id=validated_correlation_id(request.headers.get(CORRELATION_ID_HEADER_NAME))
        )
    )


class RequestContextFilter(logging.Filter):
    """Add allowlisted request context to each application log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = _request_log_context.get()
        if context.correlation_id is not None:
            setattr(record, LogField.CORRELATION_ID.value, context.correlation_id)
        if context.client_id is not None:
            setattr(record, LogField.AUTH_CLIENT_ID.value, context.client_id)
        if context.agency_id is not None:
            setattr(record, LogField.AGENCY_ID.value, context.agency_id)
        if context.application_id is not None:
            setattr(record, LogField.APPLICATION_ID.value, context.application_id)
        if context.verification_id is not None:
            setattr(record, LogField.VERIFICATION_ID.value, context.verification_id)
        return True


class JsonLogFormatter(logging.Formatter):
    """Serialize allowlisted fields with backup redaction for application messages."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redacted_message(record),
        }
        for field in LogField:
            if hasattr(record, field.value):
                payload[field.value] = getattr(record, field.value)
        if record.exc_info and record.exc_info[0] is not None:
            payload[LogField.EXCEPTION_TYPE.value] = record.exc_info[0].__name__
        # Exception messages, tracebacks, and raw stack_info are intentionally omitted.
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )


class RequestContextMiddleware:
    """Bind request logging context for the lifetime of one request."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: SyncGetResponse | AsyncGetResponse) -> None:
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> HttpResponseBase | Awaitable[HttpResponseBase]:
        if self.async_mode:
            return self._async_call(request)

        token = _bind_request_log_context(request)
        try:
            return cast(SyncGetResponse, self.get_response)(request)
        finally:
            _request_log_context.reset(token)

    async def _async_call(self, request: HttpRequest) -> HttpResponseBase:
        token = _bind_request_log_context(request)
        try:
            return await cast(AsyncGetResponse, self.get_response)(request)
        finally:
            _request_log_context.reset(token)
