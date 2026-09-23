"""A reference implementation of the ivaas-core adapter contract that noops.

It is not an income source. It shows the shape of an adapter and stands in for
an actual adapter implementation for integration testing.
"""

import logging
from datetime import UTC, datetime
from typing import override

from ivaas_core import IncomeSourceAdapter, SourceIncome, VerificationRequest

logger = logging.getLogger(__name__)


class ExampleAdapter(IncomeSourceAdapter):
    """
    For example and testing purposes only.

    Answers every lookup with an empty raw income.
    """

    source_id = "EXAMPLE_1_0"

    def __init__(self, *, timeout_seconds: int = 5) -> None:
        # Settings arrive as keyword arguments; this one only shows the shape and is never
        # used.
        self.timeout_seconds = timeout_seconds

    @override
    def verify(self, request: VerificationRequest) -> SourceIncome:
        """Log the call and succeed with no income. A real adapter queries its source here."""
        logger.info("example adapter called for verification %s", request.verification_id)
        return SourceIncome(retrieved_at=datetime.now(UTC), raw_income={})
