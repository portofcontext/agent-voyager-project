#!/usr/bin/env bash
# Run the three real-LLM supervisor examples end-to-end.
#
# Usage:
#   ./scripts/run-examples.sh              # all three (~$0.10 total on Haiku + Claude Code)
#   ./scripts/run-examples.sh 01           # just example 01
#   ./scripts/run-examples.sh 01 02        # any subset
#
# API key resolution order:
#   1. $ANTHROPIC_API_KEY if already set
#   2. $(cat ~/.anthropic-key) if that file exists
#   3. error and exit
#
# Run from anywhere — the script anchors paths via $REPO.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLES_DIR="$REPO/python/supervisors/simple-supervisor-example/examples"

# ── Resolve API key ──────────────────────────────────────────────────────────
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    if [[ -r "$HOME/.anthropic-key" ]]; then
        ANTHROPIC_API_KEY="$(cat "$HOME/.anthropic-key")"
        export ANTHROPIC_API_KEY
    else
        echo "error: ANTHROPIC_API_KEY not set and ~/.anthropic-key not readable" >&2
        echo "       set the env var or write your key to ~/.anthropic-key (chmod 600)" >&2
        exit 2
    fi
fi

# ── Pick which examples to run ───────────────────────────────────────────────
if [[ $# -eq 0 ]]; then
    SELECTED=("01" "02" "03")
else
    SELECTED=("$@")
fi

run_one() {
    local n="$1"
    local file label extra
    case "$n" in
        01)
            file="01_anthropic_cost_bounded.py"
            label="cost-bounded inspection (driver pattern, ~\$0.001)"
            extra=""
            ;;
        02)
            file="02_anthropic_self_correcting.py"
            label="self-correcting verifier (driver pattern, ~\$0.005)"
            extra=""
            ;;
        03)
            file="03_claude_code_audited.py"
            label="audited Claude Code session (observer pattern, ~\$0.10)"
            extra="USE_REAL_SDK=1"
            ;;
        *)
            echo "error: unknown example '$n' (valid: 01 02 03)" >&2
            exit 2
            ;;
    esac

    echo
    echo "════════════════════════════════════════════════════════════════════"
    echo "  Example $n — $label"
    echo "════════════════════════════════════════════════════════════════════"
    echo

    cd "$REPO"
    if [[ -n "$extra" ]]; then
        env $extra uv run python "$EXAMPLES_DIR/$file"
    else
        uv run python "$EXAMPLES_DIR/$file"
    fi
}

for n in "${SELECTED[@]}"; do
    run_one "$n"
done
