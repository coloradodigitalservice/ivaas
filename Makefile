API_DIR := income-verification-api
DOCKER_API_NAME := income-verification-api
DOCKER_BASE_STAGE_TAG := ivaas-$(DOCKER_API_NAME):base
SMOKE_IMAGE ?= ivaas-smoke:local
ADAPTERS_ENV ?= .envs/.local/.adapters# CI overrides this with .envs/.ci/.adapters
ENV := \
	--env-file .envs/.local/.django \
	--env-file .envs/.local/.postgres \
	--env-file $(ADAPTERS_ENV) \
	$(if $(wildcard $(API_DIR)/.envs/.local/.secrets),--env-file .envs/.local/.secrets)

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

.PHONY: local-services-up
local-services-up: ## start local PostgreSQL and OAuth/JWKS services
	$(COMPOSE) up --detach --wait postgres mock-oauth2-server

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
run: local-services-up ## run the local development server
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

.PHONY: test-smoke
test-smoke: ## run HTTP smoke tests against SMOKE_BASE_URL (application must already be running)
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --project $(API_DIR) --no-sync python -m pytest -c smoke_tests/pytest.ini smoke_tests/test_api.py $(SMOKE_TEST_ARGS)

.PHONY: smoke-image
smoke-image: ## build the standalone smoke-test image (override SMOKE_IMAGE to set its tag)
	docker build --file smoke_tests/Dockerfile --tag $(SMOKE_IMAGE) .

.PHONY: test-smoke-local
test-smoke-local: ## run smoke tests against the running local application and mock OAuth server
	SMOKE_BASE_URL=http://127.0.0.1:8000 \
	SMOKE_TOKEN_URL=http://127.0.0.1:8090/default/token \
	SMOKE_CLIENT_ID=local-client \
	SMOKE_CLIENT_SECRET=local-secret \
	SMOKE_EXPECTED_AGENCY=local-agency \
	SMOKE_EXPECTED_ENVIRONMENT=local \
	$(MAKE) --no-print-directory test-smoke

.PHONY: quality-fix
quality-fix: ## Apply available automatic fixes for python package quality violations
	$(RUN_NO_SYNC) ruff format . ../smoke_tests
	$(RUN_NO_SYNC) ruff check --fix . ../smoke_tests

.PHONY: quality-check
quality-check: ## run all required checks
	$(RUN_NO_SYNC) ruff format --check . ../smoke_tests
	$(RUN_NO_SYNC) ruff check . ../smoke_tests
	$(MANAGE) check
	$(LOCAL_RUN) mypy . ../smoke_tests

.PHONY: django-secret-key
django-secret-key: ## generate string for DJANGO_SECRET_KEY
	$(UV) run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

.PHONY: docker-base-image-update-check
docker-base-image-update-check: ## check for available updates in base docker image
	docker image build --no-cache --target base --tag $(DOCKER_BASE_STAGE_TAG) $(API_DIR)
	docker container run --rm -it $(DOCKER_BASE_STAGE_TAG) sh -c "apt-get update -qq && apt list --upgradable"
