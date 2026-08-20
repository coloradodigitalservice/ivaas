API_DIR := income-verification-api
DOCKER_API_NAME := income-verification-api
LOCAL_ENV := \
	--env-file .envs/.local/.django \
	--env-file .envs/.local/.postgres

COMPOSE := docker compose
UV := cd $(API_DIR) && uv
SYNC := $(UV) sync
# UV_RUN_FLAGS lets CI pass --no-sync (the public lane syncs with the private
# adapter wheel omitted; a plain `uv run` would try to re-sync it and fail).
UV_RUN_FLAGS ?=
RUN := $(UV) run $(UV_RUN_FLAGS)
LOCAL_RUN := $(RUN) $(LOCAL_ENV)
MANAGE := $(LOCAL_RUN) python manage.py


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
sync: ## set up .venv and dependencies
	$(SYNC)

ADAPTERS ?= ../income-verification-core
ADAPTERS_ABS := $(abspath $(ADAPTERS))
IVC_REPO ?= coloradodigitalservice/income-verification-core

WHEELS_DIR := $(API_DIR)/custom-adapters/wheels

# Downloads the CDLE wheel version pinned in pyproject.toml from the private
# IVC release (tag cdle-adapter-v<version>) into custom-adapters/wheels/ via a
# staging dir inside it (the whole wheels/ dir is gitignored — wheels are
# NEVER committed: ivaas is treated as public and a pure-python wheel is the
# adapter's source code).
define fetch_cdle_wheel
	set -eu; \
	version=$$(sed -n 's|.*wheels/cdle_adapter-\([0-9][0-9a-z.]*\)-py3-none-any\.whl.*|\1|p' $(API_DIR)/pyproject.toml | sort -u); \
	if [ -z "$$version" ]; then echo "could not read the pinned cdle-adapter version from $(API_DIR)/pyproject.toml"; exit 1; fi; \
	if [ "$$(printf '%s\n' "$$version" | wc -l | tr -d ' ')" != "1" ]; then echo "multiple distinct cdle-adapter versions referenced in $(API_DIR)/pyproject.toml"; exit 1; fi; \
	wheel="cdle_adapter-$$version-py3-none-any.whl"; \
	mkdir -p "$(WHEELS_DIR)"; \
	staging=$$(mktemp -d "$(WHEELS_DIR)/.staging.XXXXXX"); \
	trap 'rm -rf "$$staging"' EXIT HUP INT TERM; \
	if ! gh release download "cdle-adapter-v$$version" --repo "$(IVC_REPO)" --pattern "$$wheel" --dir "$$staging"; then \
		echo "release asset $$wheel not found on $(IVC_REPO) release cdle-adapter-v$$version"; exit 1; \
	fi; \
	count=$$(ls "$$staging"/*.whl 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$count" != "1" ]; then echo "expected exactly one downloaded wheel, got $$count"; exit 1; fi; \
	rm -f "$(WHEELS_DIR)"/cdle_adapter-*.whl; \
	mv "$$staging/$$wheel" "$(WHEELS_DIR)/"; \
	echo "fetched $$wheel from $(IVC_REPO)"
endef

.PHONY: adapters-fetch
adapters-fetch: ## download the pinned CDLE adapter wheel into custom-adapters/wheels/ (no lock/sync)
	@$(fetch_cdle_wheel)

.PHONY: adapters-sync
adapters-sync: adapters-fetch ## fetch the pinned CDLE wheel and verify it against the lockfile
	$(UV) lock --check
	$(SYNC) --locked

.PHONY: adapters-upgrade
adapters-upgrade: adapters-fetch ## after editing the pinned version in pyproject.toml: fetch and RELOCK (review the hash diff)
	$(UV) lock
	$(SYNC)

.PHONY: adapters-bootstrap
adapters-bootstrap: ## BOOTSTRAP ONLY (no IVC release exists yet): copy the sibling checkout's locally built wheel and relock
	@echo "WARNING: locking against a locally built wheel. Its hash will NOT match the published"
	@echo "release asset (wheel builds are not byte-identical across machines). Re-run"
	@echo "'make adapters-upgrade' once the IVC release exists, before this lock ships anywhere."
	@count=$$(ls $(ADAPTERS_ABS)/dist/cdle_adapter-*.whl 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$count" != "1" ]; then \
		echo "expected exactly one CDLE wheel in $(ADAPTERS_ABS)/dist (found $$count) — run 'make build' there"; exit 1; \
	fi; \
	wheel=$$(basename $(ADAPTERS_ABS)/dist/cdle_adapter-*.whl); \
	if ! grep -Fq "wheels/$$wheel" $(API_DIR)/pyproject.toml; then \
		echo "pyproject.toml cdle-adapter source does not reference wheels/$$wheel — update the path first"; exit 1; \
	fi; \
	mkdir -p $(WHEELS_DIR); \
	rm -f $(WHEELS_DIR)/cdle_adapter-*.whl; \
	cp $(ADAPTERS_ABS)/dist/cdle_adapter-*.whl $(WHEELS_DIR)/
	$(UV) lock
	$(SYNC)

.PHONY: dev-adapter
dev-adapter: ## live-develop the CDLE adapter against the app (use 'uv run --no-sync' while active; cleanup: make sync)
	$(UV) pip install --python .venv/bin/python --no-deps -e $(ADAPTERS_ABS)/adapters/cdle
	@echo "Local CDLE adapter active. Plain 'uv run' (incl. make test/quality-check) will silently restore the locked wheel — use 'uv run --no-sync' until done, then 'make sync' to restore."

.PHONY: sync-ci
sync-ci: ## set up .venv and dependencies for CI, requiring pyproject.toml and uv.lock to be consistent
	$(SYNC) --locked

.PHONY: sync-ci-public
sync-ci-public: ## CI sync for contexts without the private adapter wheel (fork PRs, public lane)
	$(SYNC) --frozen --no-install-package cdle-adapter

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
