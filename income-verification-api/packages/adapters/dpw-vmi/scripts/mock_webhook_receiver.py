# ruff: noqa: INP001
"""Receive and verify forwarded DPW VMI webhooks for local development."""

import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

_WEBHOOK_RECEIVER_URL = "http://127.0.0.1:8900/mock-program/vmi-webhooks"
_SIGNING_KEY = "00000000000000000000000000000000"


def _signature_is_valid(
    body: bytes,
    *,
    timestamp: str | None,
    signature: str | None,
) -> bool:
    if timestamp is None or signature is None:
        return False
    message = timestamp.encode() + b":" + body
    expected = hmac.new(_SIGNING_KEY.encode(), message, hashlib.sha512).hexdigest()
    return hmac.compare_digest(signature, expected)


class _ProgramWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != urlsplit(_WEBHOOK_RECEIVER_URL).path:
            self._respond(HTTPStatus.NOT_FOUND)
            return

        content_length = self.headers.get("Content-Length")
        if content_length is None or not content_length.isdigit():
            self._respond(HTTPStatus.BAD_REQUEST)
            return
        body = self.rfile.read(int(content_length))
        if not _signature_is_valid(
            body,
            timestamp=self.headers.get("X-IVaaS-Timestamp"),
            signature=self.headers.get("X-IVaaS-Signature"),
        ):
            self.log_error("Rejected webhook with an invalid IVaaS signature")
            self._respond(HTTPStatus.UNAUTHORIZED)
            return

        self.log_message(
            "Received valid webhook request_id=%s confirmation_code=%s bytes=%d",
            self.headers.get("X-IVaaS-Webhook-Request-Id", "-"),
            self.headers.get("X-VMI-Confirmation-Code", "-"),
            len(body),
        )
        self._respond(HTTPStatus.OK)

    def _respond(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main() -> None:
    # Safe for S104: Docker publishes this development-only service on host loopback.
    with ThreadingHTTPServer(
        ("0.0.0.0", urlsplit(_WEBHOOK_RECEIVER_URL).port or 80),  # noqa: S104
        _ProgramWebhookHandler,
    ) as server:
        print(f"Program webhook mock listening on {_WEBHOOK_RECEIVER_URL}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
