#!/usr/bin/env bash
# Build the release artifact `avp-gemini-cli.tar.gz` into the directory given
# (default: dist/release/): the built adapter with its production dependencies,
# the TypeScript binding installed as a real copy (with its bundled price
# table). Gemini CLI's optional dependencies (native PTY and keychain modules,
# with prebuilds for only some platforms) are left out, and its remaining
# native dependency carries a prebuild per platform, so one archive serves
# macOS and Linux on both architectures. Without a PTY, Gemini CLI's shell
# tool runs commands as child processes. Run the result with
# `node dist/src/main.js` from the extracted directory.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mkdir -p "${1:-$here/dist/release}" && cd "${1:-$here/dist/release}" && pwd)"
binding="$(cd "$here/../../../avp/bindings/typescript" && pwd)"

cd "$binding" && npm ci --no-audit --no-fund
cd "$here" && npm ci --omit=optional --no-audit --no-fund && npm run build

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
(cd "$stage" && npm install --omit=dev --omit=optional --install-links --no-package-lock --no-audit --no-fund)
# Native modules may only arrive as per-platform prebuilds (tree-sitter-bash
# ships one per platform); one compiled for the build host would not travel.
if find "$stage/node_modules" -name '*.node' -not -path '*/prebuilds/*' | grep -q .; then
  echo "error: a host-compiled native module is in the archive" >&2
  exit 1
fi

tar -czf "$out/avp-gemini-cli.tar.gz" -C "$stage" .
echo "wrote $out/avp-gemini-cli.tar.gz"
