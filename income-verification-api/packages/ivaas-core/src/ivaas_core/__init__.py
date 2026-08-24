"""Contract between the ivaas platform and income datasource adapters.

Everything the application and adapters share lives here, and nothing else.
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
