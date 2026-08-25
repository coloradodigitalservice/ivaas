# Income Verification as a Service (IVaaS) Application

The application for IVaaS, a platform for standing up a customizable income verification service.

## Structure

The (work-in-progress) intended structure of the ivaas platform based on its responsibilities and design requirements is as follows:

> [!NOTE]
> Areas of uncertainty marked with `?`

```mermaid
mindmap
  root((IVaaS Platform))
    packages
      ivaas-core
        develop custom adapters
        develop shared adapters
        helpful utilities?
      ivaas-adapters?
        shared, public adapters
    Adapters
      Custom adapters
        Live in external repositories, public or privae
      Shared adapters
        Live in packages/adapters/*?
    Configuration
      Specify adapters and adapter configurations in settings.py
      Customize environment with .env files
        Bootstrap on deployment with AppConfig?
    Build & Deployment
        Generic platform checks
            GitHub actions
        State-specific quality gates
        IAC
          Public templates
          State-specific implementations
```

## Development

For local development, see [ivaas-development](docs/development/ivaas-development.md) documentation.

## Configuration

For documentation related to configuring ivaas, see [ivaas-configuration](docs/configuration/ivaas-configuration.md).
