# AVP: orchestration commands for the multi-language repo.
#
# Default target prints help. `make check` is the free pre-commit floor
# (format / lint / unit tests / conformance / bindings drift).
#
# Layout: the core project (spec, conformance, Python/Rust/TS bindings) lives
# under avp/; agents under agents/<name>/<lang>/; the local CLI `avp` under
# avp-cli/. The uv (Python) workspace is rooted at the repo root (root
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
	avp-cli



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
	@echo "    make sync-prices     refresh bundled prices.json from models.dev (--write)"
	@echo "    make bindings        regenerate language bindings from Pydantic schemas"
	@echo "    make bindings-check  drift detector (regen + git-diff against tracked)"
	@echo "    make bindings-test   cargo test (avp/bindings/rust) + npm test (avp/bindings/typescript)"
	@echo "    make check           format-check + lint + test + test-pi + test-gemini-cli + test-opencode + conformance + bindings-check"
	@echo "    make check-agent NAME=avp-<sdk>  one Python agent: format, lint, its tests + avp-cli's, ping, describe"
	@echo "    make test-fresh      released Python agents' tests on fresh installs (newest deps; AGENTS=<names>)"
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
	@echo "    make release-cli         publish avp-cli to PyPI (tag pypi-v<pyproject version>)"
	@echo "    make release-goose       release the goose agent (tag agent-goose-v<pinned version>)"
	@echo "    make release-claude-code release the claude-code agent (tag agent-claude-code-v<pinned version>)"
	@echo "    make release-codex       release the codex agent (tag agent-codex-v<pinned version>)"
	@echo "    make release-openai-agents release the openai-agents agent (tag agent-openai-agents-v<pinned version>)"
	@echo "    make release-pi          release the pi agent (tag agent-pi-v<pinned version>)"
	@echo "    make release-gemini-cli  release the gemini-cli agent (tag agent-gemini-cli-v<pinned version>)"
	@echo "    make release-deep-agents release the deep-agents agent (tag agent-deep-agents-v<pinned version>)"
	@echo "    make release-pydantic-ai release the pydantic-ai agent (tag agent-pydantic-ai-v<pinned version>)"
	@echo "    make release-opencode    release the opencode agent (tag agent-opencode-v<pinned version>)"
	@echo "                             agent versions come from container_version in avp_cli.agents"
	@echo ""
	@echo "  Other:"
	@echo "    make sync            uv sync the Python workspace (repo root)"
	@echo "    make build-agents    build the in-tree agents' artifacts into dist/agents for local install"
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
	@cd avp-cli && AVP_REQUIRE_EGRESS_ENFORCEMENT=1 uv run python -m pytest tests/test_docker.py -m docker -v


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
	@$(UV) run python avp/scripts/generate-schemas.py


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
# newest dependencies they allow (no lockfile), the way a sandbox image gets
# them. Catches upstream drift `make test` can't see. Free; AGENTS= narrows it.
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
#   - avp-cli  -> version in avp-cli/pyproject.toml        (tag pypi-v<version>)
#   - agents   -> container_version in avp_cli.agents      (tag agent-<name>-v<version>)
# To bump an agent, edit its container_version, commit, then `make release-<name>`.


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


# Tag + push a release. $(1) = tag, $(2) = annotation. Refuses to clobber an
# existing tag (bump the version in its source of truth instead).
define cut_release
	@git rev-parse -q --verify "refs/tags/$(1)" >/dev/null \
		&& { echo "error: tag $(1) already exists; bump the version first"; exit 1; } || true
	@echo "→ cutting $(1)"
	@git tag -a "$(1)" -m "$(2)" && git push origin "$(1)"
	@echo "✓ pushed $(1); watch the build with: gh run watch \$$(gh run list -L1 --json databaseId -q '.[0].databaseId')"
endef


.PHONY: release-cli
release-cli: _release-guard
	@version=$$(grep -m1 '^version' avp-cli/pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'); \
	echo "→ verifying the wheel builds (avp-cli $$version)..."; \
	$(UV) build --wheel --package avp-cli --out-dir dist/release >/dev/null; \
	$(MAKE) --no-print-directory _cut TAG="pypi-v$$version" MSG="avp-cli $$version"


# Agent releases derive the tag from the agent's OWN package version (the same
# number its descriptor reports as agent_version and Commission.agent_versions
# pins match), guarded against the CLI's container_version pin so the two can't
# drift: bump the package version AND the pin together, commit, release.
.PHONY: release-goose
release-goose: _release-guard
	@version=$$(grep -m1 '^version' agents/avp-goose/rust/Cargo.toml | sed -E 's/.*"([^"]+)".*/\1/'); \
	pin=$$($(UV) run python -c "from avp_cli.agents import AGENT_SOURCES; print(AGENT_SOURCES['goose'].container_version)"); \
	test "$$version" = "$$pin" || { echo "error: avp-goose Cargo.toml version ($$version) != container_version pin in avp_cli.agents ($$pin); bump them together"; exit 1; }; \
	$(MAKE) --no-print-directory _cut TAG="agent-goose-v$$version" MSG="goose agent $$version"


.PHONY: release-claude-code
release-claude-code: _release-guard
	@version=$$(grep -m1 '^version' agents/avp-claude-agent-sdk/python/pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'); \
	pin=$$($(UV) run python -c "from avp_cli.agents import AGENT_SOURCES; print(AGENT_SOURCES['claude-code'].container_version)"); \
	test "$$version" = "$$pin" || { echo "error: avp-claude-agent-sdk pyproject version ($$version) != container_version pin in avp_cli.agents ($$pin); bump them together"; exit 1; }; \
	$(MAKE) --no-print-directory _cut TAG="agent-claude-code-v$$version" MSG="claude-code agent $$version"


.PHONY: release-codex
release-codex: _release-guard
	@version=$$(grep -m1 '^version' agents/avp-codex/python/pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'); \
	pin=$$($(UV) run python -c "from avp_cli.agents import AGENT_SOURCES; print(AGENT_SOURCES['codex'].container_version)"); \
	test "$$version" = "$$pin" || { echo "error: avp-codex pyproject version ($$version) != container_version pin in avp_cli.agents ($$pin); bump them together"; exit 1; }; \
	$(MAKE) --no-print-directory _cut TAG="agent-codex-v$$version" MSG="codex agent $$version"


.PHONY: release-openai-agents
release-openai-agents: _release-guard
	@version=$$(grep -m1 '^version' agents/avp-openai-agents/python/pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'); \
	pin=$$($(UV) run python -c "from avp_cli.agents import AGENT_SOURCES; print(AGENT_SOURCES['openai-agents'].container_version)"); \
	test "$$version" = "$$pin" || { echo "error: avp-openai-agents pyproject version ($$version) != container_version pin in avp_cli.agents ($$pin); bump them together"; exit 1; }; \
	$(MAKE) --no-print-directory _cut TAG="agent-openai-agents-v$$version" MSG="openai-agents agent $$version"


.PHONY: release-pi
release-pi: _release-guard
	@version=$$(node -p 'require("./agents/avp-pi/typescript/package.json").version'); \
	pin=$$($(UV) run python -c "from avp_cli.agents import AGENT_SOURCES; print(AGENT_SOURCES['pi'].container_version)"); \
	test "$$version" = "$$pin" || { echo "error: avp-pi package.json version ($$version) != container_version pin in avp_cli.agents ($$pin); bump them together"; exit 1; }; \
	$(MAKE) --no-print-directory _cut TAG="agent-pi-v$$version" MSG="pi agent $$version"

.PHONY: release-gemini-cli
release-gemini-cli: _release-guard
	@version=$$(node -p 'require("./agents/avp-gemini-cli/typescript/package.json").version'); \
	pin=$$($(UV) run python -c "from avp_cli.agents import AGENT_SOURCES; print(AGENT_SOURCES['gemini-cli'].container_version)"); \
	test "$$version" = "$$pin" || { echo "error: avp-gemini-cli package.json version ($$version) != container_version pin in avp_cli.agents ($$pin); bump them together"; exit 1; }; \
	$(MAKE) --no-print-directory _cut TAG="agent-gemini-cli-v$$version" MSG="gemini-cli agent $$version"


.PHONY: release-deep-agents
release-deep-agents: _release-guard
	@version=$$(grep -m1 '^version' agents/avp-deep-agents/python/pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'); \
	pin=$$($(UV) run python -c "from avp_cli.agents import AGENT_SOURCES; print(AGENT_SOURCES['deep-agents'].container_version)"); \
	test "$$version" = "$$pin" || { echo "error: avp-deep-agents pyproject version ($$version) != container_version pin in avp_cli.agents ($$pin); bump them together"; exit 1; }; \
	$(MAKE) --no-print-directory _cut TAG="agent-deep-agents-v$$version" MSG="deep-agents agent $$version"


.PHONY: release-pydantic-ai
release-pydantic-ai: _release-guard
	@version=$$(grep -m1 '^version' agents/avp-pydantic-ai/python/pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'); \
	pin=$$($(UV) run python -c "from avp_cli.agents import AGENT_SOURCES; print(AGENT_SOURCES['pydantic-ai'].container_version)"); \
	test "$$version" = "$$pin" || { echo "error: avp-pydantic-ai pyproject version ($$version) != container_version pin in avp_cli.agents ($$pin); bump them together"; exit 1; }; \
	$(MAKE) --no-print-directory _cut TAG="agent-pydantic-ai-v$$version" MSG="pydantic-ai agent $$version"


.PHONY: release-opencode
release-opencode: _release-guard
	@version=$$(node -p 'require("./agents/avp-opencode/typescript/package.json").version'); \
	pin=$$($(UV) run python -c "from avp_cli.agents import AGENT_SOURCES; print(AGENT_SOURCES['opencode'].container_version)"); \
	test "$$version" = "$$pin" || { echo "error: avp-opencode package.json version ($$version) != container_version pin in avp_cli.agents ($$pin); bump them together"; exit 1; }; \
	$(MAKE) --no-print-directory _cut TAG="agent-opencode-v$$version" MSG="opencode agent $$version"


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


# Build both agents' local artifacts into dist/agents, then print the
# `avp agent install --as <name>-dev` commands to register them as local builds.
# This is the contributor loop for testing a new agent build before cutting a
# GitHub release: build here, install under a -dev name, run an eval against it. (The goose build needs the Rust
# toolchain + Goose's system deps; the wheels need uv.)
.PHONY: build-agents
build-agents:
	@rm -rf dist/agents && mkdir -p dist/agents
	@echo "→ building goose binary (cargo, --features conformance)..."
	@cd agents/avp-goose/rust && cargo build --release --features conformance --bin avp-goose-conformance
	@cp agents/avp-goose/rust/target/release/avp-goose-conformance dist/agents/
	@echo "→ building claude-code wheels (agent-voyager-project + avp-conformance + agent)..."
	@$(UV) build --package agent-voyager-project --out-dir dist/agents
	@$(UV) build --package avp-conformance --out-dir dist/agents
	@$(UV) build --package avp-claude-agent-sdk --out-dir dist/agents
	@echo "→ building codex + openai-agents wheels..."
	@$(UV) build --package avp-codex --out-dir dist/agents
	@$(UV) build --package avp-openai-agents --out-dir dist/agents
	@echo "→ packaging the pi archive (npm; Node >= 22.19)..."
	@agents/avp-pi/typescript/scripts/package.sh $(CURDIR)/dist/agents
	@echo "→ packaging the gemini-cli archive (npm; Node >= 22.19)..."
	@agents/avp-gemini-cli/typescript/scripts/package.sh $(CURDIR)/dist/agents
	@echo "→ building deep-agents wheel..."
	@$(UV) build --package avp-deep-agents --out-dir dist/agents
	@echo "→ building pydantic-ai wheel..."
	@$(UV) build --package avp-pydantic-ai --out-dir dist/agents
	@echo "→ packaging the opencode archives (npm; one per platform)..."
	@agents/avp-opencode/typescript/scripts/package.sh $(CURDIR)/dist/agents
	@echo ""
	@echo "✓ built into dist/agents. Install each as a local build (add --force to replace one):"
	@echo "  uv run avp agent install goose --as goose-dev --binary <a Linux build of avp-goose-conformance>"
	@echo "  uv run avp agent install claude-code --as claude-code-dev \\"
	@echo "    --wheel dist/agents/agent_voyager_project-*.whl \\"
	@echo "    --wheel dist/agents/avp_conformance-*.whl \\"
	@echo "    --wheel dist/agents/avp_claude_agent_sdk-*.whl"
	@echo "  uv run avp agent install codex --as codex-dev \\"
	@echo "    --wheel dist/agents/agent_voyager_project-*.whl --wheel dist/agents/avp_codex-*.whl"
	@echo "  uv run avp agent install openai-agents --as openai-agents-dev \\"
	@echo "    --wheel dist/agents/agent_voyager_project-*.whl --wheel dist/agents/avp_openai_agents-*.whl"
	@echo "  uv run avp agent install pi --as pi-dev --package dist/agents/avp-pi.tar.gz"
	@echo "  uv run avp agent install gemini-cli --as gemini-cli-dev --package dist/agents/avp-gemini-cli.tar.gz"
	@echo "  uv run avp agent install deep-agents --as deep-agents-dev \\"
	@echo "    --wheel dist/agents/agent_voyager_project-*.whl --wheel dist/agents/avp_deep_agents-*.whl"
	@echo "  uv run avp agent install pydantic-ai --as pydantic-ai-dev \\"
	@echo "    --wheel dist/agents/agent_voyager_project-*.whl --wheel dist/agents/avp_pydantic_ai-*.whl"
	@echo "  uv run avp agent install opencode --as opencode-dev --package dist/agents/avp-opencode-linux-<arch>.tar.gz"
	@echo "Runs use these builds inside the Linux sandbox, so the goose binary and the"
	@echo "opencode archive must be Linux builds; the wheels and other archives work as is."


# Default goal
.DEFAULT_GOAL := help
