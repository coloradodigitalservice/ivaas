from abc import ABC, abstractmethod
from typing import ClassVar

from ivaas_core.models import SourceIncome, VerificationRequest


class IncomeSourceAdapter(ABC):
    """
    The interface every income datasource adapter implements, and IVaaS invokes.
    Concrete adapters subclass this.
    """

    source_id: ClassVar[str]
    """Provenance identifier for this source."""

    @abstractmethod
    async def verify(self, request: VerificationRequest) -> SourceIncome:
        """Perform income verification routine, based on the requested parameters.

        Should raise only contract exception types (``ivaas_core.exceptions``);
        Vendor errors should be caught, sanitized, and translated accordingly.

        See ./exceptions.py
        """
