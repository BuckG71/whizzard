# Dev workflow shortcuts. All targets are thin wrappers — pyproject.toml
# holds the canonical tool config, this just makes invocation ergonomic.
#
# PYTHON resolution: prefer the project's local venv Python if it exists
# (covers `make coverage` and other dev-deps-requiring targets without
# requiring the user to source venv/bin/activate first). Falls back to
# system python3 — that's what CI uses where the venv is replaced by
# `pip install -e ".[dev]"` against the system interpreter.
PYTHON := $(shell test -x venv/bin/python3 && echo venv/bin/python3 || echo python3)
RUFF := $(shell test -x venv/bin/ruff && echo venv/bin/ruff || echo ruff)
MYPY := $(shell test -x venv/bin/mypy && echo venv/bin/mypy || echo mypy)

.PHONY: help test lint fmt typecheck check coverage integration dx validate-decisions

help:
	@echo "Targets:"
	@echo "  test               Run the fast unit suite (311 tests, ~0.7s; excludes integration)"
	@echo "  lint               Run ruff lint checks (no auto-fix)"
	@echo "  fmt                Run ruff with --fix to apply auto-fixable lint corrections"
	@echo "  typecheck          Run mypy on whizzard + scripts"
	@echo "  check              Run lint + typecheck + unit tests (fail fast on first)"
	@echo "  coverage           Run unit tests with coverage report (fail-under threshold in pyproject.toml)"
	@echo "  integration        Run integration tests (requires real Docker daemon)"
	@echo "  validate-decisions Run scripts/validate_decisions.py (schema + tag-vocab + refs)"
	@echo "  dx ARGS=...        Run scripts/dx.py with ARGS (e.g. make dx ARGS='D-158')"

test:
	$(PYTHON) -m pytest

lint:
	$(RUFF) check whizzard scripts tests

fmt:
	$(RUFF) check --fix whizzard scripts tests

typecheck:
	$(MYPY) whizzard scripts

check: lint typecheck test

coverage:
	$(PYTHON) -m pytest --cov=whizzard --cov-report=term-missing

integration:
	$(PYTHON) -m pytest -m integration -v

validate-decisions:
	$(PYTHON) scripts/validate_decisions.py

dx:
	@$(PYTHON) scripts/dx.py $(ARGS)
