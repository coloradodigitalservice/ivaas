"""Check forwarding authenticated DPW VMI webhooks to a program."""

import logging
from email.message import Message
from http.client import IncompleteRead
from io import BytesIO
from typing import Self
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.request import BaseHandler, Request, build_opener
from urllib.response import addinfourl

import pytest
from dpw_vmi_adapter import forwarding
from dpw_vmi_adapter.forwarding import ProgramResponse, forward_webhook
from dpw_vmi_adapter.programs import DpwVmiProgram
from dpw_vmi_adapter.signing import verify

BODY = b'{"event_type":"ReportSubmission"}'
PROGRAM = DpwVmiProgram(
    program_id="test-program",
    webhook_url="https://program.example/webhook",
    webhook_signing_key="test-webhook-signing-key",
)
VMI_TIMESTAMP = "1700000000"
IVASS_TIMESTAMP = 1_800_000_000
WEBHOOK_REQUEST_ID = "01234567-89ab-cdef-0123-456789abcdef"


class StubResponse:
    """A program HTTP response accepted by urllib's context-manager contract."""

    def __init__(
        self,
        status: int,
        body: bytes,
        content_type: str | None = None,
        read_error: Exception | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.headers = Message()
        if content_type is not None:
            self.headers["Content-Type"] = content_type
        self.read_error = read_error
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def read(self, amount: int = -1) -> bytes:
        if self.read_error is not None:
            raise self.read_error
        return self.body[:amount]

    def close(self) -> None:
        self.closed = True


class StubBody(BytesIO):
    """A response body carrying the status message urllib expects."""

    def __init__(self, value: bytes, message: str) -> None:
        super().__init__(value)
        self.msg = message


class RedirectingHttpsHandler(BaseHandler):
    """Return a redirect, then a success if the opener follows it."""

    handler_order = 100

    def __init__(self) -> None:
        self.requests: list[str] = []

    def https_open(self, request: Request) -> addinfourl:
        self.requests.append(request.full_url)
        headers = Message()
        if len(self.requests) == 1:
            headers["Location"] = "https://internal.example/webhook"
            return addinfourl(
                StubBody(b"redirecting", "Found"), headers, request.full_url, code=302
            )
        return addinfourl(StubBody(b"followed", "OK"), headers, request.full_url, code=200)


def test_forward_webhook_sends_exact_body_and_signed_headers(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    program_response = StubResponse(207, b'{"received":true}', "application/json")
    open_mock = Mock(return_value=program_response)
    monkeypatch.setattr(forwarding._opener, "open", open_mock)
    monkeypatch.setattr("dpw_vmi_adapter.forwarding.time.time", lambda: IVASS_TIMESTAMP)

    with caplog.at_level(logging.INFO, logger="dpw_vmi_adapter.forwarding"):
        result = forward_webhook(
            BODY,
            program=PROGRAM,
            timeout_seconds=10,
            vmi_timestamp=VMI_TIMESTAMP,
            confirmation_code="confirmation-123",
            webhook_request_id=WEBHOOK_REQUEST_ID,
        )

    assert result == ProgramResponse(207, b'{"received":true}', "application/json")
    request = open_mock.call_args.args[0]
    headers = {name.lower(): value for name, value in request.header_items()}
    assert request.full_url == PROGRAM.webhook_url
    assert request.data == BODY
    assert request.method == "POST"
    assert open_mock.call_args.kwargs == {"timeout": 10}
    assert headers["content-type"] == "application/json"
    assert headers["x-ivaas-timestamp"] == str(IVASS_TIMESTAMP)
    assert headers["x-ivaas-webhook-request-id"] == WEBHOOK_REQUEST_ID
    assert verify(
        BODY,
        key=PROGRAM.webhook_signing_key,
        timestamp=str(IVASS_TIMESTAMP),
        signature=headers["x-ivaas-signature"],
    )
    assert headers["x-vmi-timestamp"] == VMI_TIMESTAMP
    assert headers["x-vmi-confirmation-code"] == "confirmation-123"
    assert "x-vmi-signature" not in headers
    assert "x-vmi-api-key" not in headers
    assert program_response.closed
    events = {record.__dict__.get("event.name"): record for record in caplog.records}
    assert "dpw_vmi.program_webhook.send_started" in events
    assert (
        events["dpw_vmi.program_webhook.response_received"].__dict__["http.response.status_code"]
        == 207
    )


@pytest.mark.parametrize("status_code", [400, 401, 413, 422, 429, 500, 503, 504])
def test_forward_webhook_returns_program_http_error(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    headers = Message()
    headers["Content-Type"] = "application/problem+json"
    error = HTTPError(
        PROGRAM.webhook_url,
        status_code,
        "program response",
        headers,
        BytesIO(b'{"error_code":"PROGRAM_ERROR"}'),
    )
    monkeypatch.setattr(forwarding._opener, "open", Mock(side_effect=error))

    result = forward_webhook(
        BODY,
        program=PROGRAM,
        timeout_seconds=10,
        vmi_timestamp=VMI_TIMESTAMP,
        confirmation_code=None,
        webhook_request_id=WEBHOOK_REQUEST_ID,
    )

    assert result == ProgramResponse(
        status_code,
        b'{"error_code":"PROGRAM_ERROR"}',
        "application/problem+json",
    )


def test_forward_webhook_rejects_program_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    assert any(
        isinstance(handler, forwarding._NoRedirect)
        for handler in vars(forwarding._opener)["handlers"]
    )
    handler = RedirectingHttpsHandler()
    monkeypatch.setattr(forwarding, "_opener", build_opener(forwarding._NoRedirect(), handler))

    result = forward_webhook(
        BODY,
        program=PROGRAM,
        timeout_seconds=10,
        vmi_timestamp=VMI_TIMESTAMP,
        confirmation_code=None,
        webhook_request_id=WEBHOOK_REQUEST_ID,
    )

    assert result == ProgramResponse(502, b"", None)
    assert handler.requests == [PROGRAM.webhook_url]


@pytest.mark.parametrize(
    "error",
    [URLError("unreachable"), TimeoutError(), IncompleteRead(b"partial")],
)
def test_forward_webhook_returns_gateway_timeout_for_network_failure(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    monkeypatch.setattr(forwarding._opener, "open", Mock(side_effect=error))

    result = forward_webhook(
        BODY,
        program=PROGRAM,
        timeout_seconds=10,
        vmi_timestamp=VMI_TIMESTAMP,
        confirmation_code=None,
        webhook_request_id=WEBHOOK_REQUEST_ID,
    )

    assert result == ProgramResponse(504, b"", None)


def test_forward_webhook_keeps_status_when_program_response_is_too_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        forwarding._opener,
        "open",
        Mock(return_value=StubResponse(200, b"x" * (64 * 1024 + 1))),
    )

    result = forward_webhook(
        BODY,
        program=PROGRAM,
        timeout_seconds=10,
        vmi_timestamp=VMI_TIMESTAMP,
        confirmation_code=None,
        webhook_request_id=WEBHOOK_REQUEST_ID,
    )

    assert result == ProgramResponse(200, b"", None)


def test_forward_webhook_keeps_status_when_program_response_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        forwarding._opener,
        "open",
        Mock(return_value=StubResponse(202, b"", read_error=IncompleteRead(b"partial"))),
    )

    result = forward_webhook(
        BODY,
        program=PROGRAM,
        timeout_seconds=10,
        vmi_timestamp=VMI_TIMESTAMP,
        confirmation_code=None,
        webhook_request_id=WEBHOOK_REQUEST_ID,
    )

    assert result == ProgramResponse(202, b"", None)
