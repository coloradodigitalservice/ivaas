"""The interface every income datasource adapter implements."""

from abc import ABC, abstractmethod
from typing import ClassVar

from ivaas_core.models import SourceIncome, VerificationRequest


class IncomeSource(ABC):
    """An income datasource, as the ivaas platform sees it.

    # TODO: Refine/remove this statement once settled
    Concrete adapters (one package per datasource, living outside this repo)
    subclass this. Constructors receive all configuration as keyword
    arguments assembled by application settings; adapters never read Django
    settings or their own environment. Constructors must not authenticate or
    touch the network — they run in every process that loads settings.
    """

    source_id: ClassVar[str]
    """Provenance identifier for this source, versioned with the adapter.
    Reported on every per-source API result.
    Presence is validated by the application's adapter registry at startup.
    Python cannot cheaply enforce ClassVar assignment at subclass
    definition time."""

    @abstractmethod
    async def verify(self, request: VerificationRequest) -> SourceIncome:
        """Look up the subject's income for the requested window.

        Must either return within the adapter's configured timeout bound or
        raise ``SourceTimeout`` — an unbounded external call hangs a worker.
        Raises only contract exception types (``ivaas_core.exceptions``);
        vendor errors are caught, sanitized, and translated.
        """
