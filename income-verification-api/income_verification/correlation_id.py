"""Correlation ID contract and validation."""

import re

CORRELATION_ID_HEADER_NAME = "Correlation-Id"
CORRELATION_ID_MAX_LENGTH = 128
CORRELATION_ID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
    r"(:[A-Za-z0-9._~/-]+)?$"
)

_compiled_correlation_id_pattern = re.compile(CORRELATION_ID_PATTERN)


def validated_correlation_id(value: str | None) -> str | None:
    """Return a valid correlation ID without retaining invalid input."""
    if (
        value
        and len(value) <= CORRELATION_ID_MAX_LENGTH
        and _compiled_correlation_id_pattern.fullmatch(value)
    ):
        return value

    return None
