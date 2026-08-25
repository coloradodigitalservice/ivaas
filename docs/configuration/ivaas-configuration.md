# Configuring IVaaS

## Adapters

To fetch data from specific/proprietary income sources, IVaaS uses "adapters".
Adapters are responsible for fetching and transforming data from various income data sources into a standardized format that IVaaS can process and return to clients.

Adapters encapsulate logic and implementation details

### Adapter development

#### Source code location and visibility

Adapter development can take place wherever source-code constraints allow.

Adapters that may be beneficial to other IVaaS installations should be published publicly. [TODO: Exact details of where/how pending Equifax adapter as an example]

The source code for adapters where state-specific datasource implementation details are sensitive can be hosted privately.
Privately hosted adapter code _will_ complicate build pipelines and development processes due to the inherent access restrictions.
This approach is suitable for adapters with private source code, even if an IVaaS installation/implementaton is public, since the adapter wheels are .gitignored.

#### Best practices

Adapter development requires only that the resulting adapter implement the contracts defined by the [ivaas-core package](../../income-verification-api/packages/ivaas-core):
* Adapters should be implementations of the [IncomeSourceAdapter](../../income-verification-api/packages/ivaas-core/src/ivaas_core/adapter.py) abstract base class.
* Proper error handling by IVaaS requires exceptions raised by adapters to be implementations of [IncomeSourceError](../../income-verification-api/packages/ivaas-core/src/ivaas_core/exceptions.py).

The adapter must be built into a wheel and dropped into the designated "landing-zone". See [adapter installation](#adapter-installation)

It is recommened (but optional) for local development, to configure `ADAPTERS_CHECKOUT` in the [Makefile](../../Makefile) to take advantage of `make dev-adapters` fast feedback loops.

### Adapter installation

Adapter code that is ready to be registered, tested, and deployed can be installed as follows:

1. Configure the adapter under the `INCOME_SOURCE_ADAPTERS` key in [settings.py](../../income-verification-api/config/settings.py)
2. Ensure the adapter's built wheel is dropped into the "landing-zone", [custom-adapters/wheels](../../income-verification-api/custom-adapters/wheels)
3. `make adapters-install` will install the adapter into the IVaaS virtual environment. The default docker build performs this step automatically.

On application startup, IVaaS will validate and register adapters.

> [!TIP]
> IVaaS prints confirmation of the registered, active adapters in the application logs on startup.
