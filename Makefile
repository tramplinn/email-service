DEPLOY_COMPOSE = docker compose --env-file .env.runtime

.PHONY: install run healthcheck lint format typecheck test check lock \
	staging-config staging-up staging-down

install:
	uv sync

run:
	uv run python -m email_service

healthcheck:
	uv run python -m email_service healthcheck

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy src tests

test:
	uv run pytest

check: lint typecheck test

lock:
	uv lock

staging-config:
	$(DEPLOY_COMPOSE) config --quiet

staging-up:
	$(DEPLOY_COMPOSE) up -d --build --wait

staging-down:
	$(DEPLOY_COMPOSE) down
