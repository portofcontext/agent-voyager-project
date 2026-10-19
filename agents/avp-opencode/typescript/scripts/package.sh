#!/usr/bin/env bash
# Build the release archives `avp-opencode-<platform>.tar.gz` into the
# directory given (default: dist/release/), one per platform named after it
# (default: darwin-arm64 darwin-x64 linux-arm64 linux-x64, or set PLATFORMS).
#
# Each archive is the built adapter with its production dependencies, the
# TypeScript binding installed as a real copy (with its bundled price table),
# and the pinned `opencode-<platform>` package (plus its `-baseline` build on
# x64), fetched from npm whatever the build host is. OpenCode is a native
# binary per platform, so one archive can't serve them all. Run the result with
# `node dist/src/main.js` from the extracted directory.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mkdir -p "${1:-$here/dist/release}" && cd "${1:-$here/dist/release}" && pwd)"
binding="$(cd "$here/../../../avp/bindings/typescript" && pwd)"
platforms="${PLATFORMS:-darwin-arm64 darwin-x64 linux-arm64 linux-x64}"

cd "$binding" && npm ci --no-audit --no-fund
cd "$here" && npm ci --no-audit --no-fund && npm run build
version="$(node -p 'require("./package.json").dependencies["opencode-ai"]')"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
base="$work/base"
mkdir -p "$base/dist"
cp -R dist/src "$base/dist/src"
cp README.md "$base/"
# The staged package resolves the binding by absolute path, installed as a
# copy. The adapter runs the platform package's binary directly, so the
# `opencode-ai` launcher (and its install script) is left out.
node -e '
  const fs = require("fs");
  const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
  pkg.dependencies["@avp/types"] = "file:" + process.argv[1];
  delete pkg.dependencies["opencode-ai"];
  delete pkg.devDependencies;
  delete pkg.scripts;
  fs.writeFileSync(process.argv[2] + "/package.json", JSON.stringify(pkg, null, 2) + "\n");
' "$binding" "$base"
(cd "$base" && npm install --omit=dev --install-links --no-package-lock --no-audit --no-fund)

for platform in $platforms; do
  stage="$work/$platform"
  cp -R "$base" "$stage"
  pkgs="opencode-$platform"
  # The x64 builds need AVX2; the baseline build serves CPUs (and emulators) without it.
  case "$platform" in *-x64) pkgs="$pkgs opencode-$platform-baseline" ;; esac
  for pkg in $pkgs; do
    tarball="$(cd "$work" && npm pack --silent "$pkg@$version")"
    mkdir -p "$stage/node_modules/$pkg"
    tar -xzf "$work/$tarball" -C "$stage/node_modules/$pkg" --strip-components=1
    chmod +x "$stage/node_modules/$pkg/bin/opencode"
  done
  tar -czf "$out/avp-opencode-$platform.tar.gz" -C "$stage" .
  echo "wrote $out/avp-opencode-$platform.tar.gz"
done
