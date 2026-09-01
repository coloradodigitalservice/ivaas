"""Exception types raised by income datasource adapters.

Adapters catch vendor errors (HTTP client errors, datasource API errors) and
re-raise these. Application code only ever catches these contract types.

The application maps exceptions to the API's per-source `status` values
(see docs/api/open-api-spec.yaml, `SourceResult.status`):
"""


class IncomeSourceError(Exception):
    """Base for all errors raised by an income datasource adapter."""


class SourceTimeout(IncomeSourceError):
    """The datasource did not answer within the adapter's configured timeout bound."""


class SourceUnavailable(IncomeSourceError):
    """The datasource could not be reached or refused to serve the request."""


class SourceResponseInvalid(IncomeSourceError):
    """The datasource answered, but its response could not be parsed.

    Raise instead of letting vendor parsing errors escape, so the message
    can be sanitized at the point where the raw payload is still in hand.
    """


class SubjectNotFound(IncomeSourceError):
    """The datasource answered, but no data was found based on the request parameters."""
