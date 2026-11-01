# AVP: orchestration commands for the multi-language repo.
#
# Default target prints help. `make check` is the free pre-commit floor
# (format / lint / unit tests / conformance / bindings drift).
#
# Layout: the core project (spec, conformance, Python/Rust/TS bindings) lives
# under avp/; agents under agents/<name>/<lang>/; the local CLI `avp` under
# avp-cli-legacy/. The uv (Python) workspace is rooted at the repo root (root
# pyproject.toml + ruff.toml + uv.lock), so `uv` runs from here and spans every
# Python member.
#
# Cost notes: targets that hit a real LLM are clearly marked (the paid block in
# `make help`) and require ANTHROPIC_API_KEY; they run roughly $0.10 to $0.20 on
# Haiku. Everything `make check` covers is free.

SHELL := /usr/bin/env bash

# The uv workspace is rooted at the repo root; run uv from here.
UV := uv

# Each package has its own pyproject.toml + tests/ directory. Pytest's
# importer collides if invoked at the repo root because every package
# uses the same `tests` dirname, so we iterate per-package.
TEST_PKGS := \
	avp/bindings/python \
	avp/core/conformance \
	agents/avp-claude-agent-sdk/python \
	agents/_template/python \
	agents/avp-pydantic-ai/python \
	agents/avp-deep-agents/python \
	agents/avp-codex/python \
	agents/avp-openai-agents/python \
	avp-cli-legacy



.PHONY: new-agent new-agent-rust
new-agent:
	@test -n "$(NAME)" || { echo "usage: make new-agent NAME=avp-<sdk>"; exit 2; }
	@python3 avp/scripts/new-agent.py $(NAME) --lang python

new-agent-rust:
	@test -n "$(NAME)" || { echo "usage: make new-agent-rust NAME=avp-<sdk>"; exit 2; }
	@python3 avp/scripts/new-agent.py $(NAME) --lang rust


.PHONY: help
help:
	@echo "AVP: orchestration commands"
	@echo ""
	@echo "  Free targets (no API calls):"
	@echo "    make test            pytest across every package, docker integration tests excluded"
	@echo "    make test-docker     real-sandbox integration tests (free; needs a Docker daemon)"
	@echo "    make conformance     avp-conformance validate + ping (free; no model)"
	@echo "    make lint            ruff check"
	@echo "    make format          ruff format (writes)"
	@echo "    make format-check    ruff format --check (read-only)"
	@echo "    make schemas         regenerate JSON schemas from Pydantic models"
	@echo "    make sdk-data        refresh the SDKs' bundled models.dev prices and base URLs"
	@echo "    make sync-prices     refresh bundled prices.json from models.dev (--write)"
	@echo "    make bindings        regenerate language bindings from Pydantic schemas"
	@echo "    make bindings-check  drift detector (regen + git-diff against tracked)"
	@echo "    make bindings-test   cargo test (avp/bindings/rust) + npm test (avp/bindings/typescript)"
	@echo "    make check           format-check + lint + test + test-pi + test-gemini-cli + test-opencode + conformance + bindings-check"
	@echo "    make check-agent NAME=avp-<sdk>  one Python agent: format, lint, its tests + avp-cli's, ping, describe"
	@echo "    make test-fresh      Python agents' tests on unlocked, newest deps (AGENTS=<names>)"
	@echo "    make new-agent NAME=avp-<sdk>       scaffold a Python agent from agents/_template"
	@echo "    make new-agent-rust NAME=avp-<sdk>  scaffold a Rust agent from agents/_template"
	@echo ""
	@echo "  Paid targets (cost real money; require ANTHROPIC_API_KEY):"
	@echo "    make conformance-check  run the v0.1 suite against Claude, Goose, and Pi on a real model"
	@echo "    make pi-check           run the v0.1 suite against avp-pi only (Node >= 22.19)"
	@echo "    make gemini-cli-check   run the v0.1 suite against avp-gemini-cli on Gemini (GEMINI_API_KEY)"
	@echo "    make opencode-check     run the v0.1 suite against avp-opencode (OPENAI_API_KEY)"
	@echo "    make test-live          gated avp-goose live tests (live_mcp /"
	@echo "                            live_skills; spawn the Python fixture + call a real model)."
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
	@echo "    make cli-smoke       drive the avp CLI end to end (create->list->delete; PAID=1 adds the vault-broker finale)"


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
	@cd avp-cli-legacy && AVP_REQUIRE_EGRESS_ENFORCEMENT=1 uv run python -m pytest tests/test_docker.py -m docker -v


# Manifest paths, relative to the repo root the harness runs from.
CLAUDE_MANIFEST := agents/avp-claude-agent-sdk/python/avp-conformance.json
GOOSE_MANIFEST  := agents/avp-goose/rust/avp-conformance.json
TEMPLATE_MANIFEST := agents/_template/python/avp-conformance.json
AVP_PYDANTIC_AI_MANIFEST := agents/avp-pydantic-ai/python/avp-conformance.json
AVP_DEEP_AGENTS_MANIFEST := agents/avp-deep-agents/python/avp-conformance.json
AVP_CODEX_MANIFEST := agents/avp-codex/python/avp-conformance.json
OPENAI_MANIFEST := agents/avp-openai-agents/python/avp-conformance.json
# TypeScript adapters run from their build output; `pi-build` installs and builds.
PI_DIR := agents/avp-pi/typescript
PI_MANIFEST := $(PI_DIR)/avp-conformance.json
GEMINI_CLI_DIR := agents/avp-gemini-cli/typescript
GEMINI_CLI_MANIFEST := $(GEMINI_CLI_DIR)/avp-conformance.json
# The cases pin a Claude model; Gemini CLI runs them on a Gemini one.
GEMINI_CLI_MODEL ?= google/gemini-3.1-flash-lite
OPENCODE_DIR := agents/avp-opencode/typescript
OPENCODE_MANIFEST := $(OPENCODE_DIR)/avp-conformance.json

# Set SANDBOX=--sandbox to run each agent inside the `srt` sandbox
# (@anthropic-ai/sandbox-runtime). Off by default so `conformance-check` works
# on machines without srt installed; on for any untrusted / CI run.
SANDBOX ?=


# ── Free: validate case files + liveness-ping + describe each agent (no model) ─
.PHONY: claude-ping goose-build goose-ping claude-describe goose-describe
claude-ping:
	@$(UV) run avp-conformance ping --agent $(CLAUDE_MANIFEST)

# Compile before pinging: the manifest runs `cargo run`, and a cold build
# would otherwise eat the ping's timeout.
goose-build:
	@cd agents/avp-goose/rust && cargo build --quiet --features conformance --bin avp-goose-conformance

goose-ping: goose-build
	@$(UV) run avp-conformance ping --agent $(GOOSE_MANIFEST)

claude-describe:
	@$(UV) run avp-conformance describe --agent $(CLAUDE_MANIFEST)

goose-describe: goose-build
	@$(UV) run avp-conformance describe --agent $(GOOSE_MANIFEST)


.PHONY: conformance
conformance:
	@$(UV) run avp-conformance validate
	@printf "\n\033[1;36m── avp-claude-agent-sdk ──\033[0m\n"
	@$(MAKE) --no-print-directory claude-ping
	@$(MAKE) --no-print-directory claude-describe
	@printf "\n\033[1;36m── avp-goose ──\033[0m\n"
	@$(MAKE) --no-print-directory goose-ping
	@$(MAKE) --no-print-directory goose-describe
	@printf "\n\033[1;36m── agent template (python) ──\033[0m\n"
	@$(UV) run avp-conformance ping --agent $(TEMPLATE_MANIFEST)
	@$(UV) run avp-conformance describe --agent $(TEMPLATE_MANIFEST)
	@printf "\n\033[1;36m── avp-pydantic-ai ──\033[0m\n"
	@$(UV) run avp-conformance ping --agent $(AVP_PYDANTIC_AI_MANIFEST)
	@$(UV) run avp-conformance describe --agent $(AVP_PYDANTIC_AI_MANIFEST)
	@printf "\n\033[1;36m── avp-deep-agents ──\033[0m\n"
	@$(UV) run avp-conformance ping --agent $(AVP_DEEP_AGENTS_MANIFEST)
	@$(UV) run avp-conformance describe --agent $(AVP_DEEP_AGENTS_MANIFEST)
	@printf "\n\033[1;36m── avp-codex ──\033[0m\n"
	@$(UV) run avp-conformance ping --agent $(AVP_CODEX_MANIFEST)
	@$(UV) run avp-conformance describe --agent $(AVP_CODEX_MANIFEST)
	@printf "\n\033[1;36m── avp-openai-agents ──\033[0m\n"
	@$(UV) run avp-conformance ping --agent $(OPENAI_MANIFEST)
	@$(UV) run avp-conformance describe --agent $(OPENAI_MANIFEST)
	@printf "\n\033[1;36m── avp-pi ──\033[0m\n"
	@$(MAKE) --no-print-directory pi-build
	@$(UV) run avp-conformance ping --agent $(PI_MANIFEST)
	@$(UV) run avp-conformance describe --agent $(PI_MANIFEST)
	@printf "\n\033[1;36m── avp-gemini-cli ──\033[0m\n"
	@$(MAKE) --no-print-directory gemini-cli-build
	@$(UV) run avp-conformance ping --agent $(GEMINI_CLI_MANIFEST)
	@$(UV) run avp-conformance describe --agent $(GEMINI_CLI_MANIFEST)
	@printf "\n\033[1;36m── avp-opencode ──\033[0m\n"
	@$(MAKE) --no-print-directory opencode-build
	@$(UV) run avp-conformance ping --agent $(OPENCODE_MANIFEST)
	@$(UV) run avp-conformance describe --agent $(OPENCODE_MANIFEST)

.PHONY: pi-build test-pi
pi-build:
	@cd $(PI_DIR) && npm ci --silent --no-audit --no-fund && npm run --silent build

# Pi's integration tests: its real session loop, tools, and MCP extension on a
# scripted model. Free; needs Node >= 22.19 and python3 (the MCP fixture).
test-pi: pi-build
	@cd $(PI_DIR) && node --test 'dist/tests/*.test.js'

.PHONY: gemini-cli-build test-gemini-cli
# Without optional dependencies (native PTY and keychain modules), as the
# release archive ships: the shell tool runs on child processes.
gemini-cli-build:
	@cd $(GEMINI_CLI_DIR) && npm ci --silent --omit=optional --no-audit --no-fund && npm run --silent build

# Gemini CLI's integration tests: its headless session, tools, subagents, and MCP
# client on its scripted content generator. Free; needs Node >= 22.19 and
# python3 (the MCP fixture).
test-gemini-cli: gemini-cli-build
	@cd $(GEMINI_CLI_DIR) && node --test 'dist/tests/*.test.js'

.PHONY: opencode-build test-opencode
opencode-build:
	@cd $(OPENCODE_DIR) && npm ci --silent --no-audit --no-fund && npm run --silent build

# OpenCode's integration tests: the real `opencode serve` (pinned binary), its tools,
# MCP client, and subagents on a scripted model. Free; needs Node >= 22.19 and
# python3 (the MCP fixture).
test-opencode: opencode-build
	@cd $(OPENCODE_DIR) && node --test --test-concurrency=1 'dist/tests/*.test.js'


# ── Paid: run the v0.1 suite against each agent on a real model ────────────────
.PHONY: claude-check goose-check
claude-check:
	@$(UV) run avp-conformance check --agent $(CLAUDE_MANIFEST) --suite v0.1 $(SANDBOX)

goose-check:
	@$(UV) run avp-conformance check --agent $(GOOSE_MANIFEST) --suite v0.1 $(SANDBOX)

.PHONY: pi-check
pi-check: pi-build
	@$(UV) run avp-conformance check --agent $(PI_MANIFEST) --suite v0.1 $(SANDBOX)

.PHONY: gemini-cli-check
gemini-cli-check: gemini-cli-build
	@if [ -z "$$GEMINI_API_KEY" ]; then \
		echo "error: GEMINI_API_KEY is not set; gemini-cli-check runs cases on a real model"; exit 2; \
	fi
	@$(UV) run avp-conformance check --agent $(GEMINI_CLI_MANIFEST) --suite v0.1 --model $(GEMINI_CLI_MODEL) $(SANDBOX)

# OpenCode on an OpenAI model (OPENAI_API_KEY); override with OPENCODE_MODEL.
OPENCODE_MODEL ?= openai/gpt-5-mini
.PHONY: opencode-check
opencode-check: opencode-build
	@$(UV) run avp-conformance check --agent $(OPENCODE_MANIFEST) --suite v0.1 --model $(OPENCODE_MODEL) $(SANDBOX)


.PHONY: conformance-check
conformance-check:
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "error: ANTHROPIC_API_KEY is not set; conformance-check runs cases on a real model"; exit 2; \
	fi
	@printf "\n\033[1;36m── avp-claude-agent-sdk ──\033[0m\n"
	@$(MAKE) --no-print-directory claude-check
	@printf "\n\033[1;36m── avp-goose ──\033[0m\n"
	@$(MAKE) --no-print-directory goose-check
	@printf "\n\033[1;36m── avp-pi ──\033[0m\n"
	@$(MAKE) --no-print-directory pi-check


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


.PHONY: sync-prices
sync-prices:
	@$(UV) run python avp/scripts/sync-prices.py --write


.PHONY: bindings
bindings:
	@bash avp/scripts/generate-bindings.sh


.PHONY: bindings-check
bindings-check:
	@# Drift check: snapshot current bindings, regenerate, diff against
	@# the snapshot. Pure working-tree comparison; does NOT require the
	@# bindings to be committed. If regeneration changes any byte, the
	@# user's bindings are stale relative to types.py / schemas.
	@snapshot=$$(mktemp -d); \
	cp -R avp/bindings/rust/src "$$snapshot/rust-src"; \
	cp -R avp/bindings/typescript/src "$$snapshot/ts-src"; \
	bash avp/scripts/generate-bindings.sh > /dev/null; \
	if ! diff -rq "$$snapshot/rust-src" avp/bindings/rust/src > /dev/null 2>&1 \
	   || ! diff -rq "$$snapshot/ts-src" avp/bindings/typescript/src > /dev/null 2>&1; then \
		echo "error: Rust/TS bindings are stale relative to schemas. Run 'make bindings'." >&2; \
		diff -rq "$$snapshot/rust-src" avp/bindings/rust/src 2>&1 | head -10 >&2 || true; \
		diff -rq "$$snapshot/ts-src" avp/bindings/typescript/src 2>&1 | head -10 >&2 || true; \
		rm -rf "$$snapshot"; \
		exit 1; \
	fi; \
	rm -rf "$$snapshot"; \
	echo "✓ Bindings in sync with schemas."


.PHONY: bindings-test
bindings-test:
	@cd avp/bindings/rust && cargo test --quiet
	@cd avp/bindings/typescript && npm test --silent


.PHONY: check
check: format-check lint test test-pi test-gemini-cli test-opencode conformance bindings-check
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
	@$(MAKE) --no-print-directory test TEST_PKGS="agents/$(NAME)/python avp-cli-legacy"
	@$(UV) run avp-conformance validate
	@$(UV) run avp-conformance ping --agent agents/$(NAME)/python/avp-conformance.json
	@$(UV) run avp-conformance describe --agent agents/$(NAME)/python/avp-conformance.json
	@echo ""; echo "✓ $(NAME) checks passed."


# ── Paid targets (real LLM) ───────────────────────────────────────────────────


.PHONY: test-live
test-live:
	@echo "Running gated avp-goose live tests (mcp_connect is key-free; live_mcp / live_skills / live_subagent call a real model)."
	@cd agents/avp-goose/rust && cargo test --test live_mcp --test live_skills --test live_subagent -- --ignored


# ── Releases ──────────────────────────────────────────────────────────────────
#
# Every release is a pushed git tag; CI does the build + publish (PyPI via
# Trusted Publishing, agents via GitHub releases). These targets just cut the
# right tag from a clean main, deriving the version from the single source of
# truth so the tag can never drift from what the code expects:
#   - avp-cli  -> version in avp-cli-legacy/pyproject.toml           (tag pypi-v<version>)
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
	@version=$$(grep -m1 '^version' avp-cli-legacy/pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'); \
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
# PAID=1 adds the grand finale (a CLI-built secret + env + commission run through
# the credential broker in a real sandbox; needs Docker + OPENROUTER_API_KEY).
#   make cli-smoke
#   make cli-smoke PAID=1
.PHONY: cli-smoke
cli-smoke:
	@AVP_SMOKE_PAID=$(if $(filter 1,$(PAID)),1,0) $(UV) run bash scripts/cli-smoke.sh


# Build the in-tree agents (AGENTS=<names>, default all) into dist/agents/<name>,
# each laid out like its release (artifacts + avp-release.json). This is the
# contributor loop for testing an agent before cutting a release: build here,
# `make smoke-agents`, install under a -dev name, run an eval against it. (The
# goose build needs the Rust toolchain + Goose's system deps, and runs in the
# sandbox only when built on Linux; the wheels need uv; Node agents need npm.)
AGENT_NAMES = $(shell python3 -c "import json; print(' '.join(json.load(open('avp-cli-legacy/src/avp_cli/agents.json'))))")

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
