#!/usr/bin/env bash
#
# Clean-room onboarding smoke test.
#
# Runs the README Quickstart for one or both agents inside a fresh ubuntu:24.04
# container that has NOTHING preinstalled, to prove a brand-new contributor's
# path still works: install uv -> `uv sync` -> `avp agent install <agent>` (over
# HTTPS, no gh, no auth) -> `avp agent describe` boots the installed agent. With
# AVP_SMOKE_PAID=1 it also runs a 2-run `avp eval` (needs ANTHROPIC_API_KEY).
#
# It ships the WORKING TREE into the container (git ls-files | tar), so it tests
# your local, uncommitted changes -- catching onboarding regressions before they
# are pushed. Needs podman or docker.
#
#   scripts/onboarding-smoke.sh                 # goose, free (stops at describe)
#   scripts/onboarding-smoke.sh claude-code     # claude-code (installs node + claude CLI)
#   scripts/onboarding-smoke.sh all             # both agents
#   AVP_SMOKE_PAID=1 scripts/onboarding-smoke.sh all   # also run a real eval (paid)
#
set -euo pipefail

case "${1:-goose}" in
  goose) AGENTS="goose" ;;
  claude-code) AGENTS="claude-code" ;;
  all) AGENTS="goose claude-code" ;;
  *) echo "usage: $0 [goose|claude-code|all]" >&2; exit 2 ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RUNTIME="$(command -v podman || command -v docker || true)"
[ -n "$RUNTIME" ] || { echo "error: need podman or docker on PATH" >&2; exit 2; }
IMAGE="docker.io/library/ubuntu:24.04"

PAID=0
KEY_ENV=()
if [ "${AVP_SMOKE_PAID:-0}" = "1" ]; then
  [ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "error: AVP_SMOKE_PAID=1 needs ANTHROPIC_API_KEY" >&2; exit 2; }
  PAID=1
  KEY_ENV=(-e ANTHROPIC_API_KEY)  # passes the host value through; never printed
fi

TARBALL="$(mktemp)"
INNER_FILE="$(mktemp)"
AUTHFILE=""
cleanup() { rm -f "$TARBALL" "$INNER_FILE" ${AUTHFILE:+"$AUTHFILE"}; }
trap cleanup EXIT

# podman on macOS can invoke a docker credential helper (e.g. gcloud) on pull and
# fail; bypass it with an empty auth file. Harmless for docker (we skip it there).
AUTH=()
if [[ "$RUNTIME" == *podman ]]; then
  AUTHFILE="$(mktemp)"; printf '{}' > "$AUTHFILE"; AUTH=(--authfile "$AUTHFILE")
  "$RUNTIME" pull "${AUTH[@]}" "$IMAGE" >/dev/null
fi

git ls-files -z | tar czf "$TARBALL" --null -T -

# Steps run INSIDE the container. $AGENTS (space-separated) / $PAID arrive via the
# environment; the working-tree tarball arrives on stdin. No gh is installed on
# purpose -- a public release must install over plain HTTPS. Written to a file
# (not captured via $(...)) so macOS's bash 3.2 doesn't choke on the `case )` parens.
cat > "$INNER_FILE" <<'INNEREOF'
set -uo pipefail
FAILED=0
ok()   { echo "PASS :: $1"; }
bad()  { echo "GAP  :: $1"; FAILED=1; }
step() { echo; echo "==== $1 ===="; }
has()  { case " $AGENTS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

cat > /src.tgz   # the working-tree tarball (stdin)

step "baseline + uv (no gh on purpose)"
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq git curl ca-certificates tar >/dev/null 2>&1 && ok "baseline" || bad "baseline"
curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
export PATH="$HOME/.local/bin:$PATH"
uv --version >/dev/null 2>&1 && ok "uv" || bad "uv"
command -v gh >/dev/null && bad "gh present (should be absent)" || ok "no gh (install must use HTTPS)"

step "agent runtime prereqs ($AGENTS)"
if has goose; then
  apt-get install -y -qq libssl3 >/dev/null 2>&1 && ok "libssl3 (goose binary TLS)" || bad "libssl3"
fi
if has claude-code; then
  curl -fsSL https://deb.nodesource.com/setup_20.x 2>/dev/null | bash - >/dev/null 2>&1
  apt-get install -y -qq nodejs >/dev/null 2>&1 && ok "node" || bad "node"
  npm install -g @anthropic-ai/claude-code >/dev/null 2>&1 && command -v claude >/dev/null \
    && ok "claude CLI" || bad "claude CLI"
fi

step "extract working tree + uv sync"
mkdir -p /work/avp && tar xzf /src.tgz -C /work/avp 2>/dev/null && cd /work/avp && ok "extract" || bad "extract"
uv sync >/tmp/sync.log 2>&1 && ok "uv sync" || { bad "uv sync"; tail -8 /tmp/sync.log; }

for a in $AGENTS; do
  step "avp agent install $a (HTTPS, no gh, no auth)"
  uv run avp agent install "$a" >/tmp/inst.log 2>&1 && ok "install $a" || { bad "install $a"; tail -12 /tmp/inst.log; }
  uv run avp agent describe "$a" >/tmp/desc.log 2>&1 && { ok "describe $a boots"; head -2 /tmp/desc.log; } \
    || { bad "describe $a"; tail -10 /tmp/desc.log; }
done

step "avp agent list"
uv run avp agent list 2>&1 | sed -n '3,8p'

if [ "${PAID:-0}" = "1" ]; then
  COMMA="$(echo "$AGENTS" | tr ' ' ',')"
  step "avp eval run --max-items 1 ($COMMA, PAID — real model)"
  uv run avp init capitals --agent "$COMMA" >/dev/null 2>&1 && ok "init capitals" || bad "init capitals"
  uv run avp eval run capitals.eval.json --max-items 1 || bad "eval run"
else
  step "paid eval skipped (set AVP_SMOKE_PAID=1 + ANTHROPIC_API_KEY to run it)"
fi

echo
[ $FAILED -eq 0 ] && echo "RESULT :: onboarding OK ($AGENTS)" || { echo "RESULT :: gaps found"; exit 1; }
INNEREOF

B64="$(base64 < "$INNER_FILE" | tr -d '\n')"

echo "→ onboarding smoke: [$AGENTS] ($RUNTIME, ${IMAGE##*/}, paid=$PAID) — testing the working tree"
# ${arr[@]+"${arr[@]}"} expands safely even when the array is empty under `set -u`
# on macOS's bash 3.2.
"$RUNTIME" run --rm -i ${AUTH[@]+"${AUTH[@]}"} -e AGENTS="$AGENTS" -e PAID="$PAID" \
  ${KEY_ENV[@]+"${KEY_ENV[@]}"} "$IMAGE" \
  bash -lc "echo $B64 | base64 -d > /inner.sh && bash /inner.sh" < "$TARBALL"
