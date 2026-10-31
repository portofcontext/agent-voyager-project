#!/usr/bin/env bash
# Build dist/avp.skill (a ZIP) with instructions and offline spec references.
# Usage: bash avp/scripts/build-skill.sh [output-directory]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
"$PYTHON" - "$ROOT" "${1:-$ROOT/dist}" <<'PY'
from pathlib import Path
import sys
import zipfile

root, out = map(Path, sys.argv[1:])
files = [root / name for name in ("SKILL.md", "LICENSE")]
files += sorted(
    p for p in (root / "avp/core/spec/v0.1").rglob("*")
    if p.is_file() and p.suffix in {".md", ".json", ".ndjson"}
)
out.mkdir(parents=True, exist_ok=True)
artifact = out / "avp.skill"
with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as bundle:
    for path in files:
        bundle.write(path, Path("avp") / path.relative_to(root))
print(f"Skill bundled: {artifact} ({len(files)} files)")
PY
