"""Contract between the ivaas platform and income datasource adapters.

Everything the application and adapters share lives here — and nothing else:
the ``IncomeSource`` interface, the request/response DTOs, and the exception
types. This package depends only on the Python standard library.
"""

from ivaas_core.exceptions import (
    IncomeSourceError,
    SourceResponseInvalid,
    SourceTimeout,
    SourceUnavailable,
    SubjectNotFound,
)
from ivaas_core.models import (
    LookbackPeriod,
    NormalizedEmploymentRecord,
    NormalizedIncome,
    NormalizedMonthlyIncome,
    SourceIncome,
    VerificationRequest,
)
from ivaas_core.source import IncomeSource

__all__ = [
    "IncomeSource",
    "IncomeSourceError",
    "LookbackPeriod",
    "NormalizedEmploymentRecord",
    "NormalizedIncome",
    "NormalizedMonthlyIncome",
    "SourceIncome",
    "SourceResponseInvalid",
    "SourceTimeout",
    "SourceUnavailable",
    "SubjectNotFound",
    "VerificationRequest",
]
