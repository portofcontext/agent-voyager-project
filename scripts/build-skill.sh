#!/usr/bin/env bash
# Build aep.skill — a distributable .skill archive of the AEP skill bundle.
#
# Usage:
#   scripts/build-skill.sh                # builds dist/aep.skill
#   scripts/build-skill.sh /tmp/out       # builds /tmp/out/aep.skill
#
# What goes in the bundle:
#   SKILL.md, examples/, spec/v0.1/, conformance/v0.1/, python/aep/,
#   plus README.md and LICENSE for context.
#
# What's stripped:
#   __pycache__, *.pyc, .pytest_cache, *.egg-info, .DS_Store

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$REPO/dist}"
# Absolutize OUT_DIR. The packager runs from $CREATOR (different cwd), so a
# relative arg like `dist` resolves to the wrong path. Create the dir first
# so we can `cd` into it for the absolute resolution.
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
STAGE="$(mktemp -d)/aep"

cleanup() { /bin/rm -rf "$(dirname "$STAGE")"; }
trap cleanup EXIT

# Stage the bundle under a directory named "aep" so the .skill extracts into ~/.claude/skills/aep
mkdir -p "$STAGE"
cp "$REPO/SKILL.md" "$REPO/README.md" "$REPO/LICENSE" "$STAGE/"
cp -r "$REPO/examples" "$STAGE/"
mkdir -p "$STAGE/spec" "$STAGE/conformance" "$STAGE/python"
cp -r "$REPO/spec/v0.1" "$STAGE/spec/"
cp -r "$REPO/conformance/v0.1" "$STAGE/conformance/"
cp -r "$REPO/python/aep" "$STAGE/python/"

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
echo "Skill bundled: $OUT_DIR/aep.skill"
ls -lh "$OUT_DIR/aep.skill"
