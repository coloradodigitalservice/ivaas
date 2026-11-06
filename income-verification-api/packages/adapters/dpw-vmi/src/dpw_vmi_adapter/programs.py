"""Resolve the program configured to receive DPW VMI webhooks."""

from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True, slots=True)
class DpwVmiProgram:
    """A program enrolled in the DPW VMI adapter.

    Attributes:
        program_id: Stable IVaaS program identifier.
        webhook_url: Configured destination for forwarded VMI webhooks.
        webhook_signing_key: Secret used to sign forwarded webhook bodies.
    """

    program_id: str
    webhook_url: str
    webhook_signing_key: str


def configured_programs() -> tuple[DpwVmiProgram, ...]:
    """Return the programs enrolled in DPW VMI. Rejects invalid configuration."""
    programs = []
    for program_id, program_settings in settings.PROGRAMS.items():
        if "dpw_vmi" not in program_settings:
            continue

        configuration = program_settings["dpw_vmi"]
        programs.append(
            DpwVmiProgram(
                program_id=program_id,
                webhook_url=_validated_webhook_url(program_id, configuration.get("webhook_url")),
                webhook_signing_key=_validated_webhook_signing_key(
                    program_id, configuration.get("webhook_signing_key")
                ),
            )
        )
    return tuple(programs)


def _validated_webhook_url(program_id: str, value: object) -> str:
    if not isinstance(value, str) or not _is_url(value):
        raise ImproperlyConfigured(
            f"PROGRAMS[{program_id!r}]['dpw_vmi']['webhook_url'] must be an HTTPS URL."
        )
    return value


def _validated_webhook_signing_key(program_id: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ImproperlyConfigured(
            f"PROGRAMS[{program_id!r}]['dpw_vmi']"
            "['webhook_signing_key'] must be a non-empty string."
        )
    return value


def _is_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return parsed.scheme in { "https", "http" } and parsed.hostname is not None and parsed.username is None
