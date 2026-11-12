import pytest
from ivaas_core import SourceStatus
from pydantic import ValidationError

from income_verification.schemas import SourceResult


def test_source_result_requires_nullable_fields() -> None:
    with pytest.raises(ValidationError) as error:
        SourceResult.model_validate({"sourceId": "test-source", "status": SourceStatus.NO_DATA})

    assert {detail["loc"] for detail in error.value.errors()} == {
        ("retrievedAt",),
        ("rawIncome",),
    }
