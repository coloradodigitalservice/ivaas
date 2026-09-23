"""Exception types raised by income datasource adapters.

Adapters catch vendor errors (HTTP client errors, datasource API errors) and
re-raise these. Application code only ever catches these contract types.

Each class declares the API's per-source `status` it maps to (see
docs/api/open-api-spec.yaml, `SourceResult.status`). The application reports
that status; an adapter that records outcomes at its datasource writes the same one.
"""

from typing import ClassVar

from ivaas_core.models import SourceStatus


class IncomeSourceError(Exception):
    """Base for all errors raised by an income datasource adapter."""

    status: ClassVar[SourceStatus] = SourceStatus.ERROR


class SourceTimeout(IncomeSourceError):
    """The datasource did not answer within the adapter's configured timeout bound."""

    status = SourceStatus.UNAVAILABLE


class SourceUnavailable(IncomeSourceError):
    """The datasource could not be reached or refused to serve the request."""

    status = SourceStatus.UNAVAILABLE


class SourceResponseInvalid(IncomeSourceError):
    """The datasource answered, but its response could not be parsed.

    Raise instead of letting vendor parsing errors escape, so the message
    can be sanitized at the point where the raw payload is still in hand.
    """


class SubjectNotFound(IncomeSourceError):
    """The datasource answered, but no data was found based on the request parameters."""

    status = SourceStatus.NO_DATA
