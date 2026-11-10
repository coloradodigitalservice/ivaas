"""Forward authenticated DPW VMI webhooks to the configured program."""

import logging
import time
from dataclasses import dataclass
from email.message import Message
from http.client import HTTPException, HTTPResponse
from typing import IO, override
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dpw_vmi_adapter.programs import DpwVmiProgram
from dpw_vmi_adapter.signing import sign

logger = logging.getLogger(__name__)
_MAX_RESPONSE_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class ProgramResponse:
    """The program response safe to return to VMI.

    Attributes:
        status_code: HTTP status to return unchanged to VMI.
        body: Response body, capped to protect the IVaaS worker.
        content_type: Program Content-Type when one was provided.
    """

    status_code: int
    body: bytes
    content_type: str | None


class _NoRedirect(HTTPRedirectHandler):
    """Prevent signed reports from being redirected from their destination."""

    @override
    def redirect_request(
        self,
        request: Request,
        file_pointer: IO[bytes],
        status_code: int,
        message: str,
        headers: Message,
        new_url: str,
    ) -> None:
        return None


_opener = build_opener(_NoRedirect())


def forward_webhook(
    body: bytes,
    *,
    program: DpwVmiProgram,
    timeout_seconds: int,
    vmi_timestamp: str,
    confirmation_code: str | None,
    webhook_request_id: str,
) -> ProgramResponse:
    """Send the signed body to the program and return its response for VMI."""
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-IVaaS-Timestamp": timestamp,
        "X-IVaaS-Webhook-Request-Id": webhook_request_id,
        "X-IVaaS-Signature": sign(
            body,
            key=program.webhook_signing_key,
            timestamp=timestamp,
        ),
        "X-VMI-Timestamp": vmi_timestamp,
    }
    if confirmation_code is not None:
        headers["X-VMI-Confirmation-Code"] = confirmation_code

    # Safe for S310: startup validation permits HTTPS, or HTTP only with DEBUG enabled,
    # and redirects are refused.
    request = Request(  # noqa: S310
        program.webhook_url, data=body, headers=headers, method="POST"
    )
    logger.info(
        "Sending DPW VMI webhook to program.",
        extra={
            "event.name": "dpw_vmi.program_webhook.send_started",
            "ivaas.program.id": program.program_id,
        },
    )
    try:
        # shortcut: timeout is per socket operation, use a deadline-aware client if needed.
        response = _opener.open(request, timeout=timeout_seconds)
    except HTTPError as error:
        response = error
    except HTTPException, OSError:
        return _log_send_failure(
            program.program_id,
            ProgramResponse(504, b"", None),
            error_type="network_failure",
            exc_info=True,
        )

    # IVaaS refuses redirects, and VMI defines no 3xx handling, so answer 502.
    status_code = response.status
    if 300 <= status_code < 400:
        response.close()
        return _log_program_response_received(
            program.program_id,
            ProgramResponse(502, b"", None),
            program_status_code=status_code,
            error_type="redirect",
        )

    try:
        with response:
            program_response = _read_response(response, status_code=status_code)
    except HTTPException, OSError:
        return _log_program_response_received(
            program.program_id,
            ProgramResponse(status_code, b"", None),
            error_type="response_read_failed",
            exc_info=True,
        )
    if program_response is None:
        return _log_program_response_received(
            program.program_id,
            ProgramResponse(status_code, b"", None),
            error_type="response_too_large",
        )
    return _log_program_response_received(program.program_id, program_response)


def _read_response(
    response: HTTPResponse | HTTPError, *, status_code: int
) -> ProgramResponse | None:
    body = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(body) > _MAX_RESPONSE_BYTES:
        return None
    return ProgramResponse(status_code, body, response.headers.get("Content-Type"))


def _log_program_response_received(
    program_id: str,
    response: ProgramResponse,
    *,
    program_status_code: int | None = None,
    error_type: str | None = None,
    exc_info: bool = False,
) -> ProgramResponse:
    extra: dict[str, object] = {
        "event.name": "dpw_vmi.program_webhook.response_received",
        "ivaas.program.id": program_id,
        "http.response.status_code": (
            program_status_code if program_status_code is not None else response.status_code
        ),
    }
    if error_type is not None:
        extra["error.type"] = error_type
    if error_type is not None or 400 <= response.status_code < 500:
        log = logger.error
    elif 200 <= response.status_code < 300:
        log = logger.info
    else:
        log = logger.warning
    log(
        "DPW VMI program webhook response received.",
        extra=extra,
        exc_info=exc_info,
    )
    return response


def _log_send_failure(
    program_id: str,
    response: ProgramResponse,
    *,
    error_type: str,
    exc_info: bool = False,
) -> ProgramResponse:
    logger.error(
        "Failed to send DPW VMI webhook to program.",
        extra={
            "event.name": "dpw_vmi.program_webhook.send_failed",
            "error.type": error_type,
            "ivaas.program.id": program_id,
        },
        exc_info=exc_info,
    )
    return response
