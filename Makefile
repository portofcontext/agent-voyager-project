# AVP: orchestration commands for the multi-language repo.
#
# Default target prints help. `make check` is the free pre-commit floor
# (format / lint / unit tests / conformance / bindings drift).
#
# Layout: the core project (spec, conformance, Python/TS bindings) lives
# under avp/; agents under agents/<name>/<lang>/; the local CLI `avp` under
# avp-cli/. The uv (Python) workspace is rooted at the repo root (root
# pyproject.toml + ruff.toml + uv.lock), so `uv` runs from here and spans every
# Python member.
#
# Everything `make check` covers is free. Real-model verification follows
# each adapter's README.

SHELL := /usr/bin/env bash

# The uv workspace is rooted at the repo root; run uv from here.
UV := uv

# Each package has its own pyproject.toml + tests/ directory. Pytest's
# importer collides if invoked at the repo root because every package
# uses the same `tests` dirname, so we iterate per-package.
TEST_PKGS := \
	avp/bindings/python \
	avp/core/conformance \
	agents/_template/python \
	avp-cli



.PHONY: new-agent
new-agent:
	@test -n "$(NAME)" || { echo "usage: make new-agent NAME=avp-<sdk>"; exit 2; }
	@python3 avp/scripts/new-agent.py $(NAME)


.PHONY: help
help:
	@echo "AVP: orchestration commands"
	@echo ""
	@echo "  Free targets (no API calls):"
	@echo "    make pi-check           check the Pi adapter (free; Node >= 22.19)"
	@echo "    make gemini-cli-check   check the Gemini CLI adapter (free; Node >= 22.19)"
	@echo "    make opencode-check     check the OpenCode adapter (free; Node >= 22.19)"
	@echo "    make test            pytest across every package, docker integration tests excluded"
	@echo "    make test-docker     real-sandbox integration tests (free; needs a Docker daemon)"
	@echo "    make conformance     avp-conformance validate + ping (free; no model)"
	@echo "    make lint            ruff check"
	@echo "    make format          ruff format (writes)"
	@echo "    make format-check    ruff format --check (read-only)"
	@echo "    make schemas         regenerate JSON schemas from Pydantic models"
	@echo "    make sdk-data        refresh the SDKs' bundled models.dev prices and endpoints"
	@echo "    make sdk-data-check  check that SDK packages contain all shared provider data"
	@echo "    make sync-prices     refresh bundled prices.json from models.dev (--write)"
	@echo "    make bindings        regenerate current TypeScript SDK wire types"
	@echo "    make bindings-check  check current TypeScript SDK wire-type drift"
	@echo "    make bindings-test   npm test (avp/bindings/typescript)"
	@echo "    make check           format-check + lint + test + pi-check + gemini-cli-check + opencode-check + conformance + bindings-check"
	@echo "    make check-agent NAME=avp-<sdk>  one Python agent: format, lint, its tests + avp-cli's, ping, describe"
	@echo "    make test-fresh      Python agents' tests on unlocked, newest deps (AGENTS=<names>)"
	@echo "    make new-agent NAME=avp-<sdk>       scaffold a Python agent from agents/_template"
	@echo ""
	@echo "  Releases (cut from main; push a tag, CI builds + publishes):"
	@echo "    make release-cli         publish avp-cli to PyPI (tag pypi-v<pyproject version>), after"
	@echo "                             cutting and waiting on any agent release it pins that doesn't exist"
	@echo "    make release-<agent>     release one agent (tag agent-<agent>-v<version in agents.json>)"
	@echo "    make pins                pin avp-cli to each agent's package version (agents.json)"
	@echo ""
	@echo "  Other:"
	@echo "    make sync            uv sync the Python workspace (repo root)"
	@echo "    make build-agents    build each in-tree agent into dist/agents/<name>, laid out like its release"
	@echo "    make smoke-agents    run dist/agents builds in sandbox images against a stub model (AGENTS=<names>)"
	@echo "    make cli-smoke       drive the avp CLI end to end (create->list->delete)"


# ── Free targets ──────────────────────────────────────────────────────────────


.PHONY: test
test:
	@failed=""; \
	for pkg in $(TEST_PKGS); do \
		echo "==== $$pkg (test) ===="; \
		(cd $$pkg && uv run python -m pytest -m "not real_llm and not docker" -q; e=$$?; [ $$e -eq 0 ] || [ $$e -eq 5 ]) || failed="$$failed $$pkg"; \
	done; \
	if [ -n "$$failed" ]; then echo ""; echo "FAILED packages:$$failed"; exit 1; fi; \
	echo ""; echo "All package tests passed."


# The real-sandbox integration tests: a managed OpenSandbox server over the local
# Docker daemon, a stock-image sandbox, the run contract + trajectory bind-mount
# round trip, and egress-deny enforcement. Free (no model), needs Docker.
# Egress enforcement is REQUIRED here (the strict local gate); in CI the same
# test skips when the runner's kernel can't support the sidecar's hooks.
.PHONY: test-docker
test-docker:
	@cd avp-cli && AVP_REQUIRE_EGRESS_ENFORCEMENT=1 uv run python -m pytest tests/test_docker.py -m docker -v


# Manifest paths, relative to the repo root the harness runs from.
TEMPLATE_MANIFEST := agents/_template/python/avp-conformance.json
# TypeScript adapters run from their build output; `pi-build` installs and builds.
PI_DIR := agents/avp-pi/typescript
GEMINI_CLI_DIR := agents/avp-gemini-cli/typescript
OPENCODE_DIR := agents/avp-opencode/typescript

# Validate legacy cases and the remaining Python template without model calls.
.PHONY: conformance
conformance:
	@$(UV) run avp-conformance validate
	@printf "\n\033[1;36m── agent template (python) ──\033[0m\n"
	@$(UV) run avp-conformance ping --agent $(TEMPLATE_MANIFEST)
	@$(UV) run avp-conformance describe --agent $(TEMPLATE_MANIFEST)

.PHONY: pi-build pi-check
pi-build: sdk-typescript-install
	@npm --prefix avp-sdk/typescript run build
	@npm --prefix $(PI_DIR) ci --no-audit --no-fund
	@npm --prefix $(PI_DIR) run build

pi-check: pi-build
	@npm --prefix $(PI_DIR) run format:check
	@npm --prefix $(PI_DIR) run typecheck
	@npm --prefix $(PI_DIR) test

.PHONY: gemini-cli-build gemini-cli-check
gemini-cli-build: sdk-typescript-install
	@npm --prefix avp-sdk/typescript run build
	@npm --prefix $(GEMINI_CLI_DIR) ci --no-audit --no-fund
	@npm --prefix $(GEMINI_CLI_DIR) run build

gemini-cli-check: gemini-cli-build
	@npm --prefix $(GEMINI_CLI_DIR) run format:check
	@npm --prefix $(GEMINI_CLI_DIR) run typecheck
	@npm --prefix $(GEMINI_CLI_DIR) test

.PHONY: opencode-build opencode-check
opencode-build: sdk-typescript-install
	@npm --prefix avp-sdk/typescript run build
	@npm --prefix $(OPENCODE_DIR) ci --ignore-scripts --no-audit --no-fund
	@npm --prefix $(OPENCODE_DIR) run build

opencode-check: opencode-build
	@npm --prefix $(OPENCODE_DIR) run format:check
	@npm --prefix $(OPENCODE_DIR) run typecheck
	@npm --prefix $(OPENCODE_DIR) test

.PHONY: lint
lint:
	@$(UV) run ruff check .


.PHONY: format
format:
	@$(UV) run ruff format .
	@$(UV) run ruff check --fix .


.PHONY: format-check
format-check:
	@$(UV) run ruff format --check .
	@$(UV) run ruff check .


.PHONY: schemas
schemas:
	@$(UV) run --project avp-sdk/python python scripts/generate-schemas.py


.PHONY: sdk-data
sdk-data:
	@$(UV) run --project avp-sdk/python python scripts/update-sdk-data.py

.PHONY: sdk-data-check
sdk-data-check: sdk-typescript-install
	@$(UV) run --project avp-sdk/python python scripts/test-sdk-packaging.py


.PHONY: sync-prices
sync-prices:
	@$(UV) run python avp/scripts/sync-prices.py --write


# Binding generation follows the current SDK schemas. The legacy TypeScript
# library remains tested until the old CLI/conformance stack is retired.
.PHONY: bindings bindings-check bindings-test
bindings: sdk-typescript-generate

bindings-check: sdk-typescript-bindings-check

bindings-test:
	@npm --prefix avp/bindings/typescript ci --ignore-scripts --no-audit --no-fund
	@npm --prefix avp/bindings/typescript test --silent


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

.PHONY: check
check: format-check lint sdk-data-check test pi-check gemini-cli-check opencode-check conformance bindings-check sdk-python-check sdk-typescript-check codex-check pydantic-ai-check claude-check openai-agents-check deep-agents-check
	@echo ""; echo "✓ All free checks passed."

# One Python agent's share of `make check`: format and lint, its tests, the
# CLI's registration tests, case validation, and its own ping and describe.
# Each released Python agent's tests on a fresh install of its wheels, with the
# newest dependencies they allow instead of the lock releases install. Early
# warning that `uv lock --upgrade` would break an agent. Free; AGENTS= narrows it.
.PHONY: test-fresh
test-fresh:
	@$(UV) run python avp/scripts/test-fresh-installs.py $(AGENTS)

.PHONY: check-agent
check-agent:
	@test -n "$(NAME)" || { echo "usage: make check-agent NAME=avp-<sdk>"; exit 2; }
	@test -f agents/$(NAME)/python/avp-conformance.json || { echo "error: no Python agent at agents/$(NAME)/python"; exit 2; }
	@$(MAKE) --no-print-directory format-check
	@$(MAKE) --no-print-directory test TEST_PKGS="agents/$(NAME)/python avp-cli"
	@$(UV) run avp-conformance validate
	@$(UV) run avp-conformance ping --agent agents/$(NAME)/python/avp-conformance.json
	@$(UV) run avp-conformance describe --agent agents/$(NAME)/python/avp-conformance.json
	@echo ""; echo "✓ $(NAME) checks passed."


# ── Releases ──────────────────────────────────────────────────────────────────
#
# Every release is a pushed git tag; CI does the build + publish (PyPI via
# Trusted Publishing, agents via GitHub releases). These targets just cut the
# right tag from a clean main, deriving the version from the single source of
# truth so the tag can never drift from what the code expects:
#   - avp-cli  -> version in avp-cli/pyproject.toml           (tag pypi-v<version>)
#   - agents   -> the agent's package version, which `make pins` copies into
#                 avp-cli's agents.json                        (tag agent-<name>-v<version>)
# An agent release publishes only after it runs in a sandbox image against a
# stub model (.github/workflows/agent-release.yml). To bump an agent, change
# its package version, `make pins`, commit, merge, then `make release-cli`
# (or `make release-<name>` for the agent alone).


# Guard shared by every release target: on main, clean tree, in sync with origin.
.PHONY: _release-guard
_release-guard:
	@test "$$(git rev-parse --abbrev-ref HEAD)" = "main" \
		|| { echo "error: releases are cut from main (you are on $$(git rev-parse --abbrev-ref HEAD))"; exit 1; }
	@git diff --quiet && git diff --cached --quiet \
		|| { echo "error: working tree is dirty; commit or stash before releasing"; exit 1; }
	@git fetch -q origin main \
		&& test "$$(git rev-parse HEAD)" = "$$(git rev-parse origin/main)" \
		|| { echo "error: local main is not in sync with origin/main; push or pull first"; exit 1; }
	@$(UV) run python avp/scripts/agent-pins.py --check


# Tag + push a release. $(1) = tag, $(2) = annotation. Refuses to clobber an
# existing tag (bump the version in its source of truth instead).
define cut_release
	@git rev-parse -q --verify "refs/tags/$(1)" >/dev/null \
		&& { echo "error: tag $(1) already exists; bump the version first"; exit 1; } || true
	@echo "→ cutting $(1)"
	@git tag -a "$(1)" -m "$(2)" && git push origin "$(1)"
	@echo "✓ pushed $(1); watch the build with: gh run watch \$$(gh run list -L1 --json databaseId -q '.[0].databaseId')"
endef


# The CLI installs the agent releases agents.json pins, so they must all be
# published first: release-agents.py cuts any that aren't and waits for them.
.PHONY: release-cli
release-cli: _release-guard
	@$(UV) run python avp/scripts/release-agents.py
	@version=$$(grep -m1 '^version' avp-cli/pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'); \
	echo "→ verifying the wheel builds (avp-cli $$version)..."; \
	$(UV) build --wheel --package avp-cli --out-dir dist/release >/dev/null; \
	$(MAKE) --no-print-directory _cut TAG="pypi-v$$version" MSG="avp-cli $$version"


# One agent's release, at the version agents.json pins (= its package version).
release-%: _release-guard
	@$(UV) run python avp/scripts/release-agents.py $*


.PHONY: pins
pins:
	@$(UV) run python avp/scripts/agent-pins.py


# Internal: cut the tag named by TAG. Kept separate so the release-* targets can
# compute TAG in a recipe shell, then hand it to the cut_release template.
.PHONY: _cut
_cut:
	$(call cut_release,$(TAG),$(MSG))


# ── Other ─────────────────────────────────────────────────────────────────────


.PHONY: sync
sync:
	@$(UV) sync


# Drive the `avp` CLI end to end: create -> list -> inspect -> delete across
# commissions, environments, and vault secrets, against a throwaway AVP_HOME.
#   make cli-smoke
.PHONY: cli-smoke
cli-smoke:
	@$(UV) run bash scripts/cli-smoke.sh


# Build the in-tree agents (AGENTS=<names>, default all) into dist/agents/<name>,
# each laid out like its release (artifacts + avp-release.json). This is the
# contributor loop for testing an agent before cutting a release: build here,
# `make smoke-agents`, install under a -dev name, run an eval against it.
# Python wheels need uv; Node agents need npm.
AGENT_NAMES = $(shell python3 -c "import json; print(' '.join(json.load(open('avp-cli/src/avp_cli/agents.json'))))")

.PHONY: build-agents
build-agents:
	@for agent in $(or $(AGENTS),$(AGENT_NAMES)); do \
		echo "→ building $$agent into dist/agents/$$agent"; \
		$(UV) run python avp/scripts/build-agent.py $$agent dist/agents/$$agent || exit 1; \
	done
	@echo ""
	@echo "✓ built into dist/agents. Install one as a local build (add --force to replace it):"
	@echo "  uv run avp agent install <name> --as <name>-dev --from dist/agents/<name>"


# Run each dist/agents build (AGENTS=<names>, default every built one) in its
# sandbox image against a stub model, as the release workflows do before
# publishing. Needs Docker; no API key.
.PHONY: smoke-agents
smoke-agents:
	@agents="$(or $(AGENTS),$$(cd dist/agents 2>/dev/null && ls -d */ | tr -d /))"; \
	test -n "$$agents" || { echo "error: nothing in dist/agents; run make build-agents"; exit 1; }; \
	failed=""; for agent in $$agents; do \
		$(UV) run python avp/scripts/smoke-agent.py $$agent --from dist/agents/$$agent || failed="$$failed $$agent"; \
	done; \
	test -z "$$failed" || { echo "smoke failed:$$failed"; exit 1; }


# Default goal
.DEFAULT_GOAL := help
