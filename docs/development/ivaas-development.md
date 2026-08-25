# Developing

## Prerequisites

Before starting, ensure the following are installed:

- A compatible tool version manager, such as [mise](https://mise.jdx.dev/) or [asdf](https://asdf-vm.com/)
- [Docker](https://www.docker.com/get-started/) with Docker Compose
- Make

## Setup

This project uses the tools pinned in [`.tool-versions`](./.tool-versions) for compatibility with version managers such as [asdf](https://asdf-vm.com/) and [mise](https://mise.jdx.dev/).

If using a different version manager, or installing tools manually, ensure the installed versions match those pinned in `.tool-versions`. The Python version used by the API is additionally pinned in [`income-verification-api/.python-version`](./income-verification-api/.python-version).

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

Use the setup command to install project dependencies:

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

- API: http://127.0.0.1:8000/api/
- OpenAPI documentation: http://127.0.0.1:8000/api/docs

> [!NOTE]
> `make run` starts PostgreSQL automatically if it is not already running.

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

* [Adapter Development](../configuration/ivaas-configuration.md#adapter-development)
