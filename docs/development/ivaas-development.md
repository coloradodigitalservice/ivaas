# Developing

## Prerequisites

Before starting, ensure the following are installed:

- A compatible tool version manager, such as [mise](https://mise.jdx.dev/) or [asdf](https://asdf-vm.com/)
- [Docker](https://www.docker.com/get-started/) with Docker Compose
- Make

## Setup

This project uses the tools pinned in [`.tool-versions`](../../.tool-versions) for compatibility with version managers such as [asdf](https://asdf-vm.com/) and [mise](https://mise.jdx.dev/).

If using a different version manager, or installing tools manually, ensure the installed versions match those pinned in `.tool-versions`. The Python version used by the API is additionally pinned in [`income-verification-api/.python-version`](../../income-verification-api/.python-version).

### Install development tooling

```shell
# install tooling with asdf
asdf install
```

or

```shell
# install tooling with mise
mise install
```

### Set up project for local development

1. If the IVaaS implementation is already configured to use adapters (see [Adapters](../configuration/ivaas-configuration.md#adapters) documentation),
   you will need to first download/build each configured adapter according to its own documentation (See [Adapter installation](../configuration/ivaas-configuration.md#adapter-installation))

2. Use the setup command to install project dependencies:
   ```shell
   make setup
   ```

### Initialize the database

Start the local PostgreSQL container and apply the Django migrations:

```shell
make migrate
```

The PostgreSQL data is stored in a Docker volume and persists when the container is stopped.

To completely recreate the local database:

```shell
make db-reset
make migrate
```

> [!WARNING]
> `make db-reset` permanently deletes the existing local PostgreSQL data.

## Run the application

Start the local development server:

```shell
make run
```

Or run the application entirely in Docker:

```shell
make up
```

The application will be available at:

- Health check: http://127.0.0.1:8000/api/health
- Income verification: http://127.0.0.1:8000/api/v1/income-verification
- Test connection: http://127.0.0.1:8000/api/v1/test-connection
- OpenAPI documentation: http://127.0.0.1:8000/api/docs
- OpenAPI document: http://127.0.0.1:8000/api/openapi.json

For interactive development and contract testing, import the
[IVaaS Postman collection](../../postman/IVaaS.postman_collection.json).

The local environment uses a containerized OAuth/JWKS server. The Postman collection exchanges its
committed local-only client credentials for a signed access token before protected requests, and
IVaaS verifies that token through the same authentication path used in deployed environments.
This requires no AWS credentials or external identity-provider access.

> [!NOTE]
> `make run` starts PostgreSQL and the local OAuth/JWKS server automatically if needed.

## Run project checks

Run the complete local quality suite:

```shell
make quality-check
```

This runs:

- Django system checks
- Formatting checks
- Linting checks
- Type checks

To automatically format code and apply safe lint fixes:

```shell
make quality-fix
```

To run the automated test suite, use the `make test` command:

```shell
make test
```

For a complete list of available `make` commands, run:

```shell
make help
```

## Custom development

- [Adapter Development](../configuration/ivaas-configuration.md#adapter-development)
