# AVP: orchestration commands for the multi-language repo.
#
# Default target prints help. Use `make smoke` for the full $$ sanity check
# you want before tagging a release.
#
# The Python workspace lives under python/ (its own pyproject.toml + ruff.toml
# + uv.lock); this Makefile invokes uv via `uv --directory python` so the repo
# root stays language-agnostic.
#
# Cost notes: targets that hit a real LLM are clearly marked. The default
# `make smoke` runs the entire matrix (all real-LLM tests + all examples)
# and currently costs roughly $0.10 to $0.20 on Haiku. The free checks
# (`make check`) cover format / lint / unit tests / conformance.

SHELL := /usr/bin/env bash

# All uv calls route through python/ so the repo root has no Python config.
UV := uv --directory python

# Each package has its own pyproject.toml + tests/ directory. Pytest's
# importer collides if invoked at the repo root because every package
# uses the same `tests` dirname, so we iterate per-package.
TEST_PKGS := \
	python/avp \
	python/sdks/avp-anthropic \
	python/agents/avp-claude-agent \
	python/agents/avp-openai-agent \
	python/supervisors/simple-supervisor-example

# Examples, sorted by provider so a single-provider smoke run is
# obvious from the file layout (01-07 Anthropic / Claude Code,
# 08+ OpenAI). Each script self-detects missing preflight (API key,
# SDK package, CLI binary) and exits 2; the run-an-example loop
# treats exit 2 as a skip rather than a failure, so a workstation
# with only one provider key set still completes the relevant
# subset cleanly.
EXAMPLES_ANTHROPIC := \
	python/supervisors/simple-supervisor-example/examples/01_anthropic_cost_bounded.py \
	python/supervisors/simple-supervisor-example/examples/03_claude_code_audited.py \
	python/supervisors/simple-supervisor-example/examples/05_anthropic_subagent_delegation.py \
	python/supervisors/simple-supervisor-example/examples/06_anthropic_traced_client.py \
	python/supervisors/simple-supervisor-example/examples/07_claude_agent_traced_client.py
EXAMPLES_OPENAI := \
	python/supervisors/simple-supervisor-example/examples/08_openai_agents_audited.py \
	python/supervisors/simple-supervisor-example/examples/09_openai_agents_traced_client.py
EXAMPLES := $(EXAMPLES_ANTHROPIC) $(EXAMPLES_OPENAI)

# Real-LLM test packages, grouped by which provider key they need.
# Each test file self-skips when its required key is missing, so the
# loop iterates the whole list and pytest does the gating.
REAL_LLM_PKGS_ANTHROPIC := \
	python/sdks/avp-anthropic \
	python/agents/avp-claude-agent
REAL_LLM_PKGS_OPENAI := \
	python/agents/avp-openai-agent
REAL_LLM_PKGS := $(REAL_LLM_PKGS_ANTHROPIC) $(REAL_LLM_PKGS_OPENAI)


.PHONY: help
help:
	@echo "AVP: orchestration commands"
	@echo ""
	@echo "  Free targets (no API calls):"
	@echo "    make test            pytest across every package, real-LLM excluded"
	@echo "    make conformance     avp-conformance run + validate + check-coverage"
	@echo "    make lint            ruff check"
	@echo "    make format          ruff format (writes)"
	@echo "    make format-check    ruff format --check (read-only)"
	@echo "    make schemas         regenerate JSON schemas from Pydantic models"
	@echo "    make bindings        regenerate Rust + TS bindings from schemas"
	@echo "    make bindings-check  drift detector (regen + git-diff against tracked)"
	@echo "    make bindings-test   cargo test (rust/avp) + npm test (typescript/avp)"
	@echo "    make check           format-check + lint + test + conformance + bindings-check"
	@echo ""
	@echo "  Paid targets (cost real money; require an API key for the targeted provider):"
	@echo "    make test-real-llm [anthropic|openai]   real-LLM smoke tests"
	@echo "    make examples      [anthropic|openai]   all examples (others self-skip)"
	@echo "    make smoke         [anthropic|openai]   full sanity matrix"
	@echo ""
	@echo "    The optional second word scopes the run to one provider; omit"
	@echo "    it for the full matrix. Examples:"
	@echo "      make smoke              # check + bindings-test + every provider"
	@echo "      make smoke anthropic    # check + bindings-test + Anthropic only"
	@echo "      make smoke openai       # check + bindings-test + OpenAI only"
	@echo ""
	@echo "  Other:"
	@echo "    make sync            uv sync the Python workspace at python/"


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


.PHONY: conformance
conformance:
	@$(UV) run avp-conformance validate
	@$(UV) run avp-conformance run
	@$(UV) run avp-conformance check-coverage


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
	@$(UV) run python ../scripts/generate-schemas.py


.PHONY: bindings
bindings:
	@bash scripts/generate-bindings.sh


.PHONY: bindings-check
bindings-check:
	@# Drift check: snapshot current bindings, regenerate, diff against
	@# the snapshot. Pure working-tree comparison; does NOT require the
	@# bindings to be committed. If regeneration changes any byte, the
	@# user's bindings are stale relative to types.py / schemas.
	@snapshot=$$(mktemp -d); \
	cp -R rust/avp/src "$$snapshot/rust-src"; \
	cp -R typescript/avp/src "$$snapshot/ts-src"; \
	bash scripts/generate-bindings.sh > /dev/null; \
	if ! diff -rq "$$snapshot/rust-src" rust/avp/src > /dev/null 2>&1 \
	   || ! diff -rq "$$snapshot/ts-src" typescript/avp/src > /dev/null 2>&1; then \
		echo "error: Rust/TS bindings are stale relative to schemas. Run 'make bindings'." >&2; \
		diff -rq "$$snapshot/rust-src" rust/avp/src 2>&1 | head -10 >&2 || true; \
		diff -rq "$$snapshot/ts-src" typescript/avp/src 2>&1 | head -10 >&2 || true; \
		rm -rf "$$snapshot"; \
		exit 1; \
	fi; \
	rm -rf "$$snapshot"; \
	echo "✓ Bindings in sync with schemas."


.PHONY: bindings-test
bindings-test:
	@cd rust/avp && cargo test --quiet
	@# node_modules/ and package-lock.json are gitignored, so a fresh
	@# clone has neither. Install on demand so `make smoke` works without
	@# a separate "npm install" step.
	@cd typescript/avp && { [ -d node_modules ] || npm install --silent; } && npm test --silent


.PHONY: check
check: format-check lint test conformance bindings-check
	@echo ""; echo "✓ All free checks passed."


# ── Paid targets (real LLM) ───────────────────────────────────────────────────
#
# Provider scoping: the paid targets accept an optional positional second
# word — `make smoke anthropic`, `make examples openai`, etc. The
# implementation reads MAKECMDGOALS and picks `anthropic` or `openai`
# from it (firstword wins, in case both appear). To prevent Make from
# erroring on the bare provider word as a goal it doesn't recognize, we
# declare `anthropic` and `openai` as no-op .PHONY targets.
#
# Smoke chains check + bindings-test + test-real-llm + examples by
# re-invoking $(MAKE) so each child sees the current PROVIDER value
# through MAKECMDGOALS. Direct dependencies wouldn't work because Make's
# command-line goals don't propagate across sub-makes.

PROVIDER := $(firstword $(filter anthropic openai,$(MAKECMDGOALS)))

.PHONY: anthropic openai
anthropic openai:
	@:


.PHONY: test-real-llm
test-real-llm:
	@case "$(PROVIDER)" in \
	  anthropic) \
	    if [ -z "$$ANTHROPIC_API_KEY" ]; then echo "error: ANTHROPIC_API_KEY not set"; exit 2; fi; \
	    pkgs="$(REAL_LLM_PKGS_ANTHROPIC)" ;; \
	  openai) \
	    if [ -z "$$OPENAI_API_KEY" ]; then echo "error: OPENAI_API_KEY not set"; exit 2; fi; \
	    pkgs="$(REAL_LLM_PKGS_OPENAI)" ;; \
	  *) \
	    if [ -z "$$ANTHROPIC_API_KEY" ] && [ -z "$$OPENAI_API_KEY" ]; then \
	      echo "error: neither ANTHROPIC_API_KEY nor OPENAI_API_KEY is set; real-LLM tests require at least one"; exit 2; \
	    fi; \
	    pkgs="$(REAL_LLM_PKGS)" ;; \
	esac; \
	failed=""; \
	for pkg in $$pkgs; do \
	  echo ""; echo "==== $$pkg (real-LLM) ===="; \
	  (cd $$pkg && uv run python -m pytest -m real_llm -q; e=$$?; [ $$e -eq 0 ] || [ $$e -eq 5 ]) || failed="$$failed $$pkg"; \
	done; \
	if [ -n "$$failed" ]; then echo ""; echo "FAILED packages:$$failed"; exit 1; fi; \
	echo ""; echo "All real-LLM tests passed."


# Common run-an-example macro. Distinguishes:
#   exit 0 → pass
#   exit 2 → preflight skip (missing API key / SDK / CLI); reported, not failed
#   anything else → fail
define run_examples
	@failed=""; skipped=""; \
	for ex in $(1); do \
		echo ""; echo "==== $$ex ===="; \
		$(UV) run python ../$$ex; \
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
	@case "$(PROVIDER)" in \
	  anthropic) \
	    if [ -z "$$ANTHROPIC_API_KEY" ]; then echo "error: ANTHROPIC_API_KEY not set"; exit 2; fi ;; \
	  openai) \
	    if [ -z "$$OPENAI_API_KEY" ]; then echo "error: OPENAI_API_KEY not set"; exit 2; fi ;; \
	  *) \
	    if [ -z "$$ANTHROPIC_API_KEY" ] && [ -z "$$OPENAI_API_KEY" ]; then \
	      echo "error: neither ANTHROPIC_API_KEY nor OPENAI_API_KEY is set"; exit 2; \
	    fi ;; \
	esac
ifeq ($(PROVIDER),anthropic)
	$(call run_examples,$(EXAMPLES_ANTHROPIC))
else ifeq ($(PROVIDER),openai)
	$(call run_examples,$(EXAMPLES_OPENAI))
else
	$(call run_examples,$(EXAMPLES))
endif


.PHONY: smoke
smoke:
	@$(MAKE) --no-print-directory check bindings-test
	@$(MAKE) --no-print-directory test-real-llm $(PROVIDER)
	@$(MAKE) --no-print-directory examples $(PROVIDER)
	@echo ""; echo "✓ smoke complete (provider=$(if $(PROVIDER),$(PROVIDER),all)): free checks + bindings tests + real-LLM tests + examples passed."


# ── Other ─────────────────────────────────────────────────────────────────────


.PHONY: sync
sync:
	@$(UV) sync


# Default goal
.DEFAULT_GOAL := help
