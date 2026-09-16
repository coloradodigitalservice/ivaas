"""Contract tests for the ivaas-core package.

Exercises contract the way the application will use it.
"""

from collections.abc import Callable
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, date, datetime

import pytest
from ivaas_core import (
    LAST4_SSN_PATTERN,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    NAME_PATTERN,
    SSN_PATTERN,
    IncomeSourceAdapter,
    IncomeSourceError,
    LookbackPeriod,
    SourceIncome,
    SourceResponseInvalid,
    SourceTimeout,
    SourceUnavailable,
    SubjectNotFound,
    VerificationRequest,
)

MakeRequest = Callable[..., VerificationRequest]


def test_portable_validation_constraints_are_public() -> None:
    assert NAME_MIN_LENGTH == 1
    assert NAME_MAX_LENGTH == 256
    assert NAME_PATTERN == r"^[^\x00-\x1F\x7F]+$"
    assert SSN_PATTERN == r"^[0-9]{9}$"
    assert LAST4_SSN_PATTERN == r"^[0-9]{4}$"


@pytest.fixture
def make_request(last_calendar_month: LookbackPeriod) -> MakeRequest:
    def _make_request(**overrides: object) -> VerificationRequest:
        fields: dict[str, object] = {
            "first_name": "John",
            "last_name": "Doe",
            "lookback_period": last_calendar_month,
            "last4_ssn": "1234",
        }
        fields.update(overrides)
        return VerificationRequest(**fields)  # type: ignore[arg-type]

    return _make_request


class StubSource(IncomeSourceAdapter):
    source_id = "STUB_1_0"

    def __init__(self, *, subject_exists: bool = True, times_out: bool = False) -> None:
        self.subject_exists = subject_exists
        self.times_out = times_out

    def verify(self, request: VerificationRequest) -> SourceIncome:
        if self.times_out:
            raise SourceTimeout("stub timed out")
        if not self.subject_exists:
            raise SubjectNotFound("stub holds no records")
        return SourceIncome(
            retrieved_at=datetime(2026, 8, 19, tzinfo=UTC),
            raw_income={"entries": [{"employer_name": "Food and Stuff", "gross_wages": "1300.00"}]},
        )


class TestIncomeSourceAdapterInterface:
    def test_conforming_adapter_is_an_income_source(self) -> None:
        assert isinstance(StubSource(), IncomeSourceAdapter)

    def test_interface_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            IncomeSourceAdapter()  # type: ignore[abstract]

    def test_verify_returns_source_income(self, make_request: MakeRequest) -> None:
        result = StubSource().verify(make_request())

        assert isinstance(result, SourceIncome)
        assert result.raw_income["entries"] == [
            {"employer_name": "Food and Stuff", "gross_wages": "1300.00"}
        ]

    def test_contract_exceptions_are_caught_by_identity(self, make_request: MakeRequest) -> None:
        with pytest.raises(SubjectNotFound):
            StubSource(subject_exists=False).verify(make_request())
        with pytest.raises(SourceTimeout):
            StubSource(times_out=True).verify(make_request())

    def test_contract_exceptions_share_a_base(self, make_request: MakeRequest) -> None:
        with pytest.raises(IncomeSourceError):
            StubSource(times_out=True).verify(make_request())

    def test_invalid_response_exception_maps_to_error_status(self) -> None:
        assert issubclass(SourceResponseInvalid, IncomeSourceError)
        assert not issubclass(SourceResponseInvalid, SourceUnavailable)


class TestVerificationRequest:
    def test_accepts_last4_ssn(self, make_request: MakeRequest) -> None:
        assert make_request().last4_ssn == "1234"

    def test_accepts_full_ssn(self, make_request: MakeRequest) -> None:
        request = make_request(ssn="123001234", last4_ssn=None)

        assert request.ssn == "123001234"

    def test_rejects_both_ssn_forms(self, make_request: MakeRequest) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            make_request(ssn="123001234")

    def test_rejects_neither_ssn_form(self, make_request: MakeRequest) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            make_request(last4_ssn=None)

    @pytest.mark.parametrize("ssn", ["12300123", "1230012345", "12300123a", "123001234\n"])
    def test_rejects_malformed_ssn(self, make_request: MakeRequest, ssn: str) -> None:
        with pytest.raises(ValueError, match="nine digits"):
            make_request(ssn=ssn, last4_ssn=None)

    @pytest.mark.parametrize("last4_ssn", ["123", "12345", "12a4", "1234\n"])
    def test_rejects_malformed_last4_ssn(self, make_request: MakeRequest, last4_ssn: str) -> None:
        with pytest.raises(ValueError, match="four digits"):
            make_request(last4_ssn=last4_ssn)

    @pytest.mark.parametrize("field_name", ["first_name", "last_name"])
    def test_rejects_empty_names(self, make_request: MakeRequest, field_name: str) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            make_request(**{field_name: ""})

    @pytest.mark.parametrize("field_name", ["first_name", "last_name"])
    def test_rejects_control_characters_in_names(
        self, make_request: MakeRequest, field_name: str
    ) -> None:
        with pytest.raises(ValueError, match="control characters"):
            make_request(**{field_name: "Jo\x00hn"})

    @pytest.mark.parametrize("field_name", ["first_name", "last_name"])
    def test_rejects_overlong_names(self, make_request: MakeRequest, field_name: str) -> None:
        with pytest.raises(ValueError, match="at most 256"):
            make_request(**{field_name: "x" * 257})

    def test_ssn_suppressed_from_repr(self, make_request: MakeRequest) -> None:
        rendered = repr(make_request(ssn="123001234", last4_ssn=None))

        assert "123001234" not in rendered
        assert "1234" not in rendered

    def test_requests_are_immutable(self, make_request: MakeRequest) -> None:
        with pytest.raises(FrozenInstanceError):
            make_request().first_name = "Jane"  # type: ignore[misc]


class TestLookbackPeriod:
    def test_rejects_end_before_start(self) -> None:
        with pytest.raises(ValueError, match="must not precede"):
            LookbackPeriod(start_date=date(2026, 6, 30), end_date=date(2026, 1, 1))

    def test_single_day_window_is_valid(self) -> None:
        day = date(2026, 3, 15)

        assert LookbackPeriod(start_date=day, end_date=day).start_date == day


class TestSourceIncome:
    def test_rejects_naive_retrieved_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            SourceIncome(retrieved_at=datetime(2026, 8, 19), raw_income={})

    def test_raw_income_is_required(self) -> None:
        with pytest.raises(TypeError):
            SourceIncome(retrieved_at=datetime(2026, 8, 19, tzinfo=UTC))  # type: ignore[call-arg]

    def test_raw_income_defensively_copies_the_input_mapping(self) -> None:
        source_dict: dict[str, object] = {"quarters": (1, 2)}
        result = SourceIncome(
            retrieved_at=datetime(2026, 8, 19, tzinfo=UTC),
            raw_income=source_dict,
        )
        source_dict["quarters"] = (1, 2, 3)
        source_dict["extra"] = True

        assert result.raw_income["quarters"] == (1, 2)
        assert "extra" not in result.raw_income

    def test_dtos_serialize_with_dataclasses_asdict(self) -> None:
        result = SourceIncome(
            retrieved_at=datetime(2026, 8, 19, tzinfo=UTC),
            raw_income={"entries": []},
        )

        assert asdict(result)["raw_income"] == {"entries": []}
