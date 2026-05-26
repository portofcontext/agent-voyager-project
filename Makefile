# AVP: orchestration commands for the multi-language repo.
#
# Default target prints help. Use `make smoke` for the full $$ sanity check
# you want before tagging a release.
#
# Layout: the core project (spec, conformance, Python/Rust/TS bindings) lives
# under avp/; agents under agents/<name>/<lang>/; SDK adapters under sdks/;
# supervisor examples under supervisors/. The uv (Python) workspace is rooted
# at the repo root (root pyproject.toml + ruff.toml + uv.lock), so `uv` runs
# from here and spans every Python member.
#
# Cost notes: targets that hit a real LLM are clearly marked. The default
# `make smoke` runs the entire matrix (all real-LLM tests + all examples)
# and currently costs roughly $0.10 to $0.20 on Haiku. The free checks
# (`make check`) cover format / lint / unit tests / conformance.

SHELL := /usr/bin/env bash

# The uv workspace is rooted at the repo root; run uv from here.
UV := uv

# Each package has its own pyproject.toml + tests/ directory. Pytest's
# importer collides if invoked at the repo root because every package
# uses the same `tests` dirname, so we iterate per-package.
TEST_PKGS := \
	avp/bindings/python \
	avp/core/conformance \
	sdks/avp-anthropic \
	agents/avp-claude-agent-sdk/python \
	supervisors/simple-supervisor-example

# All examples. Each script self-detects missing preflight (API key,
# claude_agent_sdk, the `claude` CLI) and exits 2. The run-an-example
# loop treats exit 2 as a skip rather than a failure, so a run on a
# workstation without the Claude Code CLI still completes the Anthropic-
# only examples cleanly.
EXAMPLES := \
	supervisors/simple-supervisor-example/examples/01_anthropic_cost_bounded.py \
	supervisors/simple-supervisor-example/examples/03_claude_code_audited.py \
	supervisors/simple-supervisor-example/examples/05_anthropic_subagent_delegation.py \
	supervisors/simple-supervisor-example/examples/06_anthropic_traced_client.py \
	supervisors/simple-supervisor-example/examples/07_claude_agent_traced_client.py


.PHONY: help
help:
	@echo "AVP: orchestration commands"
	@echo ""
	@echo "  Free targets (no API calls):"
	@echo "    make test            pytest across every package, real-LLM excluded"
	@echo "    make conformance     avp-conformance validate + ping (free; no model)"
	@echo "    make lint            ruff check"
	@echo "    make format          ruff format (writes)"
	@echo "    make format-check    ruff format --check (read-only)"
	@echo "    make schemas         regenerate JSON schemas from Pydantic models"
	@echo "    make sync-prices     refresh bundled prices.json from models.dev (--write)"
	@echo "    make bindings        regenerate Rust + TS bindings from schemas"
	@echo "    make bindings-check  drift detector (regen + git-diff against tracked)"
	@echo "    make bindings-test   cargo test (avp/bindings/rust) + npm test (avp/bindings/typescript)"
	@echo "    make check           format-check + lint + test + conformance + bindings-check"
	@echo ""
	@echo "  Paid targets (cost real money; require ANTHROPIC_API_KEY):"
	@echo "    make conformance-check  run the v0.1 suite against both agents on a real model"
	@echo "    make test-real-llm      real-LLM smoke tests for both agents"
	@echo "    make test-live          gated avp-goose live tests (mcp_connect / live_mcp /"
	@echo "                            live_skills; spawn the uv server + call a real model). Needs uv."
	@echo "    make examples           all 5 examples (03 / 07 self-skip without \`claude\` CLI)"
	@echo "    make smoke              check + bindings-test + test-real-llm + conformance-check + examples"
	@echo ""
	@echo "  Other:"
	@echo "    make sync            uv sync the Python workspace (repo root)"


# ── Free targets ──────────────────────────────────────────────────────────────


.PHONY: test
test:
	@failed=""; \
	for pkg in $(TEST_PKGS); do \
		echo "==== $$pkg (test) ===="; \
		(cd $$pkg && uv run python -m pytest -m "not real_llm" -q; e=$$?; [ $$e -eq 0 ] || [ $$e -eq 5 ]) || failed="$$failed $$pkg"; \
	done; \
	if [ -n "$$failed" ]; then echo ""; echo "FAILED packages:$$failed"; exit 1; fi; \
	echo ""; echo "All package tests passed."


# Manifest paths, relative to the repo root the harness runs from.
CLAUDE_MANIFEST := agents/avp-claude-agent-sdk/python/avp-conformance.json
GOOSE_MANIFEST  := agents/avp-goose/rust/avp-conformance.json

# Set SANDBOX=--sandbox to run each agent inside the `srt` sandbox
# (@anthropic-ai/sandbox-runtime). Off by default so `conformance-check` works
# on machines without srt installed; on for any untrusted / CI run.
SANDBOX ?=


# ── Free: validate case files + liveness-ping each agent (no model calls) ──────
.PHONY: claude-ping goose-ping
claude-ping:
	@$(UV) run avp-conformance ping --agent $(CLAUDE_MANIFEST)

goose-ping:
	@$(UV) run avp-conformance ping --agent $(GOOSE_MANIFEST)


.PHONY: conformance
conformance:
	@$(UV) run avp-conformance validate
	@printf "\n\033[1;36m── avp-claude-agent-sdk ──\033[0m\n"
	@$(MAKE) --no-print-directory claude-ping
	@printf "\n\033[1;36m── avp-goose ──\033[0m\n"
	@$(MAKE) --no-print-directory goose-ping


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

.PHONY: sync-prices-check
sync-prices-check:
	@$(UV) run python avp/scripts/sync-prices.py --check


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
	for pkg in sdks/avp-anthropic agents/avp-claude-agent-sdk/python; do \
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


# Common run-an-example macro. Distinguishes:
#   exit 0 → pass
#   exit 2 → preflight skip (missing API key / SDK / CLI); we report it but don't fail
#   anything else → fail
define run_examples
	@failed=""; skipped=""; \
	for ex in $(1); do \
		echo ""; echo "==== $$ex ===="; \
		$(UV) run python $$ex; \
		rc=$$?; \
		case $$rc in \
			0) ;; \
			2) skipped="$$skipped $$ex" ;; \
			*) failed="$$failed $$ex" ;; \
		esac; \
	done; \
	echo ""; \
	if [ -n "$$skipped" ]; then echo "SKIPPED (preflight):$$skipped"; fi; \
	if [ -n "$$failed" ]; then echo "FAILED:$$failed"; exit 1; fi; \
	echo "All non-skipped examples passed."
endef


.PHONY: examples
examples:
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "error: ANTHROPIC_API_KEY is not set"; exit 2; \
	fi
	$(call run_examples,$(EXAMPLES))


.PHONY: smoke
smoke: check bindings-test test-real-llm conformance-check examples
	@echo ""; echo "✓ smoke complete: free checks + bindings tests + real-LLM tests + conformance suite + all examples passed."


# ── Other ─────────────────────────────────────────────────────────────────────


.PHONY: sync
sync:
	@$(UV) sync


# Default goal
.DEFAULT_GOAL := help
