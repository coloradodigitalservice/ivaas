"""Authenticate inbound DPW VMI webhook requests."""

import logging
import re
import time
from typing import NoReturn, cast, override

from django.apps import apps
from django.http import HttpRequest
from ninja.security import APIKeyHeader

from dpw_vmi_adapter.apps import DpwVmiAdapterConfig
from dpw_vmi_adapter.signing import verify
from income_verification.request_context import LogField

logger = logging.getLogger(__name__)
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{128}\Z")
_FUTURE_TIMESTAMP_TOLERANCE_SECONDS = 5


class DpwVmiAuthenticationError(Exception):
    """Reject a webhook without exposing the failed check to the sender."""


def _reject(reason: str, detail: str) -> NoReturn:
    logger.warning(
        "DPW VMI webhook header validation failed: %s",
        detail,
        extra={
            LogField.EVENT_NAME.value: "dpw_vmi.webhook.header_validation_failed",
            LogField.AUTH_FAILURE_REASON.value: reason,
            LogField.HTTP_RESPONSE_STATUS_CODE.value: 401,
        },
    )
    raise DpwVmiAuthenticationError


class DpwVmiSignature(APIKeyHeader):
    """Check the signed raw request body before webhook processing."""

    param_name = "X-VMI-Signature"

    @override
    def authenticate(self, request: HttpRequest, signature: str | None) -> str:
        configuration = cast(DpwVmiAdapterConfig, apps.get_app_config("dpw_vmi_adapter"))
        timestamp = request.headers.get("X-VMI-Timestamp")
        if timestamp is None:
            _reject("missing_timestamp", "Missing X-VMI-Timestamp header.")
        if len(timestamp) > 20 or not timestamp.isascii() or not timestamp.isdigit():
            _reject("invalid_timestamp", "X-VMI-Timestamp must be Unix seconds.")
        signed_at = int(timestamp)

        if signature is None:
            _reject("missing_signature", "Missing X-VMI-Signature header.")
        if _SIGNATURE_PATTERN.fullmatch(signature) is None:
            _reject("invalid_signature", "X-VMI-Signature must be 128 lowercase hex characters.")
        confirmation_code = request.headers.get("X-VMI-Confirmation-Code")
        if not confirmation_code or not confirmation_code.strip():
            _reject("missing_confirmation_code", "Missing X-VMI-Confirmation-Code header.")
        if not verify(
            request.body,
            key=configuration.webhook_api_key,
            timestamp=timestamp,
            signature=signature,
        ):
            _reject("signature_mismatch", "X-VMI-Signature does not match the request.")

        age = time.time() - signed_at
        if age < -_FUTURE_TIMESTAMP_TOLERANCE_SECONDS:
            _reject("future_timestamp", "X-VMI-Timestamp is too far in the future.")
        if age > configuration.webhook_timestamp_max_age_seconds:
            _reject("expired_timestamp", "X-VMI-Timestamp is too old.")
        return signature
