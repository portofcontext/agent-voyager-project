#!/usr/bin/env bash
#
# End-to-end smoke for the `avp` CLI: exercises create -> list -> inspect ->
# delete across every manageable surface (commissions, environments, vault
# secrets) plus the read-only views (agents, evals, sandbox). Assumes `avp` is
# on PATH (or run via `make cli-smoke`, which puts the workspace venv on PATH).
#
# The free path runs against a throwaway AVP_HOME, so your real ~/.avp is
# untouched. With AVP_SMOKE_PAID=1 it adds the grand finale: a CLI-created vault
# secret + environment + commission, run for real in a sandbox where the
# credential broker injects the secret the agent never sees. The finale reaches
# into your REAL ~/.avp on purpose (the OpenSandbox server is a shared singleton,
# keyed by its config and only allowed to bind-mount under the home it was
# started with — a throwaway home would mismatch its key + allowed paths). It
# names everything fin-* and deletes it in a trap, leaves goose installed only if
# you already had it, and writes one eval run under ~/.avp/runs.
#
#   scripts/cli-smoke.sh                                       # free: CRUD + read-only views
#   AVP_SMOKE_PAID=1 OPENROUTER_API_KEY=sk-or-... scripts/cli-smoke.sh   # + the grand finale
#   make cli-smoke                                             # free, via the venv
#   make cli-smoke PAID=1                                      # finale (needs OPENROUTER_API_KEY)
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
avp cm create demo-cm --model anthropic/claude-opus-4-8 --prompt '{input}' >/dev/null
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
has "$(avp agent list)" goose; ok "agent list shows goose"
avp eval list >/dev/null 2>&1; ok "eval list runs"
avp sandbox status >/dev/null 2>&1 && ok "sandbox status runs" || ok "sandbox status ran (Docker may be down)"

# ── Eval scaffolding (avp init) ──────────────────────────────────────────────
# --agent keeps it non-interactive (no agent appears without it -> hangs on a TTY).
step "init: scaffold an eval (non-interactive)"
work="$(dirname "$AVP_HOME")/work"; mkdir -p "$work"
avp init capitals --agent goose --dir "$work" >/dev/null
ls "$work"/*.eval.json >/dev/null
ok "avp init wrote an eval config + commissions"

# ── Paid grand finale: the whole chain, end to end (opt-in) ──────────────────
# Everything together: a CLI-created vault secret + environment + commission, run
# for real in a sandbox where the credential broker injects the secret the agent
# never sees. Uses goose + OpenRouter (model "openai/gpt-4o" — its slug is
# OpenRouter's own model id, so it needs no slug-split). The run converging is
# itself the proof the vault worked: the sandbox holds only a sentinel, so the
# call can only succeed if the broker injected the real key.
if [[ "${AVP_SMOKE_PAID:-0}" == "1" ]]; then
  step "PAID FINALE: secret + env + commission -> broker-injected sandboxed run (Docker + OPENROUTER_API_KEY)"
  [[ -n "${OPENROUTER_API_KEY:-}" ]] || die "set OPENROUTER_API_KEY (the value stored in the vault)"
  REAL="$HOME/.avp"; R=(env "AVP_HOME=$REAL" avp)   # invoke avp against the real home
  had_goose=0; [[ -f "$REAL/agents/goose/avp-conformance.json" ]] && had_goose=1

  # Clean up every fin-* resource we add to the real library, whatever happens.
  cleanup_finale() {
    "${R[@]}" cm delete fin-cm >/dev/null 2>&1 || true
    "${R[@]}" env delete fin-env >/dev/null 2>&1 || true
    "${R[@]}" env secret delete fin-key >/dev/null 2>&1 || true
    [[ $had_goose -eq 0 ]] && "${R[@]}" agent uninstall goose >/dev/null 2>&1 || true
  }
  trap 'cleanup_finale; rm -rf "$(dirname "$AVP_HOME")"' EXIT

  "${R[@]}" env secret create fin-key "$OPENROUTER_API_KEY" --force >/dev/null
  ok "secret create fin-key (the real OpenRouter key, stored host-side)"
  "${R[@]}" env create fin-env --image python:3.12-slim --force >/dev/null
  ok "env create fin-env"
  "${R[@]}" cm create fin-cm --force --model openai/gpt-4o \
    --provider-id openrouter --provider-base-url https://openrouter.ai/api/v1 \
    --credential fin-key --prompt '{input}' >/dev/null
  ok "cm create fin-cm (references the vault secret by handle)"
  has "$("${R[@]}" cm describe fin-cm)" '"vault": "fin-key"'
  ok "commission carries the handle, not the value"

  [[ $had_goose -eq 1 ]] || { "${R[@]}" agent install goose >/dev/null; ok "agent install goose"; }

  cat >"$work/finale.eval.json" <<'JSON'
{
  "name": "vault-finale",
  "agents": ["goose"],
  "dataset": {"source": "inline", "items": [
    {"id": "ping", "prompt": "Reply with exactly the word PONG and nothing else.", "expected": "PONG"}
  ]},
  "scorer": {"name": "exact-match"},
  "commissions": ["fin-cm"]
}
JSON
  "${R[@]}" eval run "$work/finale.eval.json" --env fin-env --name vault-finale \
    --json "$work/board.json" --timeout 600 >/dev/null
  # eval run exits 0 even when cells error, so assert the board has zero errors:
  # a converged run with only a sentinel in-sandbox proves the broker injected.
  python3 - "$work/board.json" <<'PY'
import json, sys
b = json.load(open(sys.argv[1]))
rows = b.get("commissions") or []          # the board's per-commission rows
runs = sum(r.get("n_items", 0) for r in rows)
errs = sum(r.get("n_errors", 0) for r in rows)
if runs < 1:
    sys.exit("no runs executed")
if errs:
    sys.exit(f"{errs} cell(s) errored — broker/vault path failed")
PY
  ok "sandboxed run converged through the broker (vault secret used, never exposed)"
  cleanup_finale; trap 'rm -rf "$(dirname "$AVP_HOME")"' EXIT
  ok "finale resources cleaned from the real library"
else
  step "skipping paid finale (AVP_SMOKE_PAID=1 + OPENROUTER_API_KEY for the full chain)"
fi

printf '\n\033[1;32mall %d checks passed\033[0m (throwaway AVP_HOME cleaned up)\n' "$pass"
