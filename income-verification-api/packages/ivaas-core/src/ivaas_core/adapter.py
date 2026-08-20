"""The interface every income datasource adapter implements."""

from abc import ABC, abstractmethod
from typing import ClassVar

from ivaas_core.models import SourceIncome, VerificationRequest


class IncomeSourceAdapter(ABC):
    """An adapter to an income datasource for the IVaaS platform to invoke.

    # TODO: Refine/remove this statement once settled
    Concrete adapters (one package per datasource, living outside this repo)
    subclass this. Constructors receive all configuration as keyword
    arguments assembled by application settings; adapters never read Django
    settings or their own environment. Constructors must not authenticate or
    touch the network — they run in every process that loads settings.
    """

    source_id: ClassVar[str]
    """Provenance identifier for this source."""

    @abstractmethod
    async def verify(self, request: VerificationRequest) -> SourceIncome:
        """Look up the subject's income for the requested window.

        Must either return within the adapter's configured timeout bound or
        raise ``SourceTimeout`` — an unbounded external call hangs a worker.
        Raises only contract exception types (``ivaas_core.exceptions``);
        vendor errors are caught, sanitized, and translated.
        """
