API_DIR := income-verification-api
COMPOSE := docker compose
UV := cd $(API_DIR) && uv
SYNC := $(UV) sync
RUN := $(UV) run

.DEFAULT_GOAL := help

.PHONY: help
help: ## print the help documentation
	@grep -E '^[/a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: sync install-hooks ## set up the local development environment

.PHONY: install-hooks
install-hooks: ## install pre-commit hooks
	$(RUN) pre-commit install --install-hooks

.PHONY: sync
sync: ## set up .venv and dependencies
	$(SYNC)

.PHONY: sync-ci
sync-ci: ## set up .venv and dependencies for CI, requiring pyproject.toml and uv.lock to be consistent
	$(SYNC) --locked

.PHONY: db-up
db-up: ## start PostgreSQL
	$(COMPOSE) up --wait postgres

.PHONY: db-down
db-down: ## stop local services
	$(COMPOSE) down

.PHONY: db-reset
db-reset: ## recreate the local PostgreSQL database
	$(COMPOSE) down --volumes
	$(COMPOSE) up --wait postgres

.PHONY: run
run: db-up ## run the Django development server
	$(RUN) python manage.py runserver

.PHONY: migrate
migrate: db-up ## apply database migrations
	 $(RUN) python manage.py migrate

.PHONY: migrations
migrations: ## generate database migrations
	$(RUN) python manage.py makemigrations

.PHONY: test
test: db-up ## run tests
	$(RUN) pytest

.PHONY: quality-fix
quality-fix: ## Apply available automatic fixes for python package quality violations
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

.PHONY: quality-check
quality-check: ## run all required checks
	$(RUN) ruff format --check .
	$(RUN) ruff check .
	$(RUN) python manage.py check
	$(RUN) mypy .
	$(MAKE) test
