# AVP — orchestration commands for the workspace.
#
# Default target prints help. Use `make smoke` for the full $$ sanity check
# you want before tagging a release.
#
# Cost notes: targets that hit a real LLM are clearly marked. The default
# `make smoke` runs the entire matrix (all real-LLM tests + all examples)
# and currently costs roughly $0.10–0.20 on Haiku. The free checks
# (`make check`) cover format / lint / unit tests / conformance.

SHELL := /usr/bin/env bash

# Each package has its own pyproject.toml + tests/ directory. Pytest's
# importer collides if invoked at the repo root because every package
# uses the same `tests` dirname, so we iterate per-package.
TEST_PKGS := \
	python/avp \
	python/agents/avp-anthropic \
	python/agents/avp-claude-agent \
	python/supervisors/simple-supervisor-example

# All examples. Each script self-detects missing preflight (API key,
# claude_agent_sdk, the `claude` CLI) and exits 2 — the run-an-example
# loop treats exit 2 as a skip rather than a failure, so a run on a
# workstation without the Claude Code CLI still completes the Anthropic-
# only examples cleanly.
EXAMPLES := \
	python/supervisors/simple-supervisor-example/examples/01_anthropic_cost_bounded.py \
	python/supervisors/simple-supervisor-example/examples/02_anthropic_self_correcting.py \
	python/supervisors/simple-supervisor-example/examples/03_claude_code_audited.py \
	python/supervisors/simple-supervisor-example/examples/04_ddd_supervisor.py \
	python/supervisors/simple-supervisor-example/examples/05_anthropic_subagent_delegation.py \
	python/supervisors/simple-supervisor-example/examples/06_anthropic_traced_client.py \
	python/supervisors/simple-supervisor-example/examples/07_claude_agent_traced_client.py


.PHONY: help
help:
	@echo "AVP — orchestration commands"
	@echo ""
	@echo "  Free targets (no API calls):"
	@echo "    make test            — pytest across every package, real-LLM excluded"
	@echo "    make conformance     — avp-conformance run + validate + check-coverage"
	@echo "    make lint            — ruff check"
	@echo "    make format          — ruff format (writes)"
	@echo "    make format-check    — ruff format --check (read-only)"
	@echo "    make schemas         — regenerate JSON schemas from Pydantic models"
	@echo "    make bindings        — regenerate Rust + TS bindings from schemas"
	@echo "    make bindings-check  — drift detector (regen + git-diff against tracked)"
	@echo "    make bindings-test   — cargo test (rust/avp) + npm test (typescript/avp)"
	@echo "    make check           — format-check + lint + test + conformance + bindings-check"
	@echo ""
	@echo "  Paid targets (cost real money; require ANTHROPIC_API_KEY):"
	@echo "    make test-real-llm   — real-LLM smoke tests for both runners"
	@echo "    make examples        — all 7 examples (03 / 07 self-skip without \`claude\` CLI)"
	@echo "    make smoke           — check + bindings-test + test-real-llm + examples (full sanity)"
	@echo ""
	@echo "  Other:"
	@echo "    make sync            — uv sync the workspace"


# ── Free targets ──────────────────────────────────────────────────────────────


.PHONY: test
test:
	@failed=""; \
	for pkg in $(TEST_PKGS); do \
		echo "==== $$pkg (test) ===="; \
		(cd $$pkg && uv run pytest -m "not real_llm" -q) || failed="$$failed $$pkg"; \
	done; \
	if [ -n "$$failed" ]; then echo ""; echo "FAILED packages:$$failed"; exit 1; fi; \
	echo ""; echo "All package tests passed."


.PHONY: conformance
conformance:
	@uv run avp-conformance validate
	@uv run avp-conformance run
	@uv run avp-conformance check-coverage


.PHONY: lint
lint:
	@uv run ruff check python


.PHONY: format
format:
	@uv run ruff format python
	@uv run ruff check --fix python


.PHONY: format-check
format-check:
	@uv run ruff format --check python
	@uv run ruff check python


.PHONY: schemas
schemas:
	@uv run python scripts/generate-schemas.py


.PHONY: bindings
bindings:
	@bash scripts/generate-bindings.sh


.PHONY: bindings-check
bindings-check:
	@# Drift check: regenerate Rust + TS bindings; fail if any tracked file
	@# has changed. Catches the case where types.py / schemas changed but
	@# generated code wasn't regen'd. Untracked files (e.g. brand-new
	@# binding files awaiting their first commit) DON'T count as drift —
	@# they need to be `git add`'d and committed normally.
	@bash scripts/generate-bindings.sh > /dev/null
	@if ! git diff --quiet -- rust/avp/src typescript/avp/src 2>/dev/null; then \
		echo "error: Rust/TS bindings drifted from schemas. Run 'make bindings' and commit." >&2; \
		git diff --stat -- rust/avp/src typescript/avp/src >&2; \
		exit 1; \
	fi
	@echo "✓ Bindings in sync with schemas."


.PHONY: bindings-test
bindings-test:
	@cd rust/avp && cargo test --quiet
	@cd typescript/avp && npm test --silent


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
	for pkg in python/agents/avp-anthropic python/agents/avp-claude-agent; do \
		echo ""; echo "==== $$pkg (real-LLM) ===="; \
		(cd $$pkg && uv run pytest -m real_llm -q) || failed="$$failed $$pkg"; \
	done; \
	if [ -n "$$failed" ]; then echo ""; echo "FAILED packages:$$failed"; exit 1; fi; \
	echo ""; echo "All real-LLM tests passed."


# Common run-an-example macro. Distinguishes:
#   exit 0 → pass
#   exit 2 → preflight skip (missing API key / SDK / CLI) — we report it but don't fail
#   anything else → fail
define run_examples
	@failed=""; skipped=""; \
	for ex in $(1); do \
		echo ""; echo "==== $$ex ===="; \
		uv run python $$ex; \
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
smoke: check bindings-test test-real-llm examples
	@echo ""; echo "✓ smoke complete — free checks + bindings tests + real-LLM tests + all examples passed."


# ── Other ─────────────────────────────────────────────────────────────────────


.PHONY: sync
sync:
	@uv sync


# Default goal
.DEFAULT_GOAL := help
