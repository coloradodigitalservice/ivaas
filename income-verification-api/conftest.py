"""Shared test fixtures for all test suites in this project."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from ivaas_core import LookbackPeriod, VerificationRequest


@pytest.fixture
def last_calendar_month() -> LookbackPeriod:
    """The most recently completed calendar month, first day through last day."""
    first_of_current_month = date.today().replace(day=1)
    last_day_of_previous_month = first_of_current_month - timedelta(days=1)
    first_day_of_previous_month = last_day_of_previous_month.replace(day=1)
    return LookbackPeriod(
        start_date=first_day_of_previous_month,
        end_date=last_day_of_previous_month,
    )


@pytest.fixture
def verification_request(last_calendar_month: LookbackPeriod) -> VerificationRequest:
    """A standard, valid request for exercising any adapter."""
    return VerificationRequest(
        verification_id=uuid4(),
        agency_id="TEST_PROGRAM",
        application_id="APP-2026-004471",
        first_name="John",
        last_name="Doe",
        lookback_period=last_calendar_month,
        last4_ssn="1234",
    )
