"""Resolve the program configured to receive DPW VMI webhooks."""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True, slots=True)
class DpwVmiProgram:
    """A program enrolled in the DPW VMI adapter."""

    program_id: str
    webhook_api_key: str


def configured_programs() -> tuple[DpwVmiProgram, ...]:
    """Return the programs enrolled in DPW VMI. Rejects invalid configuration."""
    programs = []
    for program_id, program_settings in settings.PROGRAMS.items():
        if "dpw_vmi" not in program_settings:
            continue

        configuration = program_settings["dpw_vmi"]
        webhook_api_key = configuration.get("webhook_api_key")
        if not isinstance(webhook_api_key, str) or not webhook_api_key:
            raise ImproperlyConfigured(
                f"PROGRAMS[{program_id!r}]['dpw_vmi']"
                "['webhook_api_key'] must be a non-empty string."
            )
        programs.append(DpwVmiProgram(program_id=program_id, webhook_api_key=webhook_api_key))
    return tuple(programs)
