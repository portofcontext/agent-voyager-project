#!/usr/bin/env bash
# Build avp.skill — a distributable .skill archive of the AVP skill bundle.
#
# Usage:
#   scripts/build-skill.sh                # builds dist/avp.skill
#   scripts/build-skill.sh /tmp/out       # builds /tmp/out/avp.skill
#
# What goes in the bundle:
#   SKILL.md (+ README.md, LICENSE) from the repo root, plus the core
#   project's avp/spec/v0.1/ and avp/python/avp/ (conformance cases ship
#   inside python/avp, so there's no separate conformance/ copy).
#
# Worked example Configs live at supervisors/simple-supervisor-example/
# in the source repo and aren't shipped in the bundle — they need the agent
# packages and an Anthropic API key to actually run, neither of which install
# alongside a skill bundle. SKILL.md references them by their in-tree path so
# downstream agents can follow the link back to the repo.
#
# What's stripped:
#   __pycache__, *.pyc, .pytest_cache, *.egg-info, .DS_Store

set -euo pipefail

# `avp/scripts/build-skill.sh`: ROOT is the repo root (holds SKILL.md /
# README.md / LICENSE); AVP is the core project dir (holds spec/ + python/).
AVP="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$AVP/.." && pwd)"
OUT_DIR="${1:-$ROOT/dist}"
# Absolutize OUT_DIR. The packager runs from $CREATOR (different cwd), so a
# relative arg like `dist` resolves to the wrong path. Create the dir first
# so we can `cd` into it for the absolute resolution.
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
STAGE="$(mktemp -d)/avp"

cleanup() { /bin/rm -rf "$(dirname "$STAGE")"; }
trap cleanup EXIT

# Stage the bundle under a directory named "avp" so the .skill extracts into ~/.claude/skills/avp
mkdir -p "$STAGE"
cp "$ROOT/SKILL.md" "$ROOT/README.md" "$ROOT/LICENSE" "$STAGE/"
mkdir -p "$STAGE/spec" "$STAGE/python"
cp -r "$AVP/core/spec/v0.1" "$STAGE/spec/"
cp -r "$AVP/bindings/python" "$STAGE/python/avp"

# Strip build artifacts
find "$STAGE" \( -name __pycache__ -o -name .pytest_cache -o -name '*.egg-info' \) \
  -type d -exec /bin/rm -rf {} + 2>/dev/null || true
find "$STAGE" -name '*.pyc' -delete 2>/dev/null || true
find "$STAGE" -name '.DS_Store' -delete 2>/dev/null || true

# package_skill.py lives inside the anthropics/skills repo. Two lookup paths:
#   1. Pre-vendored at SKILL_CREATOR_DIR (set by CI when it clones the repo)
#   2. Locally installed at ~/.agents/skills/skill-creator (npx skills add output)
# If neither is found, exit with instructions.
if [[ -n "${SKILL_CREATOR_DIR:-}" && -f "$SKILL_CREATOR_DIR/scripts/package_skill.py" ]]; then
  CREATOR="$SKILL_CREATOR_DIR"
elif [[ -f "$HOME/.agents/skills/skill-creator/scripts/package_skill.py" ]]; then
  CREATOR="$HOME/.agents/skills/skill-creator"
else
  echo "error: skill-creator scripts not found" >&2
  echo "  set SKILL_CREATOR_DIR=<path to skill-creator>, or" >&2
  echo "  install with: npx skills add anthropics/skills@skill-creator -g -y" >&2
  exit 1
fi

cd "$CREATOR"
PYTHON="${PYTHON:-$(command -v python3 || command -v python)}"
if [[ -z "$PYTHON" ]]; then
  echo "error: no python or python3 in PATH; set PYTHON=/path/to/python" >&2
  exit 1
fi
PYTHONPATH=. "$PYTHON" -m scripts.package_skill "$STAGE" "$OUT_DIR"
echo ""
echo "Skill bundled: $OUT_DIR/avp.skill"
ls -lh "$OUT_DIR/avp.skill"
