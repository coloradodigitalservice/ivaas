"""Contract DTOs, aligned to the schemas in docs/api/open-api-spec.yaml.

Plain frozen dataclasses: this package depends on nothing but the standard
library. Validation enforces the structural rules the spec states where a
mistake is cheap to reject early (field presence, formats, ordering,
consistency); pure wire-format concerns (e.g. rendering ``Decimal`` as the
spec's two-decimal ``Dollar`` string) belong to the API layer.

Immutability model: dataclasses are frozen (attribute reassignment raises),
and mappings are defensively copied at construction so later mutation of the
caller's original cannot alter a DTO. The copies are exposed under the
read-only ``Mapping`` type, which strict type checking enforces; runtime
write-protection of mapping contents is deliberately not provided, keeping
the DTOs compatible with ``dataclasses.asdict`` and ordinary serializers.
Values nested inside ``raw_income`` are opaque and shared, not deep-copied —
adapters must not retain or mutate what they return.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

_SSN_PATTERN = re.compile(r"[0-9]{9}")
_LAST4_SSN_PATTERN = re.compile(r"[0-9]{4}")
# TODO: These should be more clearly enumerable
_MONTH_KEY_PATTERN = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
# Spec pattern for names: printable, no ASCII control characters.
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1F\x7F]")

_MAX_NAME_LENGTH = 256


def _validate_name(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > _MAX_NAME_LENGTH:
        raise ValueError(f"{field_name} must be at most {_MAX_NAME_LENGTH} characters")
    if _CONTROL_CHARS_PATTERN.search(value):
        raise ValueError(f"{field_name} must not contain control characters")


@dataclass(frozen=True, slots=True)
class LookbackPeriod:
    """The window of time to return income for, both bounds inclusive.

    A source that cannot reach back to ``start_date`` raises
    ``SourceUnavailable`` rather than returning a shortened window, so a
    caller never has to infer that it received less than it asked for.
    """

    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")


@dataclass(frozen=True, slots=True)
class VerificationRequest:
    """What an income datasource needs to look up a subject.

    Exactly one of ``ssn`` or ``last4_ssn`` must be provided, depending on
    the needs of the downstream datasource. Both are suppressed from repr so
    request objects can be logged safely.
    """

    first_name: str
    last_name: str
    lookback_period: LookbackPeriod
    ssn: str | None = field(default=None, repr=False)
    last4_ssn: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _validate_name(self.first_name, "first_name")
        _validate_name(self.last_name, "last_name")
        if (self.ssn is None) == (self.last4_ssn is None):
            raise ValueError("exactly one of ssn or last4_ssn must be provided")
        if self.ssn is not None and not _SSN_PATTERN.fullmatch(self.ssn):
            raise ValueError("ssn must be nine digits with no separators")
        if self.last4_ssn is not None and not _LAST4_SSN_PATTERN.fullmatch(self.last4_ssn):
            raise ValueError("last4_ssn must be four digits")


@dataclass(frozen=True, slots=True)
class NormalizedEmploymentRecord:
    """Normalized income from one employer for one calendar month."""

    employer_name: str
    amount: Decimal

    def __post_init__(self) -> None:
        _validate_name(self.employer_name, "employer_name")


@dataclass(frozen=True, slots=True)
class NormalizedMonthlyIncome:
    """One calendar month of income from a single source.

    ``total`` is the sum of ``records``, and it is derived, so a mismatch is a
    bug in the adapter and rejected here.

    TODO: total as an implementation detail of construction, or derived on demand instead?
    """

    total: Decimal
    records: tuple[NormalizedEmploymentRecord, ...]

    def __post_init__(self) -> None:
        expected = sum((record.amount for record in self.records), Decimal("0"))
        if self.total != expected:
            raise ValueError(f"total {self.total} does not equal sum of records {expected}")


@dataclass(frozen=True, slots=True)
class NormalizedIncome:
    """Income from a single source, restated into calendar months.

    Every value here is derived, not quoted from the source. Keys of
    ``months`` are ``YYYY-MM``.
    """

    months: Mapping[str, NormalizedMonthlyIncome]

    def __post_init__(self) -> None:
        for key in self.months:
            if not _MONTH_KEY_PATTERN.fullmatch(key):
                raise ValueError(f"month key {key!r} is not in YYYY-MM form")
        object.__setattr__(self, "months", dict(self.months))


@dataclass(frozen=True, slots=True)
class SourceIncome:
    """What an adapter returns for a successful lookup.

    TODO: validate this decision
    The application wraps this in the API's per-source envelope (source id,
    status). ``retrieved_at`` is an instant and must be timezone-aware.
    ``raw_income`` is the source's PII-stripped raw payload; its per-adapter
    shape is not yet specified (spec TBD), so it is carried as an opaque
    mapping for now. ``normalized_income`` is deliberately required even
    though the wire schema leaves it optional: producing normalized income
    is this platform's job, and the API layer can still choose what to emit.
    """

    retrieved_at: datetime
    normalized_income: NormalizedIncome
    raw_income: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if self.raw_income is not None:
            object.__setattr__(self, "raw_income", dict(self.raw_income))
