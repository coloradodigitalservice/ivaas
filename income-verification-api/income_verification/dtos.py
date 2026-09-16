"""Application-layer data transfer objects."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from ivaas_core import VerificationRequest as CoreVerificationRequest


@dataclass(frozen=True, slots=True)
class VerificationRequestEnvelope:
    """A validated core request plus API and application metadata."""

    application_id: str
    correlation_id: str
    core_request: CoreVerificationRequest
    verification_id: UUID = field(default_factory=uuid4)
