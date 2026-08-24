"""Contract between the ivaas platform and income datasource adapters.

Everything the application and adapters share lives here — and nothing else:
the ``IncomeSourceAdapter`` interface, the request/response DTOs, and the exception
types. This package depends only on the Python standard library.
"""

from ivaas_core.adapter import IncomeSourceAdapter
from ivaas_core.exceptions import (
    IncomeSourceError,
    SourceResponseInvalid,
    SourceTimeout,
    SourceUnavailable,
    SubjectNotFound,
)
from ivaas_core.models import (
    LookbackPeriod,
    SourceIncome,
    VerificationRequest,
)

__all__ = [
    "IncomeSourceAdapter",
    "IncomeSourceError",
    "LookbackPeriod",
    "SourceIncome",
    "SourceResponseInvalid",
    "SourceTimeout",
    "SourceUnavailable",
    "SubjectNotFound",
    "VerificationRequest",
]
