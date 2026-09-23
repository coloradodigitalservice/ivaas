"""Contract between the ivaas platform and income datasource adapters.

Everything the application and adapters share lives here, and nothing else.
"""

from ivaas_core.adapter import IncomeSourceAdapter
from ivaas_core.constraints import (
    LAST4_SSN_PATTERN,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    NAME_PATTERN,
    SSN_PATTERN,
)
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
    SourceStatus,
    VerificationRequest,
)

__all__ = [
    "LAST4_SSN_PATTERN",
    "NAME_MAX_LENGTH",
    "NAME_MIN_LENGTH",
    "NAME_PATTERN",
    "SSN_PATTERN",
    "IncomeSourceAdapter",
    "IncomeSourceError",
    "LookbackPeriod",
    "SourceIncome",
    "SourceResponseInvalid",
    "SourceStatus",
    "SourceTimeout",
    "SourceUnavailable",
    "SubjectNotFound",
    "VerificationRequest",
]
