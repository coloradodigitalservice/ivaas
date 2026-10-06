"""Backup PII redaction for formatted application log messages."""

import logging
import re
from collections.abc import Mapping
from copy import copy
from dataclasses import fields, is_dataclass
from functools import cache
from typing import cast

from ivaas_core import SourceIncome
from ivaas_core import VerificationRequest as CoreVerificationRequest
from loggingredactor import RedactingFilter
from loggingredactor.common_pii_filters import EMAIL, PHONE, PII_KEYS
from pydantic import BaseModel

_REDACTION_MASK = "[REDACTED]"
_SSN_PATTERN = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
_BEARER_TOKEN_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:password|passwd|token|api[_-]?key|secret|otp|pin)\s*[:=]\s*"
    r"[\"']?[^\"',\s;}]+[\"']?",
    re.IGNORECASE,
)


_LOG_KEY_SEPARATORS = re.compile(r"[-_\s]")


def _normalized_log_key(key: object) -> str:
    return _LOG_KEY_SEPARATORS.sub("", str(key)).lower()


_SAFE_MODEL_KEYS = frozenset(
    _normalized_log_key(key)
    for key in (
        "application_id",
        "verification_id",
        "correlation_id",
        "agency_id",
        "source_id",
        "status",
        "retrieved_at",
    )
)
_SENSITIVE_LOG_KEYS = frozenset(
    _normalized_log_key(key)
    for key in (
        *PII_KEYS,
        "request",
        "response",
        "requestPayload",
        "responsePayload",
        "otp",
        "pin",
    )
)

_TEXT_REDACTOR = RedactingFilter(
    mask=_REDACTION_MASK,
    mask_patterns=(
        _SSN_PATTERN,
        _BEARER_TOKEN_PATTERN,
        _JWT_PATTERN,
        _SECRET_ASSIGNMENT_PATTERN,
        EMAIL,
        PHONE.US,
        PHONE.INTERNATIONAL,
    ),
)


def _sensitive_model_keys(model: type) -> frozenset[str]:
    """Return the model keys that are considered sensitive, and therefore should not be logged."""
    if is_dataclass(model):
        names = {field.name for field in fields(model)}
    elif issubclass(model, BaseModel):
        names = set(model.model_fields)
        names.update(field.alias for field in model.model_fields.values() if field.alias)
    else:
        return frozenset()
    return frozenset(_normalized_log_key(name) for name in names) - _SAFE_MODEL_KEYS


@cache
def _sensitive_message_keys() -> frozenset[str]:
    # Load API schemas after Django settings have initialized logging.
    from income_verification.schemas import SourceResult, VerificationRequest, VerificationResponse

    return _SENSITIVE_LOG_KEYS.union(
        *(
            _sensitive_model_keys(model)
            for model in (
                CoreVerificationRequest,
                SourceIncome,
                VerificationRequest,
                SourceResult,
                VerificationResponse,
            )
        )
    )


def _redact_log_value(value: object) -> object:
    """Mask schema-derived keys and default model fields to sensitive."""
    sensitive_keys = _sensitive_message_keys()
    if is_dataclass(value) and not isinstance(value, type):
        sensitive_keys |= _sensitive_model_keys(type(value))
        value = {field.name: getattr(value, field.name) for field in fields(value)}
    elif isinstance(value, BaseModel):
        sensitive_keys |= _sensitive_model_keys(type(value))
        value = value.model_dump()
    if isinstance(value, Mapping):
        return {
            key: _REDACTION_MASK
            if _normalized_log_key(key) in sensitive_keys
            else _redact_log_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return type(value)(_redact_log_value(item) for item in value)
    return value


def redacted_message(record: logging.LogRecord) -> str:
    """Return a copy of a log message with all sensitive values masked"""
    try:
        safe_record = copy(record)
        safe_record.msg = _redact_log_value(record.msg)
        safe_record.args = cast(
            tuple[object, ...] | Mapping[str, object], _redact_log_value(record.args)
        )
        return cast(str, _TEXT_REDACTOR.redact(safe_record.getMessage()))
    except Exception:
        # Redaction failures must neither expose the original message nor break a request.
        return "[REDACTED: log message could not be safely formatted]"
