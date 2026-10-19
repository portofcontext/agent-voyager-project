#!/usr/bin/env bash
# Build the release artifact `avp-pi.tar.gz` into the directory given (default:
# dist/release/): the built adapter with its production dependencies, the
# TypeScript binding installed as a real copy (with its bundled price table).
# Pi's dependencies are JavaScript plus per-platform prebuilds, so one archive
# serves macOS and Linux on both architectures. Run the result with
# `node dist/src/main.js` from the extracted directory.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mkdir -p "${1:-$here/dist/release}" && cd "${1:-$here/dist/release}" && pwd)"
binding="$(cd "$here/../../../avp/bindings/typescript" && pwd)"

cd "$binding" && npm ci --no-audit --no-fund
cd "$here" && npm ci --no-audit --no-fund && npm run build

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/dist"
cp -R dist/src "$stage/dist/src"
cp README.md "$stage/"
# The staged package resolves the binding by absolute path, installed as a copy.
node -e '
  const fs = require("fs");
  const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
  pkg.dependencies["@avp/types"] = "file:" + process.argv[1];
  delete pkg.devDependencies;
  delete pkg.scripts;
  fs.writeFileSync(process.argv[2] + "/package.json", JSON.stringify(pkg, null, 2) + "\n");
' "$binding" "$stage"
(cd "$stage" && npm install --omit=dev --install-links --no-package-lock --no-audit --no-fund)

tar -czf "$out/avp-pi.tar.gz" -C "$stage" .
echo "wrote $out/avp-pi.tar.gz"
