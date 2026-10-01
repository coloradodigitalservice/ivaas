# Configuring IVaaS

## API

`API_VERSION` controls the program-facing API's URL prefix and the version advertised by its
generated OpenAPI document. It defaults to `v1`, which exposes API endpoints under `/api/v1`.

### Authentication

Program-facing routes use OAuth2 machine authentication by default; `/api/health` is public.
Every environment uses the same signed-access-token verification path. Configure:

- `AUTH_ISSUER`: exact issuer required in access tokens.
- `AUTH_JWKS_URL`: endpoint from which IVaaS retrieves the issuer's public signing keys.
- `AUTH_TOKEN_URL`: client-credentials token endpoint advertised in generated OpenAPI.
- `AUTH_REQUIRED_SCOPE`: scope required by program-facing operations; defaults to
  `ivaas/income.verify`.
- `AUTH_CLIENT_AGENCY_MAP`: JSON object mapping verified OAuth client IDs to IVaaS agency IDs.
- `AUTH_JWKS_CACHE_SECONDS`: local JWKS document cache lifetime; defaults to 300 seconds.
- `AUTH_JWKS_TIMEOUT_SECONDS`: JWKS request timeout; defaults to five seconds.
- `DEPLOYMENT_ENVIRONMENT`: environment name returned by `/api/v1/test-connection`.

IVaaS accepts only RS256 access tokens with the configured issuer, a future expiration, an
`access` token use, the required scope, and a client ID present in `AUTH_CLIENT_AGENCY_MAP`.
It validates tokens using public signing keys and never needs consuming agencies' client secrets.
Both JWKS duration settings must be greater than zero, and the client-to-agency map must contain at
least one entry. Invalid authentication configuration fails application startup rather than
falling back to unauthenticated behavior.

The client-to-agency map is deployment-time onboarding configuration. Adding or changing an entry
requires deploying or restarting IVaaS; there is currently no runtime onboarding API or durable
onboarding store.

For local development, `make run` and `make up` start a containerized OAuth/JWKS server. The committed
local settings point IVaaS and the Postman collection at that server, so local requests exercise
the same signed-token verification path without AWS credentials or an external identity provider.

## Adapters

To fetch data from specific/proprietary income sources, IVaaS uses "adapters".
Adapters are responsible for fetching and transforming data from various income data sources into a format that IVaaS can process and return to clients.

Adapters encapsulate logic and implementation details relating to the data sources they interact with, so that the IVaaS application needs only to be concerned with invoking the relevant adapter(s) based on incoming client requests.

### Adapter development

#### Source code location and visibility

Adapter development can take place wherever source-code constraints allow.

If an adapters can be used by multiple jurisdictions (i.e. commercial or federal data sources), it can be housed in this repository or in a separate public repository. [TODO: Exact details of standards & processes pending Equifax adapter as an example]

The source code for jurisdiction-specific adapters (e.g. a state unemployment insurance database) can be hosted publicly or privately.

Privately hosted adapter code _will_ complicate build pipelines and development processes due to the inherent access restrictions. This approach is suitable for adapters with private source code, even if an IVaaS installation/implementation is public, since the adapter wheels are .gitignored.

#### Best practices

Adapter development requires only that the resulting adapter implement the contracts defined by the [ivaas-core package](../../income-verification-api/packages/ivaas-core):

- Adapters should be implementations of the [IncomeSourceAdapter](../../income-verification-api/packages/ivaas-core/src/ivaas_core/adapter.py) abstract base class.
- Proper error handling by IVaaS requires exceptions raised by adapters to be implementations of [IncomeSourceError](../../income-verification-api/packages/ivaas-core/src/ivaas_core/exceptions.py).

The adapter must be built into a wheel and dropped into the designated "landing-zone". See [adapter installation](#adapter-installation)

It is recommended (but optional) for local development, to configure `ADAPTERS_CHECKOUT` in the [Makefile](../../Makefile) to take advantage of `make dev-adapters` fast feedback loops.

### Adapter installation

Adapter code that is ready to be registered, tested, and deployed can be installed as follows:

1. Configure the adapter under the `INCOME_SOURCE_ADAPTERS` key in [settings.py](../../income-verification-api/config/settings.py). See [Adapter Configuration](#adapter-configuration) below for details.
2. Ensure the adapter's built wheel is dropped into the "landing-zone", [custom-adapters/wheels](../../income-verification-api/custom-adapters/wheels)
3. `make adapters-install` will install the adapter into the IVaaS virtual environment. The default docker build performs this step automatically.

On application startup, IVaaS will validate and register adapters.

> [!TIP]
> IVaaS prints confirmation of the registered, active adapters in the application logs on startup.

### Adapter configuration

Every adapter is declared as one entry under `INCOME_SOURCE_ADAPTERS` in [settings.py](../../income-verification-api/config/settings.py).
The entry's key is the adapter's name in logs and error messages.
Values that vary by environment should come from environment variables, following the pattern `<ADAPTER>_<SETTING>`, with a sensible default in settings.

```python
INCOME_SOURCE_ADAPTERS = {
    "example": {
        "class": "example_adapter.ExampleAdapter",
        "enabled": env.bool("EXAMPLE_ADAPTER_ENABLED", default=False),
        "config": {
            "timeout_seconds": env.int("EXAMPLE_TIMEOUT_SECONDS", default=5),
        },
        "retry_policy": {
            "max_attempts": env.int("EXAMPLE_RETRY_POLICY_MAX_ATTEMPTS", default=3),
            "backoff": {
                "strategy": "exponential",
                "initial_seconds": env.float("EXAMPLE_RETRY_POLICY_BACKOFF_INITIAL_SECONDS", default=0.5),
                "max_seconds": env.float("EXAMPLE_RETRY_POLICY_BACKOFF_MAX_SECONDS", default=5),
            },
        },
        "circuit_breaker": {
            "failure_threshold": env.int("EXAMPLE_CIRCUIT_BREAKER_FAILURE_THRESHOLD", default=5),
            "reset_timeout_seconds": env.float("EXAMPLE_CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS", default=30),
        },
    },
}
```

**All keys are required**.
IVaaS validates every entry at startup and refuses to start on a missing key or an invalid value, so a misconfigured adapter is caught before it can serve a request.

#### `class`

The import path of the adapter class. The class must implement `IncomeSourceAdapter` from ivaas-core and must be importable from an installed wheel.

#### `enabled`

Whether IVaaS registers the adapter at startup. Disabled adapters are skipped but still validated.

#### `config`

Keyword arguments passed to the adapter's constructor. IVaaS treats these as opaque; the adapter decides what it needs.
A value of `None` means the environment variable was not set, and IVaaS reports it as missing configuration when the adapter is enabled.

#### `retry_policy`

How IVaaS retries a call to the adapter that fails because the data source timed out or could not be reached.

Set to `None` to disable retries for the adapter. Otherwise provide:

| Key            | Purpose                                                                               |
| -------------- | ------------------------------------------------------------------------------------- |
| `max_attempts` | Total maximum allowable call attempts for a single request, counting the first.       |
| `backoff`      | The pause between attempts. Following either a fixed or exponential backoff strategy. |

Backoff shapes:

| `strategy`    | Keys                             | Behavior                                                                                                |
| ------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `fixed`       | `seconds`                        | The same pause before every retry.                                                                      |
| `exponential` | `initial_seconds`, `max_seconds` | The pause doubles after each retry, plus a small random amount (jitter), never exceeding `max_seconds`. |

#### `circuit_breaker`

Protects IVaaS and the data source when the source is down. Each retry attempt that times out or cannot reach the source counts as a failure; a success resets the count. After `failure_threshold` consecutive failures the breaker opens, and every call to that adapter fails immediately, without contacting the source, until `reset_timeout_seconds` have passed. The next call is then allowed through as a trial: success closes the breaker, failure opens it for another reset period.

Set to `None` to disable the breaker for the adapter. Otherwise provide:

| Key                     | Purpose                                                                                                                                                                            |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `failure_threshold`     | Number of _consecutive_ failures that open the breaker. It is recommended to keep it above `max_attempts` so that one request's own retries cannot open the circuit breaker alone. |
| `reset_timeout_seconds` | How long the breaker stays open before allowing a trial call.                                                                                                                      |

Every failed attempt and every breaker trip is logged with the adapter's name and the underlying cause.

> [!NOTE]
> The worst-case time a single request can spend on one adapter is roughly `max_attempts` times the adapter's timeout, plus the backoffs in between. Size `max_attempts` and the adapter's timeout together with that ceiling in mind.
