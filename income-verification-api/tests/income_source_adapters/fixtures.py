"""Importable-by-dotted-path fixture classes for registry tests."""

from datetime import UTC, datetime

from ivaas_core import (
    IncomeSourceAdapter,
    NormalizedIncome,
    SourceIncome,
    SubjectNotFound,
    VerificationRequest,
)


class StubSource(IncomeSourceAdapter):
    source_id = "STUB_1_0"

    def __init__(self, *, greeting: str = "hello") -> None:
        self.greeting = greeting

    async def verify(self, request: VerificationRequest) -> SourceIncome:
        raise SubjectNotFound("stub holds no records")


class MissingSourceId(IncomeSourceAdapter):
    async def verify(self, request: VerificationRequest) -> SourceIncome:
        return SourceIncome(
            retrieved_at=datetime.now(tz=UTC),
            normalized_income=NormalizedIncome(months={}),
        )


class NotASource:
    def __init__(self, **kwargs: object) -> None:
        pass
