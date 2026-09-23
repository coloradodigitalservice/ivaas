"""Application-layer data transfer objects."""

from dataclasses import dataclass
from uuid import UUID

from ivaas_core import VerificationRequest as CoreVerificationRequest


@dataclass(frozen=True, slots=True)
class VerificationRequestEnvelope:
    """A validated core request plus API and application metadata."""

    application_id: str
    correlation_id: str
    verification_id: UUID
    core_request: CoreVerificationRequest
