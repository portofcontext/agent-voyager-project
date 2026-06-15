#!/usr/bin/env bash
# One-time setup for the Context Nuke demo (Code Mode x Arcade on AVP).
# Idempotent: safe to re-run. See README.md for prerequisites.
set -euo pipefail
cd "$(dirname "$0")"
DIR="$(pwd)"
PCTX_VERSION="v0.7.1"

echo "==> checking prerequisites"
command -v uv     >/dev/null || { echo "missing: uv (https://astral.sh/uv)"; exit 1; }
command -v docker >/dev/null || { echo "missing: docker (colima / OrbStack / Docker Desktop)"; exit 1; }
command -v gh     >/dev/null || { echo "missing: gh (GitHub CLI), used to fetch the pctx binary"; exit 1; }
command -v avp    >/dev/null || { echo "missing: avp  ->  uv tool install avp-cli"; exit 1; }

# colima keeps its socket off the default path; point DOCKER_HOST at it if needed.
if ! docker info >/dev/null 2>&1 && docker context inspect colima >/dev/null 2>&1; then
  export DOCKER_HOST="$(docker context inspect colima -f '{{.Endpoints.docker.Host}}')"
fi
docker info >/dev/null 2>&1 || { echo "docker daemon not reachable; start it (e.g. 'colima start')"; exit 1; }

echo "==> installing the goose agent"
avp agent install goose >/dev/null

echo "==> generating the nuke workbook + ground truth"
uv run make_nuke.py >/dev/null
uv run verify_nuke.py   # confirm the exact answers are recoverable from the sheet

echo "==> downloading the pctx ${PCTX_VERSION} linux binary for the sandbox"
case "$(uname -m)" in
  arm64|aarch64) ASSET="pctx-aarch64-unknown-linux-gnu.tar.gz" ;;
  x86_64|amd64)  ASSET="pctx-x86_64-unknown-linux-gnu.tar.gz" ;;
  *) echo "unsupported arch $(uname -m)"; exit 1 ;;
esac
gh release download "$PCTX_VERSION" --repo portofcontext/pctx --pattern "$ASSET" --dir "$DIR" --clobber
cp -f "$DIR/$ASSET" "$DIR/pctx-linux.tar.gz"

echo "==> building the Code Mode sandbox image (nuke-cm:latest)"
docker build -f Dockerfile.codemode -t nuke-cm:latest "$DIR" >/dev/null
echo "    $(docker run --rm nuke-cm:latest pctx --version) in image"

echo "==> installing commissions into the avp library"
mkdir -p "$HOME/.avp/commissions"
cp -f nuke-baseline.commission.json "$HOME/.avp/commissions/nuke-baseline.json"
cp -f nuke-codemode.commission.json "$HOME/.avp/commissions/nuke-codemode.json"

echo "==> creating the avp environment (custom image + seeded files)"
avp env create nuke-cm --image nuke-cm:latest \
  --file "nuke.xlsx=@$DIR/nuke.xlsx" \
  --file "sheets_mcp.py=@$DIR/sheets_mcp.py" \
  --file "pctx.json=@$DIR/pctx.json" \
  --force >/dev/null

echo
echo "setup complete.  run it with:   ANTHROPIC_API_KEY=sk-ant-... ./run.sh"
