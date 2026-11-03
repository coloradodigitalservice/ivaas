"""Check DPW VMI program configuration."""

from collections.abc import Mapping
from importlib import import_module

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from dpw_vmi_adapter.apps import DpwVmiAdapterConfig
from dpw_vmi_adapter.programs import DpwVmiProgram, configured_programs

PROGRAM_ID = "test-program"
WEBHOOK_API_KEY = "test-webhook-api-key"
WEBHOOK_ADAPTERS = {
    "dpw_vmi_adapter": {
        "enabled": True,
        "config": {
            "webhook_path": "/dpw-vmi/v1/income-report",
            "webhook_api_key": "dpw-vmi-test-key",
            "webhook_timestamp_max_age_seconds": 300,
        },
    },
}


def program_configuration(
    webhook_api_key: object = WEBHOOK_API_KEY,
) -> Mapping[str, Mapping[str, object]]:
    return {
        "dpw_vmi": {
            "webhook_api_key": webhook_api_key,
        },
    }


@pytest.mark.parametrize("webhook_api_key", [None, ""])
def test_configured_programs_requires_webhook_api_key(webhook_api_key: object) -> None:
    with (
        override_settings(PROGRAMS={PROGRAM_ID: program_configuration(webhook_api_key)}),
        pytest.raises(ImproperlyConfigured, match="webhook_api_key"),
    ):
        configured_programs()


def test_configured_programs_returns_all_enrolled_programs() -> None:
    programs = {
        PROGRAM_ID: program_configuration(),
        "second-program": program_configuration("second-webhook-api-key"),
        "other-program": {},
    }

    with override_settings(PROGRAMS=programs):
        result = configured_programs()

    assert result == (
        DpwVmiProgram(
            program_id=PROGRAM_ID,
            webhook_api_key=WEBHOOK_API_KEY,
        ),
        DpwVmiProgram(
            program_id="second-program",
            webhook_api_key="second-webhook-api-key",
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
