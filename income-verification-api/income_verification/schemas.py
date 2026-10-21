"""Schemas for the program-facing IVaaS API."""

from collections.abc import Mapping
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from ivaas_core import (
    LAST4_SSN_PATTERN,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    NAME_PATTERN,
    SSN_PATTERN,
    SourceStatus,
    VerificationContext,
)
from ivaas_core import LookbackPeriod as CoreLookbackPeriod
from ivaas_core import VerificationRequest as CoreVerificationRequest
from ninja import Field, Schema
from pydantic import ConfigDict, model_validator
from pydantic.alias_generators import to_camel
from pydantic_core import PydanticCustomError

from income_verification.api_error_codes import ERRORS, ErrorCode
from income_verification.dtos import VerificationRequestEnvelope


class ApiSchema(Schema):
    """Accept only camel-case API aliases while exposing snake-case attributes."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=False,
    )


class VerificationRequest(ApiSchema):
    model_config = ConfigDict(
        json_schema_extra={
            "oneOf": [
                {"required": ["ssn"]},
                {"required": ["last4Ssn"]},
            ]
        }
    )

    application_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[\x20-\x7E]+$",
    )
    first_name: str = Field(
        min_length=NAME_MIN_LENGTH,
        max_length=NAME_MAX_LENGTH,
        pattern=NAME_PATTERN,
    )
    last_name: str = Field(
        min_length=NAME_MIN_LENGTH,
        max_length=NAME_MAX_LENGTH,
        pattern=NAME_PATTERN,
    )
    ssn: str | None = Field(default=None, pattern=SSN_PATTERN, repr=False)
    last4_ssn: str | None = Field(default=None, pattern=LAST4_SSN_PATTERN, repr=False)
    lookback_period: CoreLookbackPeriod

    @model_validator(mode="after")
    def request_must_be_valid(self) -> Self:
        if self.ssn is None and self.last4_ssn is None:
            code = ErrorCode.MISSING_IDENTITY_IDENTIFIER
            raise PydanticCustomError(
                code.value,
                ERRORS[code].message,
            )

        if self.ssn is not None and self.last4_ssn is not None:
            code = ErrorCode.MULTIPLE_IDENTITY_IDENTIFIERS
            raise PydanticCustomError(
                code.value,
                ERRORS[code].message,
            )

        return self

    def _to_core_request(self) -> CoreVerificationRequest:
        return CoreVerificationRequest(
            first_name=self.first_name,
            last_name=self.last_name,
            ssn=self.ssn,
            last4_ssn=self.last4_ssn,
            lookback_period=self.lookback_period,
        )

    def to_envelope(self, correlation_id: str, *, agency_id: str) -> VerificationRequestEnvelope:
        """Issue this verification its id and build what the adapters receive."""
        return VerificationRequestEnvelope(
            request=self._to_core_request(),
            context=VerificationContext(
                verification_id=uuid4(),
                correlation_id=correlation_id,
                agency_id=agency_id,
                application_id=self.application_id,
            ),
        )


class SourceResult(ApiSchema):
    """What one income source reported for the verification."""

    # The adapter engine builds this by field name; the camel-case aliases are for the wire.
    model_config = ConfigDict(validate_by_name=True)

    source_id: str = Field(
        min_length=1,
        description="Identifier declared by the income source adapter.",
    )
    status: SourceStatus = Field(
        description=(
            "OK: the source answered with rawIncome. NO_DATA: the source holds nothing for the "
            "subject. UNAVAILABLE: the source could not be reached, timed out, or is being "
            "given time to recover. ERROR: any other failure at the source."
        ),
    )
    retrieved_at: datetime | None = Field(
        default=None,
        description="When the source answered. Only with OK.",
    )
    raw_income: Mapping[str, object] | None = Field(
        default=None,
        description="The source's raw payload, in the shape its adapter defines. Only with OK.",
    )


class VerificationResponse(ApiSchema):
    verification_id: UUID
    sources: list[SourceResult] = Field(
        description="One result per income source consulted for this verification.",
    )


class TestConnectionResponse(ApiSchema):
    """Non-PII confirmation of the resolved caller and current environment."""

    authenticated_as: str
    environment: str


class Error(ApiSchema):
    code: ErrorCode
    message: str
