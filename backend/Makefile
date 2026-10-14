# Backend quality/test/build commands (task 1.2 / 5.2).
# Windows note: `make` may not be installed; equivalent `uv run` commands are in README/foundation.md.

.PHONY: install lint typecheck test test:integration test:e2e build

install:
	uv sync

lint:
	uv run ruff check .

typecheck:
	uv run mypy app

test:
	uv run pytest

test:integration:
	uv run pytest -m integration

test:e2e:
	npm --prefix ../frontend run test:e2e

build:
	uv build