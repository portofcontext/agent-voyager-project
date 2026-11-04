# Each SDK, CLI, and agent owns its dependencies and lockfile.
SHELL := /usr/bin/env bash
UV := uv
.DEFAULT_GOAL := help

PYTHON_PROJECTS := avp-sdk/python avp-cli agents/avp-codex/python agents/avp-pydantic-ai/python agents/avp-claude-agent-sdk/python agents/avp-openai-agents/python agents/avp-deep-agents/python
PI_DIR := agents/avp-pi/typescript
GEMINI_CLI_DIR := agents/avp-gemini-cli/typescript
OPENCODE_DIR := agents/avp-opencode/typescript

.PHONY: help
help:
	@echo "make check          all free SDK, CLI, and adapter checks"
	@echo "make cli-check      CLI format, lint, types, and tests (sandboxes when available)"
	@echo "make test           Python tests in each standalone project"
	@echo "make test-docker    CLI integration tests against a real container engine"
	@echo "make check-agent NAME=avp-<sdk>  one Python adapter's checks"
	@echo "make format         format and lint Python sources"
	@echo "make schemas        generate wire JSON Schemas"
	@echo "make bindings       generate TypeScript SDK types"
	@echo "make bindings-test  TypeScript SDK tests"
	@echo "make sdk-data       refresh shared provider prices and endpoints"
	@echo "make sdk-data-check verify data links and SDK archives"
	@echo "make build-skill    package the skill and offline specs"
	@echo "make sync           install each Python project's locked dependencies"
	@echo "make release-sdk-python | release-sdk-typescript | release-cli  publish a GitHub beta"

.PHONY: sync test format format-check lint schemas sdk-data sdk-data-check build-skill
sync:
	@for project in $(PYTHON_PROJECTS); do $(UV) sync --locked --project $$project || exit 1; done

test:
	@for project in $(PYTHON_PROJECTS); do (cd $$project && $(UV) run pytest -q) || exit 1; done

format:
	@$(UV) run --project avp-sdk/python ruff format .
	@$(UV) run --project avp-sdk/python ruff check --fix .

format-check:
	@$(UV) run --project avp-sdk/python ruff format --check .

lint:
	@$(UV) run --project avp-sdk/python ruff check .

schemas:
	@$(UV) run --project avp-sdk/python python scripts/generate-schemas.py

sdk-data:
	@$(UV) run --project avp-sdk/python python scripts/update-sdk-data.py

sdk-data-check: sdk-typescript-install
	@$(UV) run --project avp-sdk/python python scripts/test-sdk-packaging.py

build-skill:
	@bash scripts/build-skill.sh dist

.PHONY: bindings bindings-check bindings-test
bindings: sdk-typescript-generate
bindings-check: sdk-typescript-bindings-check
bindings-test: sdk-typescript-test

.PHONY: cli-check test-docker check-agent
cli-check:
	@cd avp-cli && $(UV) run ruff format --check .
	@cd avp-cli && $(UV) run ruff check .
	@cd avp-cli && $(UV) run ty check
	@cd avp-cli && $(UV) run pytest -q

test-docker:
	@cd avp-cli && $(UV) run python -c 'from avp_cli.engine import client; client()'
	@cd avp-cli && $(UV) run pytest tests/test_agent.py tests/test_conformance_mock.py -v

check-agent:
	@test -n "$(NAME)" && test -f "agents/$(NAME)/python/pyproject.toml" || { echo "usage: make check-agent NAME=avp-<sdk>"; exit 2; }
	@cd agents/$(NAME)/python && $(UV) run ruff format --check . && $(UV) run ruff check . && $(UV) run ty check && $(UV) run pytest -q

.PHONY: pi-build pi-check
pi-build:
	@npm --prefix $(PI_DIR) ci --no-audit --no-fund
	@npm --prefix $(PI_DIR) run build

pi-check: pi-build
	@npm --prefix $(PI_DIR) run format:check
	@npm --prefix $(PI_DIR) run typecheck
	@npm --prefix $(PI_DIR) test

.PHONY: gemini-cli-build gemini-cli-check
gemini-cli-build:
	@npm --prefix $(GEMINI_CLI_DIR) ci --no-audit --no-fund
	@npm --prefix $(GEMINI_CLI_DIR) run build

gemini-cli-check: gemini-cli-build
	@npm --prefix $(GEMINI_CLI_DIR) run format:check
	@npm --prefix $(GEMINI_CLI_DIR) run typecheck
	@npm --prefix $(GEMINI_CLI_DIR) test

.PHONY: opencode-build opencode-check
opencode-build:
	@npm --prefix $(OPENCODE_DIR) ci --ignore-scripts --no-audit --no-fund
	@npm --prefix $(OPENCODE_DIR) run build

opencode-check: opencode-build
	@npm --prefix $(OPENCODE_DIR) run format:check
	@npm --prefix $(OPENCODE_DIR) run typecheck
	@npm --prefix $(OPENCODE_DIR) test

.PHONY: sdk-python-check
sdk-python-check:
	@cd avp-sdk/python && $(UV) run ruff format --check .
	@cd avp-sdk/python && $(UV) run ruff check .
	@cd avp-sdk/python && $(UV) run ty check
	@cd avp-sdk/python && $(UV) run pytest -q

.PHONY: sdk-typescript-install sdk-typescript-generate sdk-typescript-bindings-check sdk-typescript-test sdk-typescript-check
sdk-typescript-install:
	@npm --prefix avp-sdk/typescript ci --ignore-scripts --no-audit --no-fund

sdk-typescript-generate: sdk-typescript-install
	@npm --prefix avp-sdk/typescript run generate

sdk-typescript-bindings-check: sdk-typescript-install
	@npm --prefix avp-sdk/typescript run generate:check

sdk-typescript-test: sdk-typescript-install
	@npm --prefix avp-sdk/typescript test

sdk-typescript-check: sdk-typescript-install
	@npm --prefix avp-sdk/typescript run format:check
	@npm --prefix avp-sdk/typescript run generate:check
	@npm --prefix avp-sdk/typescript run build
	@npm --prefix avp-sdk/typescript test


.PHONY: codex-check
codex-check:
	@cd agents/avp-codex/python && $(UV) run ruff format --check .
	@cd agents/avp-codex/python && $(UV) run ruff check .
	@cd agents/avp-codex/python && $(UV) run ty check
	@cd agents/avp-codex/python && $(UV) run pytest -q

.PHONY: pydantic-ai-check
pydantic-ai-check:
	@cd agents/avp-pydantic-ai/python && $(UV) run ruff format --check .
	@cd agents/avp-pydantic-ai/python && $(UV) run ruff check .
	@cd agents/avp-pydantic-ai/python && $(UV) run ty check
	@cd agents/avp-pydantic-ai/python && $(UV) run pytest -q

.PHONY: claude-check
claude-check:
	@cd agents/avp-claude-agent-sdk/python && $(UV) run ruff format --check .
	@cd agents/avp-claude-agent-sdk/python && $(UV) run ruff check .
	@cd agents/avp-claude-agent-sdk/python && $(UV) run ty check
	@cd agents/avp-claude-agent-sdk/python && $(UV) run pytest -q

.PHONY: openai-agents-check
openai-agents-check:
	@cd agents/avp-openai-agents/python && $(UV) run ruff format --check .
	@cd agents/avp-openai-agents/python && $(UV) run ruff check .
	@cd agents/avp-openai-agents/python && $(UV) run ty check
	@cd agents/avp-openai-agents/python && $(UV) run pytest -q

.PHONY: deep-agents-check
deep-agents-check:
	@cd agents/avp-deep-agents/python && $(UV) run ruff format --check .
	@cd agents/avp-deep-agents/python && $(UV) run ruff check .
	@cd agents/avp-deep-agents/python && $(UV) run ty check
	@cd agents/avp-deep-agents/python && $(UV) run pytest -q


.PHONY: release-check release-sdk-python release-sdk-typescript release-cli
release-check:
	@$(UV) run --project avp-sdk/python python scripts/test-releases.py

release-sdk-python:
	@$(UV) run --project avp-sdk/python python scripts/release.py tag sdk-python

release-sdk-typescript:
	@$(UV) run --project avp-sdk/python python scripts/release.py tag sdk-typescript

release-cli:
	@$(UV) run --project avp-sdk/python python scripts/release.py tag cli

.PHONY: check
check: format-check lint release-check sdk-data-check sdk-python-check sdk-typescript-check cli-check codex-check pydantic-ai-check claude-check openai-agents-check deep-agents-check pi-check gemini-cli-check opencode-check build-skill
	@echo "All free checks passed."
