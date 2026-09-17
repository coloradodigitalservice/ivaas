"""Contract DTOs, aligned to the schemas in docs/api/open-api-spec.yaml.

Plain frozen dataclasses: this package depends on nothing but the standard
library. Validation enforces structural rules (field presence, formats, ordering, consistency);
Payload validation concerns belong to
* Adapters interacting with external datasources
* The IVaaS API layer

Immutability model:
* dataclasses are frozen (attribute reassignment raises)
* mappings are defensively copied at construction, so that later mutation of the caller's original
  cannot alter a DTO.
* Read-only `Mapping` type, which strict type checking enforces;
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from ivaas_core.constraints import (
    LAST4_SSN_PATTERN,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    NAME_PATTERN,
    SSN_PATTERN,
)


def _validate_name(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if len(value) < NAME_MIN_LENGTH:
        raise ValueError(f"{field_name} must be at least {NAME_MIN_LENGTH} characters")
    if len(value) > NAME_MAX_LENGTH:
        raise ValueError(f"{field_name} must be at most {NAME_MAX_LENGTH} characters")
    if not re.fullmatch(NAME_PATTERN, value):
        raise ValueError(f"{field_name} must not contain control characters")


def _validate_ssn_fields(ssn: str | None, last4_ssn: str | None) -> None:
    if (ssn is None) == (last4_ssn is None):
        raise ValueError("exactly one of ssn or last4_ssn must be provided")
    if ssn is not None and not re.fullmatch(SSN_PATTERN, ssn):
        raise ValueError("ssn must be nine digits (no separators)")
    if last4_ssn is not None and not re.fullmatch(LAST4_SSN_PATTERN, last4_ssn):
        raise ValueError("last4_ssn must be four digits")


@dataclass(frozen=True, slots=True)
class LookbackPeriod:
    """The window of time to return income for, both bounds inclusive.

    An adapter that cannot reach back to `start_date` should raise, so that returned data is
    unambiguously representative of the whole period
    """

    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")


class SourceStatus(StrEnum):
    """The outcome of one datasource lookup, in the API's per-source `status` vocabulary.

    ivaas reports it on each source result. Each contract exception declares the
    status it maps to, so an adapter that records outcomes at the datasource
    reports the same status ivaas will.
    """

    OK = "OK"
    NO_DATA = "NO_DATA"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class VerificationRequest:
    """What an income datasource needs to look up a subject.

    Exactly one of `ssn` or `last4_ssn` must be provided, depending on
    the needs of the downstream datasource. Both are suppressed from repr so
    request objects can be logged safely.
    """

    verification_id: UUID
    program_id: str
    requestor_id: str
    first_name: str
    last_name: str
    lookback_period: LookbackPeriod
    ssn: str | None = field(default=None, repr=False)
    last4_ssn: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.program_id:
            raise ValueError("program_id must not be empty")
        if not self.requestor_id:
            # TODO: It is not clear at the time of writing whether this identifier will be something
            #       every program can make available.
            #       As a result, this could be made optional or removed entirely.
            raise ValueError("requestor_id must not be empty")
        _validate_name(self.first_name, "first_name")
        _validate_name(self.last_name, "last_name")
        _validate_ssn_fields(self.ssn, self.last4_ssn)


@dataclass(frozen=True, slots=True)
class SourceIncome:
    """What an adapter returns for a successful lookup.

    The application must wrap this in the API's per-source envelope (source id,
    status). `retrieved_at` is an instant and must be timezone-aware.
    `raw_income` is the source's PII-stripped raw payload. Its shape is adapter-specific and is
    defined alongside the adapter that produces it.
    """

    retrieved_at: datetime
    raw_income: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        object.__setattr__(self, "raw_income", dict(self.raw_income))
