"""Schemas for the program-facing IVaaS API."""

from datetime import datetime
from typing import Literal, Self
from income_verification.api_error_codes import ErrorCode, ERRORS
from uuid import UUID

from ivaas_core import (
    LAST4_SSN_PATTERN,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    NAME_PATTERN,
    SSN_PATTERN,
)
from ivaas_core import LookbackPeriod as CoreLookbackPeriod
from ivaas_core import VerificationRequest as CoreVerificationRequest
from ninja import Field, Schema
from pydantic import ConfigDict, model_validator
from pydantic.alias_generators import to_camel
from pydantic_core import PydanticCustomError

from income_verification.dtos import VerificationRequestEnvelope


class ApiSchema(Schema):
    """Expose Python field names as the camel-case names in the API contract."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


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

        self._to_core_request()
        return self

    def _to_core_request(self) -> CoreVerificationRequest:
        return CoreVerificationRequest(
            first_name=self.first_name,
            last_name=self.last_name,
            ssn=self.ssn,
            last4_ssn=self.last4_ssn,
            lookback_period=self.lookback_period,
        )

    def to_envelope(self, correlation_id: str) -> VerificationRequestEnvelope:
        return VerificationRequestEnvelope(
            application_id=self.application_id,
            correlation_id=correlation_id,
            core_request=self._to_core_request(),
        )


class SourceResult(ApiSchema):
    source_id: str = Field(
        min_length=1,
        description="Identifier declared by the income source adapter.",
    )
    status: Literal["OK", "NO_DATA", "UNAVAILABLE", "ERROR"]
    retrieved_at: datetime
    raw_income: dict[str, object] | None = None


class VerificationResponse(ApiSchema):
    verification_id: UUID
    sources: list[SourceResult] = Field(default_factory=list)


class Error(ApiSchema):
    code: ErrorCode
    message: str
