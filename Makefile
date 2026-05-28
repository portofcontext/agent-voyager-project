# AVP: orchestration commands for the multi-language repo.
#
# Default target prints help. Use `make smoke` for the full $$ sanity check
# you want before tagging a release.
#
# Layout: the core project (spec, conformance, Python/Rust/TS bindings) lives
# under avp/; agents under agents/<name>/<lang>/; the local CLI `avp` under
# avp-cli/. The uv (Python) workspace is rooted at the repo root (root
# pyproject.toml + ruff.toml + uv.lock), so `uv` runs from here and spans every
# Python member.
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
	agents/avp-claude-agent-sdk/python \
	avp-cli



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
	@echo "    make examples           scaffold + run the demo eval end-to-end (self-skips without an agent CLI)"
	@echo "    make smoke              check + bindings-test + test-real-llm + conformance-check + examples"
	@echo ""
	@echo "  Other:"
	@echo "    make sync            uv sync the Python workspace (repo root)"
	@echo "    make avp <args>      run the local avp CLI (e.g. make avp eval list); flags via ARGS=\"...\""


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


# The example is the CLI: scaffold the bundled demo eval (`avp init demo`) and
# run it end-to-end against a real agent, printing the ranked board. Exit codes:
#   exit 0 → pass
#   exit 2 → preflight skip (no agent toolchain present); reported, not a failure
#   anything else → fail
.PHONY: examples
examples:
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "error: ANTHROPIC_API_KEY is not set"; exit 2; \
	fi
	@tmp=$$(mktemp -d); \
	$(UV) run avp init demo --dir $$tmp --agent goose >/dev/null; \
	echo ""; echo "==== avp eval run (demo) ===="; \
	$(UV) run avp eval run $$tmp/demo.eval.json; rc=$$?; echo ""; \
	case $$rc in \
		0) echo "✓ example passed: demo eval" ;; \
		2) echo "SKIPPED (preflight): demo eval" ;; \
		*) echo "FAILED: demo eval"; exit 1 ;; \
	esac


.PHONY: smoke
smoke: check bindings-test test-real-llm conformance-check examples
	@echo ""; echo "✓ smoke complete: free checks + bindings tests + real-LLM tests + conformance suite + all examples passed."


# ── Other ─────────────────────────────────────────────────────────────────────


.PHONY: sync
sync:
	@$(UV) sync


# ── Local CLI passthrough ─────────────────────────────────────────────────────
# `make avp <args>` forwards to `uv run avp <args>`:
#   make avp                         # the welcome / agent routing
#   make avp init
#   make avp eval list
#   make avp commission validate avp/core/spec/v0.1/examples/commission.json
# make consumes leading-dash flags itself, so pass those via ARGS:
#   make avp ARGS="eval run my_eval.py --agent goose --json out.json"
.PHONY: avp
avp:
	@$(UV) run avp $(filter-out avp,$(MAKECMDGOALS)) $(ARGS)

# Let bare subcommand words (init, eval, ...) and path args be goals without a
# rule. The recipe is a no-op; `avp` above collects them via MAKECMDGOALS. Only
# matches goals that have no explicit rule, so real targets are unaffected.
%:
	@:


# Default goal
.DEFAULT_GOAL := help
