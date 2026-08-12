# Income Verification As A Service (IVAAS) Application

The application for IVAAS.

## Setup

This project uses the tools pinned in [`.tool-versions`](./.tool-versions) for compatibility with version managers such as [asdf](https://asdf-vm.com/) and [mise](https://mise.jdx.dev/).

If using a different version manager, or installing tools manually, ensure the installed versions match those pinned in `.tool-versions`. The Python version used by the API is additionally pinned in [`income-verification-api/.python-version`](./income-verification-api/.python-version).

### Prerequisites

Before starting, ensure the following are installed:

- A compatible tool version manager, such as `mise` or `asdf`
- Docker with Docker Compose
- Make

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

Use the setup command to install any python dependencies:

```shell
   make setup
```

### Initialize the database

Start the local PostgreSQL container and apply the Django migrations:

```bash
    make migrate
```

The PostgreSQL data is stored in a Docker volume and persists when the container is stopped.

To completely recreate the local database:

```bash
    make db-reset
    make migrate
```

> WARNING: `make db-reset` permanently deletes the existing local PostgreSQL data.

### Run the application

Start the local Django development server:

```bash
    make run
```

The application will be available at:

- API: http://127.0.0.1:8000/api/
- OpenAPI documentation: http://127.0.0.1:8000/api/docs
- Django admin: http://127.0.0.1:8000/admin/

> NOTE: `make run` starts PostgreSQL automatically if it is not already running.

### Run project checks

Run the complete local quality suite:

```bash
    make quality-check
```

This runs:

- Django system checks
- Ruff formatting checks
- Ruff linting
- mypy type checking
- pytest tests

To automatically format code and apply safe lint fixes:

```bash
    make quality-fix
```

For a complete list of available `make` commands, run:

```shell
    make help
```
