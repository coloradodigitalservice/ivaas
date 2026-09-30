"""Application-layer data transfer objects."""

from dataclasses import dataclass

from ivaas_core import VerificationContext
from ivaas_core import VerificationRequest as CoreVerificationRequest


@dataclass(frozen=True, slots=True)
class VerificationRequestEnvelope:
    """A validated core request plus API and application metadata."""

    request: CoreVerificationRequest
    context: VerificationContext
