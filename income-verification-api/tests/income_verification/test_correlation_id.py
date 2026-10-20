import pytest

from income_verification.correlation_id import (
    CORRELATION_ID_MAX_LENGTH,
    validated_correlation_id,
)


@pytest.mark.parametrize(
    "correlation_id",
    [
        "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31",
        "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31:program/reference-1",
    ],
)
def test_accepts_valid_correlation_ids(correlation_id: str) -> None:
    assert validated_correlation_id(correlation_id) == correlation_id


@pytest.mark.parametrize(
    "correlation_id",
    [
        None,
        "",
        "SENTINEL-MALFORMED-CORRELATION",
        "8c3d1e90-5a27-1b6f-9e14-2f7b0c9a5d31",
        "8c3d1e90-5a27-4b6f-9e14-2f7b0c9a5d31:contains spaces",
        "x" * (CORRELATION_ID_MAX_LENGTH + 1),
    ],
)
def test_discards_missing_or_malformed_correlation_ids(correlation_id: str | None) -> None:
    assert validated_correlation_id(correlation_id) is None
