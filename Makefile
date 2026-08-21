API_DIR := income-verification-api
DOCKER_API_NAME := income-verification-api
LOCAL_ENV := \
	--env-file .envs/.local/.django \
	--env-file .envs/.local/.postgres \
	--env-file .envs/.local/.adapters

COMPOSE := docker compose
UV := cd $(API_DIR) && uv
SYNC := $(UV) sync
# --no-sync: side-loaded adapter wheels are not in the lockfile, and a plain
# `uv run` syncs first and would uninstall them. `make sync`/`make sync-ci`
# are the explicit synchronization points.
RUN := $(UV) run --no-sync
LOCAL_RUN := $(RUN) $(LOCAL_ENV)
MANAGE := $(LOCAL_RUN) python manage.py

# ============================================================================
# Custom adapters.
#
# Adapter wheels are placed in $(WHEELS_DIR) by whoever builds (a developer,
# or the CI repo that owns fetching). Everything here runs off wheels being
# in that directory, and everything tolerates it being empty — zero adapters
# is a valid (generic) configuration.
# ============================================================================
ADAPTERS_CHECKOUT ?= ../income-verification-core
ADAPTERS_WHEELS_DIRECTORY := $(API_DIR)/custom-adapters/wheels

.DEFAULT_GOAL := help

.PHONY: help
help: ## print the help documentation
	@grep -E '^[/a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: sync install-hooks ## set up the local development environment

.PHONY: install-hooks
install-hooks: ## install pre-commit hooks
	$(RUN) pre-commit install --install-hooks

.PHONY: pre-commit
pre-commit: ## run pre-commit hooks on all files
	$(RUN) pre-commit run --all-files

.PHONY: sync
sync: ## set up .venv and dependencies, including any adapter wheels
	$(SYNC)
	@$(MAKE) --no-print-directory adapters-install

.PHONY: sync-ci
sync-ci: ## set up .venv and dependencies for CI, requiring pyproject.toml and uv.lock to be consistent
	$(SYNC) --locked
	@$(MAKE) --no-print-directory adapters-install

.PHONY: adapters-install
adapters-install: ## install landing-zone adapter wheels into the venv (no-op when empty)
	@if ls $(ADAPTERS_WHEELS_DIRECTORY)/*.whl >/dev/null 2>&1; then \
		( $(UV) pip install --python .venv/bin/python --no-deps custom-adapters/wheels/*.whl ); \
	fi

.PHONY: dev-adapter
dev-adapter: ## live-develop adapters from the sibling checkout (cleanup: make sync)
	@set -e; for d in $(abspath $(ADAPTERS_CHECKOUT))/adapters/*/; do \
		[ -d "$$d" ] || continue; \
		( $(UV) pip install --python .venv/bin/python --no-deps -e "$$d" ); \
	done

.PHONY: db-up
db-up: ## start the local docker PostgreSQL database
	$(COMPOSE) up --wait postgres

.PHONY: db-reset
db-reset: ## recreate the local docker PostgreSQL database
	$(COMPOSE) down --volumes
	$(COMPOSE) up --wait postgres

.PHONY: up
up: ## start the local containerized application
	$(COMPOSE) up --build --detach --wait

.PHONY: down
down: ## stop the local containerized application
	$(COMPOSE) down

.PHONY: docker-migrate
docker-migrate: up ## apply migrations in the running api container
	$(COMPOSE) exec $(COMPOSE_API_NAME) python manage.py migrate

.PHONY: run
run: db-up ## run the local development server
	$(LOCAL_RUN) uvicorn config.asgi:application \
		--reload \
		--host 127.0.0.1 \
		--port 8000

.PHONY: migrate
migrate: db-up ## apply database migrations
	$(MANAGE) migrate

.PHONY: migrations
migrations: ## generate database migrations
	$(MANAGE) makemigrations

.PHONY: test
test: db-up ## run tests
	$(LOCAL_RUN) pytest

.PHONY: quality-fix
quality-fix: ## Apply available automatic fixes for python package quality violations
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

.PHONY: quality-check
quality-check: ## run all required checks
	$(RUN) ruff format --check .
	$(RUN) ruff check .
	$(MANAGE) check
	$(LOCAL_RUN) mypy .
