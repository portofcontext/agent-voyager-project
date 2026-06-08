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
	avp-cli



.PHONY: help
help:
	@echo "AVP: orchestration commands"
	@echo ""
	@echo "  Free targets (no API calls):"
	@echo "    make test            pytest across every package, real-LLM + docker excluded"
	@echo "    make test-docker     real-sandbox seam tests (free; needs a Docker daemon)"
	@echo "    make conformance     avp-conformance validate + ping (free; no model)"
	@echo "    make lint            ruff check"
	@echo "    make format          ruff format (writes)"
	@echo "    make format-check    ruff format --check (read-only)"
	@echo "    make schemas         regenerate JSON schemas from Pydantic models"
	@echo "    make sync-prices     refresh bundled prices.json from models.dev (--write)"
	@echo "    make bindings        regenerate language bindings from Pydantic schemas"
	@echo "    make bindings-check  drift detector (regen + git-diff against tracked)"
	@echo "    make bindings-test   cargo test (avp/bindings/rust) + npm test (avp/bindings/typescript)"
	@echo "    make check           format-check + lint + test + conformance + bindings-check"
	@echo ""
	@echo "  Paid targets (cost real money; require ANTHROPIC_API_KEY):"
	@echo "    make conformance-check  run the v0.1 suite against both agents on a real model"
	@echo "    make test-real-llm      real-LLM smoke tests for both agents"
	@echo "    make test-live          gated avp-goose live tests (mcp_connect / live_mcp /"
	@echo "                            live_skills; spawn the uv server + call a real model). Needs uv."
	@echo ""
	@echo "  Other:"
	@echo "    make sync            uv sync the Python workspace (repo root)"
	@echo "    make build-agents    build both agents' artifacts into dist/agents for local install"
	@echo "    make onboarding-smoke  run the README Quickstart in a clean container (AGENT=goose|claude-code|all, PAID=1)"
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


# The real-sandbox seam tests: a managed OpenSandbox server over the local
# Docker daemon, a stock-image sandbox, the run contract + trajectory bind-mount
# round trip, and egress-deny enforcement. Free (no model), needs Docker.
# Egress enforcement is REQUIRED here (the strict local gate); in CI the same
# test skips when the runner's kernel can't support the sidecar's hooks.
.PHONY: test-docker
test-docker:
	@cd avp-cli && AVP_REQUIRE_EGRESS_ENFORCEMENT=1 uv run python -m pytest tests/test_docker_seam.py -m docker -v


# Manifest paths, relative to the repo root the harness runs from.
CLAUDE_MANIFEST := agents/avp-claude-agent-sdk/python/avp-conformance.json
GOOSE_MANIFEST  := agents/avp-goose/rust/avp-conformance.json

# Set SANDBOX=--sandbox to run each agent inside the `srt` sandbox
# (@anthropic-ai/sandbox-runtime). Off by default so `conformance-check` works
# on machines without srt installed; on for any untrusted / CI run.
SANDBOX ?=


# ── Free: validate case files + liveness-ping + describe each agent (no model) ─
.PHONY: claude-ping goose-ping claude-describe goose-describe
claude-ping:
	@$(UV) run avp-conformance ping --agent $(CLAUDE_MANIFEST)

goose-ping:
	@$(UV) run avp-conformance ping --agent $(GOOSE_MANIFEST)

claude-describe:
	@$(UV) run avp-conformance describe --agent $(CLAUDE_MANIFEST)

goose-describe:
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


# ── Paid: run the v0.1 suite against each agent on a real model ────────────────
.PHONY: claude-check goose-check
claude-check:
	@$(UV) run avp-conformance check --agent $(CLAUDE_MANIFEST) --suite v0.1 $(SANDBOX)

goose-check:
	@$(UV) run avp-conformance check --agent $(GOOSE_MANIFEST) --suite v0.1 $(SANDBOX)


.PHONY: conformance-check
conformance-check:
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "error: ANTHROPIC_API_KEY is not set; conformance-check runs cases on a real model"; exit 2; \
	fi
	@printf "\n\033[1;36m── avp-claude-agent-sdk ──\033[0m\n"
	@$(MAKE) --no-print-directory claude-check
	@printf "\n\033[1;36m── avp-goose ──\033[0m\n"
	@$(MAKE) --no-print-directory goose-check


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
check: format-check lint test conformance bindings-check
	@echo ""; echo "✓ All free checks passed."


# ── Paid targets (real LLM) ───────────────────────────────────────────────────


.PHONY: test-real-llm
test-real-llm:
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "error: ANTHROPIC_API_KEY is not set; real-LLM tests require it"; exit 2; \
	fi
	@failed=""; \
	for pkg in agents/avp-claude-agent-sdk/python; do \
		echo ""; echo "==== $$pkg (real-LLM) ===="; \
		(cd $$pkg && uv run python -m pytest -m real_llm -q; e=$$?; [ $$e -eq 0 ] || [ $$e -eq 5 ]) || failed="$$failed $$pkg"; \
	done; \
	if [ -n "$$failed" ]; then echo ""; echo "FAILED packages:$$failed"; exit 1; fi; \
	echo ""; echo "All real-LLM tests passed."


.PHONY: test-live
test-live:
	@command -v uv >/dev/null 2>&1 || { echo "error: uv is required (the bundled MCP server runs via uv run)"; exit 2; }
	@echo "Running gated avp-goose live tests (mcp_connect is key-free; live_mcp / live_skills / live_subagent call a real model)."
	@cd agents/avp-goose/rust && cargo test --test mcp_connect --test live_mcp --test live_skills --test live_subagent -- --ignored


# ── Other ─────────────────────────────────────────────────────────────────────


.PHONY: sync
sync:
	@$(UV) sync


# Clean-room onboarding test: run the README Quickstart for AGENT (default goose)
# inside a fresh container, shipping the WORKING TREE in so it catches regressions
# before they're pushed. Free by default (stops at `describe`); set PAID=1 (needs
# ANTHROPIC_API_KEY) to also run a real eval.
#   make onboarding-smoke
#   make onboarding-smoke AGENT=claude-code
#   make onboarding-smoke PAID=1
.PHONY: onboarding-smoke
onboarding-smoke:
	@AVP_SMOKE_PAID=$(if $(filter 1,$(PAID)),1,0) bash scripts/onboarding-smoke.sh $(if $(AGENT),$(AGENT),goose)


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
# `avp agent install` commands to register them. This is the contributor loop
# for testing a new agent build before cutting a GitHub release: build here,
# install locally, run an eval against it. (The goose build needs the Rust
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
	@echo ""
	@echo "✓ built into dist/agents. Install locally (add --force to replace an install):"
	@echo "  uv run avp agent install goose --binary dist/agents/avp-goose-conformance"
	@echo "  uv run avp agent install claude-code \\"
	@echo "    --wheel dist/agents/agent_voyager_project-*.whl \\"
	@echo "    --wheel dist/agents/avp_conformance-*.whl \\"
	@echo "    --wheel dist/agents/avp_claude_agent_sdk-*.whl"


# Default goal
.DEFAULT_GOAL := help
