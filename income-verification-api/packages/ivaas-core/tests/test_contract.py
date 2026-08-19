"""Contract tests for the ivaas-core package.

Exercises the contract the way the application will use it: a minimal
conforming adapter is instantiated, type-checked against the interface, and
its contract exceptions are caught by identity.
"""

import asyncio
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from ivaas_core import (
    IncomeSource,
    IncomeSourceError,
    LookbackPeriod,
    NormalizedEmploymentRecord,
    NormalizedIncome,
    NormalizedMonthlyIncome,
    SourceIncome,
    SourceResponseInvalid,
    SourceTimeout,
    SourceUnavailable,
    SubjectNotFound,
    VerificationRequest,
)


def last_calendar_month() -> LookbackPeriod:
    """The most recently completed calendar month, first day through last day."""
    first_of_current_month = date.today().replace(day=1)
    last_day_of_previous_month = first_of_current_month - timedelta(days=1)
    first_day_of_previous_month = last_day_of_previous_month.replace(day=1)
    return LookbackPeriod(
        start_date=first_day_of_previous_month,
        end_date=last_day_of_previous_month,
    )


LOOKBACK = last_calendar_month()


def make_request(**overrides: object) -> VerificationRequest:
    fields: dict[str, object] = {
        "first_name": "John",
        "last_name": "Doe",
        "lookback_period": LOOKBACK,
        "last4_ssn": "1234",
    }
    fields.update(overrides)
    return VerificationRequest(**fields)  # type: ignore[arg-type]


class StubSource(IncomeSource):
    source_id = "STUB_1_0"

    def __init__(self, *, subject_exists: bool = True, times_out: bool = False) -> None:
        self.subject_exists = subject_exists
        self.times_out = times_out

    async def verify(self, request: VerificationRequest) -> SourceIncome:
        if self.times_out:
            raise SourceTimeout("stub timed out")
        if not self.subject_exists:
            raise SubjectNotFound("stub holds no records")
        month = NormalizedMonthlyIncome(
            total=Decimal("1300.00"),
            records=(
                NormalizedEmploymentRecord(
                    employer_name="Food and Stuff", amount=Decimal("1300.00")
                ),
            ),
        )
        return SourceIncome(
            retrieved_at=datetime(2026, 8, 19, tzinfo=UTC),
            normalized_income=NormalizedIncome(months={"2026-03": month}),
        )


class TestIncomeSourceInterface:
    def test_conforming_adapter_is_an_income_source(self) -> None:
        assert isinstance(StubSource(), IncomeSource)

    def test_interface_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            IncomeSource()  # type: ignore[abstract]

    def test_verify_returns_source_income(self) -> None:
        result = asyncio.run(StubSource().verify(make_request()))

        assert isinstance(result, SourceIncome)
        assert result.normalized_income.months["2026-03"].total == Decimal("1300.00")

    def test_contract_exceptions_are_caught_by_identity(self) -> None:
        with pytest.raises(SubjectNotFound):
            asyncio.run(StubSource(subject_exists=False).verify(make_request()))
        with pytest.raises(SourceTimeout):
            asyncio.run(StubSource(times_out=True).verify(make_request()))

    def test_contract_exceptions_share_a_base(self) -> None:
        with pytest.raises(IncomeSourceError):
            asyncio.run(StubSource(times_out=True).verify(make_request()))

    def test_invalid_response_exception_maps_to_error_status(self) -> None:
        assert issubclass(SourceResponseInvalid, IncomeSourceError)
        assert not issubclass(SourceResponseInvalid, SourceUnavailable)


class TestVerificationRequest:
    def test_accepts_last4_ssn(self) -> None:
        assert make_request().last4_ssn == "1234"

    def test_accepts_full_ssn(self) -> None:
        request = make_request(ssn="123001234", last4_ssn=None)

        assert request.ssn == "123001234"

    def test_rejects_both_ssn_forms(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            make_request(ssn="123001234")

    def test_rejects_neither_ssn_form(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            make_request(last4_ssn=None)

    @pytest.mark.parametrize("ssn", ["12300123", "1230012345", "12300123a", "123001234\n"])
    def test_rejects_malformed_ssn(self, ssn: str) -> None:
        with pytest.raises(ValueError, match="nine digits"):
            make_request(ssn=ssn, last4_ssn=None)

    @pytest.mark.parametrize("last4_ssn", ["123", "12345", "12a4", "1234\n"])
    def test_rejects_malformed_last4_ssn(self, last4_ssn: str) -> None:
        with pytest.raises(ValueError, match="four digits"):
            make_request(last4_ssn=last4_ssn)

    @pytest.mark.parametrize("field_name", ["first_name", "last_name"])
    def test_rejects_empty_names(self, field_name: str) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            make_request(**{field_name: ""})

    @pytest.mark.parametrize("field_name", ["first_name", "last_name"])
    def test_rejects_control_characters_in_names(self, field_name: str) -> None:
        with pytest.raises(ValueError, match="control characters"):
            make_request(**{field_name: "Jo\x00hn"})

    @pytest.mark.parametrize("field_name", ["first_name", "last_name"])
    def test_rejects_overlong_names(self, field_name: str) -> None:
        with pytest.raises(ValueError, match="at most 256"):
            make_request(**{field_name: "x" * 257})

    def test_ssn_suppressed_from_repr(self) -> None:
        rendered = repr(make_request(ssn="123001234", last4_ssn=None))

        assert "123001234" not in rendered
        assert "1234" not in rendered

    def test_requests_are_immutable(self) -> None:
        with pytest.raises(FrozenInstanceError):
            make_request().first_name = "Jane"  # type: ignore[misc]


class TestLookbackPeriod:
    def test_rejects_end_before_start(self) -> None:
        with pytest.raises(ValueError, match="must not precede"):
            LookbackPeriod(start_date=date(2026, 6, 30), end_date=date(2026, 1, 1))

    def test_single_day_window_is_valid(self) -> None:
        day = date(2026, 3, 15)

        assert LookbackPeriod(start_date=day, end_date=day).start_date == day


def make_month(amount: str = "1300.00") -> NormalizedMonthlyIncome:
    return NormalizedMonthlyIncome(
        total=Decimal(amount),
        records=(
            NormalizedEmploymentRecord(employer_name="Food and Stuff", amount=Decimal(amount)),
        ),
    )


class TestNormalizedIncome:
    def test_rejects_total_that_is_not_sum_of_records(self) -> None:
        with pytest.raises(ValueError, match="does not equal sum"):
            NormalizedMonthlyIncome(
                total=Decimal("100.00"),
                records=(
                    NormalizedEmploymentRecord(employer_name="A", amount=Decimal("1.00")),
                    NormalizedEmploymentRecord(employer_name="B", amount=Decimal("2.00")),
                ),
            )

    def test_empty_months_are_valid(self) -> None:
        assert NormalizedIncome(months={}).months == {}

    @pytest.mark.parametrize("key", ["2026-13", "2026-0", "202603", "2026-03\n", "march"])
    def test_rejects_malformed_month_keys(self, key: str) -> None:
        with pytest.raises(ValueError, match="YYYY-MM"):
            NormalizedIncome(months={key: make_month()})

    def test_rejects_empty_employer_name(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            NormalizedEmploymentRecord(employer_name="", amount=Decimal("1.00"))

    def test_months_defensively_copies_the_input_mapping(self) -> None:
        source_dict = {"2026-03": make_month()}
        income = NormalizedIncome(months=source_dict)
        source_dict["2026-04"] = make_month()

        assert "2026-04" not in income.months

    def test_dtos_serialize_with_dataclasses_asdict(self) -> None:
        income = NormalizedIncome(months={"2026-03": make_month()})

        serialized = asdict(income)

        assert serialized["months"]["2026-03"]["total"] == Decimal("1300.00")


class TestSourceIncome:
    def test_rejects_naive_retrieved_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            SourceIncome(
                retrieved_at=datetime(2026, 8, 19),
                normalized_income=NormalizedIncome(months={}),
            )

    def test_raw_income_defensively_copies_the_input_mapping(self) -> None:
        source_dict: dict[str, object] = {"quarters": (1, 2)}
        result = SourceIncome(
            retrieved_at=datetime(2026, 8, 19, tzinfo=UTC),
            normalized_income=NormalizedIncome(months={}),
            raw_income=source_dict,
        )
        source_dict["extra"] = True

        assert result.raw_income is not None
        assert "extra" not in result.raw_income
