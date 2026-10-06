import io
import json
import logging

import pytest
from django.conf import settings

from income_verification.request_context import JsonLogFormatter, LogField


def test_every_declared_adapter_package_logs_like_the_engine() -> None:
    engine_logger = settings.LOGGING["loggers"]["adapter_engine"]

    for declaration in settings.INCOME_SOURCE_ADAPTERS.values():
        package = str(declaration["class"]).partition(".")[0]
        assert settings.LOGGING["loggers"][package] == engine_logger


def test_engine_and_adapter_handlers_redact_messages_and_preserve_source_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packages = {"adapter_engine"} | {
        str(declaration["class"]).partition(".")[0]
        for declaration in settings.INCOME_SOURCE_ADAPTERS.values()
    }
    for package in packages:
        logger = logging.getLogger(package)
        stream = io.StringIO()
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and isinstance(
                handler.formatter, JsonLogFormatter
            ):
                monkeypatch.setattr(handler, "stream", stream)

        logger.warning(
            "lookup failed: %s",
            {"firstName": "SensitiveGivenName", "ssn": "123456789"},
            extra={LogField.SOURCE_ID.value: "test-source"},
        )

        output = json.loads(stream.getvalue())
        assert "SensitiveGivenName" not in output["message"]
        assert "123456789" not in output["message"]
        assert "[REDACTED]" in output["message"]
        assert output[LogField.SOURCE_ID.value] == "test-source"
