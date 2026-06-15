#!/usr/bin/env bash
# Run the Context Nuke head-to-head: naive tool-calling vs pctx Code Mode.
# Pass extra avp flags through, e.g. ./run.sh --max-items 1
set -euo pipefail
cd "$(dirname "$0")"

: "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY (a Claude API key) first}"

# colima: point DOCKER_HOST at its socket if the default isn't up.
if ! docker info >/dev/null 2>&1 && docker context inspect colima >/dev/null 2>&1; then
  export DOCKER_HOST="$(docker context inspect colima -f '{{.Endpoints.docker.Host}}')"
fi

# avp forwards GOOSE_* into the sandbox; clear host overrides so the commission's
# model/provider wins (a stray GOOSE_PROVIDER would otherwise hijack the run).
unset GOOSE_PROVIDER GOOSE_MODEL 2>/dev/null || true

avp eval run nuke.eval.json --env nuke-cm --agent goose "$@"
