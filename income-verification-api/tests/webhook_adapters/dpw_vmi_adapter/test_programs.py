"""Check DPW VMI program configuration."""

from collections.abc import Mapping
from importlib import import_module

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from dpw_vmi_adapter.apps import DpwVmiAdapterConfig
from dpw_vmi_adapter.programs import DpwVmiProgram, configured_programs

PROGRAM_ID = "test-program"
WEBHOOK_URL = "https://program.example/webhook"
WEBHOOK_SIGNING_KEY = "test-webhook-signing-key"
WEBHOOK_ADAPTERS = {
    "dpw_vmi_adapter": {
        "enabled": True,
        "config": {
            "webhook_path": "/dpw-vmi/v1/income-report",
            "webhook_api_key": "dpw-vmi-test-key",
            "webhook_timestamp_max_age_seconds": 300,
            "program_timeout_seconds": 10,
        },
    },
}


def program_configuration(
    webhook_url: object = WEBHOOK_URL,
    webhook_signing_key: object = WEBHOOK_SIGNING_KEY,
) -> Mapping[str, Mapping[str, object]]:
    return {
        "dpw_vmi": {
            "webhook_url": webhook_url,
            "webhook_signing_key": webhook_signing_key,
        },
    }


@pytest.mark.parametrize(
    ("webhook_url", "webhook_signing_key", "message"),
    [
        (None, WEBHOOK_SIGNING_KEY, "webhook_url"),
        ("ftp://program.example/webhook", WEBHOOK_SIGNING_KEY, "webhook_url"),
        ("http://program.example/webhook", WEBHOOK_SIGNING_KEY, "webhook_url"),
        ("https://user:password@program.example/webhook", WEBHOOK_SIGNING_KEY, "webhook_url"),
        ("https://program.example:not-a-port/webhook", WEBHOOK_SIGNING_KEY, "webhook_url"),
        (WEBHOOK_URL, None, "webhook_signing_key"),
        (WEBHOOK_URL, "", "webhook_signing_key"),
    ],
)
def test_configured_programs_requires_webhook_configuration(
    webhook_url: object,
    webhook_signing_key: object,
    message: str,
) -> None:
    with (
        override_settings(
            DEBUG=False,
            PROGRAMS={PROGRAM_ID: program_configuration(webhook_url, webhook_signing_key)},
        ),
        pytest.raises(ImproperlyConfigured, match=message),
    ):
        configured_programs()


def test_configured_programs_allows_http_in_debug_mode() -> None:
    webhook_url = "http://localhost:9000/webhook"

    with override_settings(
        DEBUG=True,
        PROGRAMS={PROGRAM_ID: program_configuration(webhook_url=webhook_url)},
    ):
        result = configured_programs()

    assert result[0].webhook_url == webhook_url


@pytest.mark.parametrize(
    "webhook_url",
    ["ftp://localhost/webhook", "http:///webhook", "http://user:password@localhost/webhook"],
)
def test_configured_programs_rejects_other_invalid_urls_in_debug_mode(
    webhook_url: str,
) -> None:
    with (
        override_settings(
            DEBUG=True,
            PROGRAMS={PROGRAM_ID: program_configuration(webhook_url=webhook_url)},
        ),
        pytest.raises(ImproperlyConfigured, match="webhook_url"),
    ):
        configured_programs()


def test_configured_programs_returns_all_enrolled_programs() -> None:
    programs = {
        PROGRAM_ID: program_configuration(),
        "second-program": program_configuration(
            "https://second.example/webhook", "second-webhook-signing-key"
        ),
        "other-program": {},
    }

    with override_settings(PROGRAMS=programs):
        result = configured_programs()

    assert result == (
        DpwVmiProgram(
            program_id=PROGRAM_ID,
            webhook_url=WEBHOOK_URL,
            webhook_signing_key=WEBHOOK_SIGNING_KEY,
        ),
        DpwVmiProgram(
            program_id="second-program",
            webhook_url="https://second.example/webhook",
            webhook_signing_key="second-webhook-signing-key",
        ),
    )


@pytest.mark.parametrize(
    ("programs", "error"),
    [
        ({}, "requires at least one program"),
        (
            {
                "first-program": program_configuration(),
                "second-program": program_configuration(),
            },
            "currently supports only one program",
        ),
    ],
)
def test_app_ready_requires_exactly_one_program(
    programs: Mapping[str, Mapping[str, Mapping[str, object]]],
    error: str,
) -> None:
    app_module = import_module("dpw_vmi_adapter")
    app_config = DpwVmiAdapterConfig("dpw_vmi_adapter", app_module)

    with (
        override_settings(PROGRAMS=programs, WEBHOOK_ADAPTERS=WEBHOOK_ADAPTERS),
        pytest.raises(ImproperlyConfigured, match=error),
    ):
        app_config.ready()
