"""Exception types raised by income datasource adapters.

Adapters catch vendor errors (HTTP client errors, datasource API errors) and
re-raise these. Application code only ever catches these contract types.

The application maps exceptions to the API's per-source ``status`` values
(see docs/api/open-api-spec.yaml, ``SourceResult.status``):

- ``SubjectNotFound``        -> ``NO_DATA``
- ``SourceTimeout``          -> ``UNAVAILABLE``
- ``SourceUnavailable``      -> ``UNAVAILABLE``
- ``SourceResponseInvalid``  -> ``ERROR``
- any other exception        -> ``ERROR`` (and is a bug: adapters raise only these types)

Messages must never contain claimant PII or raw vendor error text: adapter
implementations sanitize vendor payloads before raising, because datasource
error messages can echo query values.
"""


class IncomeSourceError(Exception):
    """Base for all errors raised by an income datasource adapter."""


class SourceTimeout(IncomeSourceError):
    """The datasource did not answer within the adapter's configured timeout bound."""


class SourceUnavailable(IncomeSourceError):
    """The datasource could not be reached or refused to serve the request."""


class SourceResponseInvalid(IncomeSourceError):
    """The datasource answered, but its response was malformed or semantically invalid.

    Raised instead of letting vendor parsing errors escape, so the message
    can be sanitized at the point where the raw payload is still in hand.
    """


class SubjectNotFound(IncomeSourceError):
    """The datasource answered, but holds no records for the requested subject."""
