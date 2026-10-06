"""Importable-by-dotted-path fixture classes for registry tests, to mimic dynamic adapter imports"""

from datetime import UTC, datetime

from ivaas_core import (
    IncomeSourceAdapter,
    SourceIncome,
    SubjectNotFound,
    VerificationContext,
    VerificationRequest,
)


class StubSource(IncomeSourceAdapter):
    source_id = "STUB_1_0"

    def __init__(self, *, greeting: str = "hello") -> None:
        self.greeting = greeting

    def verify(self, request: VerificationRequest, context: VerificationContext) -> SourceIncome:
        raise SubjectNotFound("stub holds no records")


class MissingSourceId(IncomeSourceAdapter):
    def verify(self, request: VerificationRequest, context: VerificationContext) -> SourceIncome:
        return SourceIncome(retrieved_at=datetime.now(tz=UTC), raw_income={})


class NotASource:
    def __init__(self, **kwargs: object) -> None:
        pass
