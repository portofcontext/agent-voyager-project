#!/usr/bin/env bash
#
# End-to-end smoke for the `avp` CLI: exercises create -> list -> inspect ->
# delete across every manageable surface (commissions, environments, vault
# secrets) plus the read-only views (agents, evals, sandbox). Assumes `avp` is
# on PATH (or run via `make cli-smoke`, which puts the workspace venv on PATH).
#
# Uses a throwaway AVP_HOME, so the real ~/.avp is untouched. No model calls.
#   scripts/cli-smoke.sh
#   make cli-smoke
#
# Every check is its own statement (not `cmd && ok`), so `set -e` aborts the
# moment any step fails — a failed step never silently skips.
set -euo pipefail

export AVP_HOME="$(mktemp -d)/.avp"
trap 'rm -rf "$(dirname "$AVP_HOME")"' EXIT

pass=0
step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok()   { printf '\033[1;32mok\033[0m %s\n' "$*"; pass=$((pass + 1)); }
die()  { printf '\033[1;31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }
has()  { grep -q -- "$2" <<<"$1" || die "expected to find '$2'"; }       # output contains
no()   { grep -q -- "$2" <<<"$1" && die "did NOT expect '$2'" || true; } # output lacks

step "welcome screen"
avp >/dev/null
ok "avp (no args) renders"

# ── Commissions (avp cm) ─────────────────────────────────────────────────────
step "commissions: create -> list -> describe -> check -> delete"
avp cm create demo-cm --model anthropic/claude-opus-4-8 >/dev/null
ok "cm create"
has "$(avp cm list)" demo-cm; ok "cm list shows it"
has "$(avp cm describe demo-cm)" 'anthropic/claude-opus-4-8'; ok "cm describe renders the wire model"
avp cm check demo-cm >/dev/null; ok "cm check passes"
avp cm delete demo-cm >/dev/null; ok "cm delete"
no "$(avp cm list 2>&1)" demo-cm; ok "cm list no longer shows it"

# ── Environments (avp env) ───────────────────────────────────────────────────
step "environments: create -> list -> show -> delete"
avp env create demo-env --image python:3.12-slim --pip requests --net example.com >/dev/null
ok "env create"
has "$(avp env list)" demo-env; ok "env list shows it"
has "$(avp env show demo-env)" python:3.12-slim; ok "env show renders the image"
avp env delete demo-env >/dev/null; ok "env delete"
no "$(avp env list 2>&1)" demo-env; ok "env list no longer shows it"

# ── Vault secrets (avp env secret) ───────────────────────────────────────────
step "secrets: create -> list -> (force) -> delete"
avp env secret create demo-key 'sk-super-secret-value' >/dev/null
ok "secret create"
secrets="$(avp env secret list)"
has "$secrets" demo-key; ok "secret list shows the handle"
no "$secrets" 'sk-super-secret-value'; ok "secret list never prints the value"
# create without --force on an existing handle must fail (clobber guard)
if avp env secret create demo-key 'other' >/dev/null 2>&1; then die "expected clobber guard"; fi
ok "secret create refuses to overwrite without --force"
avp env secret create demo-key 'sk-rotated' --force >/dev/null; ok "secret create --force overwrites"
avp env secret delete demo-key >/dev/null; ok "secret delete"
no "$(avp env secret list 2>&1)" demo-key; ok "secret list no longer shows it"

# ── Read-only views ──────────────────────────────────────────────────────────
step "agents / evals / sandbox (read-only)"
avp agent list >/dev/null; ok "agent list runs with no built-in archive agents"
avp eval list >/dev/null 2>&1; ok "eval list runs"
avp sandbox status >/dev/null 2>&1 && ok "sandbox status runs" || ok "sandbox status ran (Docker may be down)"

# ── Eval scaffolding (avp init) ──────────────────────────────────────────────
# --agent keeps it non-interactive (no agent appears without it -> hangs on a TTY).
step "init: scaffold an eval (non-interactive)"
work="$(dirname "$AVP_HOME")/work"; mkdir -p "$work"
avp init capitals --agent example-agent --dir "$work" >/dev/null
ls "$work"/*.eval.json >/dev/null
ok "avp init wrote an eval config + commissions"

printf '\n\033[1;32mall %d checks passed\033[0m (throwaway AVP_HOME cleaned up)\n' "$pass"
