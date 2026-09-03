API_DIR := income-verification-api
DOCKER_API_NAME := income-verification-api
ADAPTERS_ENV ?= .envs/.local/.adapters# CI overrides this with .envs/.ci/.adapters
ENV := \
	--env-file .envs/.local/.django \
	--env-file .envs/.local/.postgres \
	--env-file $(ADAPTERS_ENV)

COMPOSE := docker compose
UV := cd $(API_DIR) && uv
SYNC := $(UV) sync
# --no-sync: adapter wheels are not in the lockfile. A plain `uv run` syncs first and would uninstall them.
# `make sync`/`make sync-ci` are the explicit synchronization points.
RUN_NO_SYNC := $(UV) run --no-sync
LOCAL_RUN := $(RUN_NO_SYNC) $(ENV)
MANAGE := $(LOCAL_RUN) python manage.py

# ============================================================================
# Custom adapters.
#
# For live adapter-app development, adapters must be checked out to the following directory
ADAPTERS_CHECKOUT ?= ../iv-colorado-adapters
ADAPTER_MODULES := $(abspath $(ADAPTERS_CHECKOUT))/adapters/*/
# Otherwise, adapters are installed via `make adapters-install`
# ============================================================================

.DEFAULT_GOAL := help

.PHONY: help
help: ## print the help documentation
	@grep -E '^[/a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: sync install-hooks ## set up the local development environment

.PHONY: install-hooks
install-hooks: ## install pre-commit hooks
	$(RUN_NO_SYNC) pre-commit install --install-hooks

.PHONY: pre-commit
pre-commit: ## run pre-commit hooks on all files
	$(RUN_NO_SYNC) pre-commit run --all-files

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
	@cd $(API_DIR) && custom-adapters/install.sh

.PHONY: dev-adapters
dev-adapters: ## live-develop adapters from the sibling checkout (cleanup: make sync)
	@set -e; for d in $(ADAPTER_MODULES); do \
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
	$(COMPOSE) exec $(DOCKER_API_NAME) python manage.py migrate

.PHONY: run
run: db-up ## run the local development server
	$(LOCAL_RUN) uvicorn config.asgi:application \
		--reload \
		--host 127.0.0.1 \
		--port 8000

.PHONY: shell
shell: db-up ## Django shell with local env files
	$(MANAGE) shell

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
	$(RUN_NO_SYNC) ruff format .
	$(RUN_NO_SYNC) ruff check --fix .

.PHONY: quality-check
quality-check: ## run all required checks
	$(RUN_NO_SYNC) ruff format --check .
	$(RUN_NO_SYNC) ruff check .
	$(MANAGE) check
	$(LOCAL_RUN) mypy .
