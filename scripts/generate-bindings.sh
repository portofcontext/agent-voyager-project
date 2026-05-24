#!/usr/bin/env bash
# Regenerate the Rust + TypeScript bindings for AVP wire types from the
# canonical JSON Schemas under `spec/v0.1/`.
#
# Single source of truth chain:
#   python/avp/src/avp/types.py (Pydantic, hand-written)
#     -> spec/v0.1/*.schema.json (auto-generated; scripts/generate-schemas.py)
#       -> rust/avp/src/*.rs       (generated here, via cargo-typify)
#       -> typescript/avp/src/*.ts (generated here, via json-schema-to-typescript)
#
# Why we generate per-schema and not from the unified bundle:
#   cargo-typify can't follow `$ref` across files. The bundle (avp.schema.json)
#   uses `oneOf` of refs to siblings; pointed at the bundle, typify errors out.
#   We feed each per-shape schema in directly. That produces some duplicate
#   helper types (JsonRpcRequestPayload exists in both event and supervisor
#   modules) — they're equivalent on the wire; pick the module-scoped one.
#
# Why we strip `default: null` from schemas before typify:
#   typify has a wart: when a property has `"default": null` AND its type is
#   a newtype wrapper (e.g. `Id` defined as `type: string | integer | null`),
#   it emits a broken `Default` function trying to construct the newtype with
#   no arguments. Pydantic's `= None` defaults emit `"default": null` in the
#   schema, but they're redundant — a nullable type defaults to absence
#   regardless. We strip them before generation; the Pydantic source still
#   carries the correct semantic.
#
# Prerequisites:
#   - cargo install cargo-typify
#   - npx (ships with Node.js — no global install needed for json-schema-to-typescript)
#   - jq (for the default-stripping pre-pass)

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SPEC="$REPO/spec/v0.1"
RUST_OUT="$REPO/rust/avp/src"
TS_OUT="$REPO/typescript/avp/src"

# Tools
command -v cargo-typify >/dev/null 2>&1 || {
  echo "error: cargo-typify not found. Install: cargo install cargo-typify" >&2
  exit 1
}
command -v jq >/dev/null 2>&1 || {
  echo "error: jq not found. Install: brew install jq" >&2
  exit 1
}
command -v npx >/dev/null 2>&1 || {
  echo "error: npx not found. Install Node.js." >&2
  exit 1
}

mkdir -p "$RUST_OUT" "$TS_OUT"

# Strip `default: null` recursively from a schema. Pre-pass for typify; safe
# for json-schema-to-typescript too (TS optional types don't care about the
# explicit default).
strip_null_defaults() {
  local input="$1"
  # walk the schema; delete any object key called "default" whose value is null.
  jq 'walk(if type == "object" and has("default") and .default == null then del(.default) else . end)' "$input"
}

generate_rust() {
  local name="$1"      # output module name (no .rs)
  local schema="$2"    # path to schema file
  local tmp
  tmp="$(mktemp -t "avp-${name}-XXXXXX.json")"
  trap "rm -f '$tmp'" RETURN

  strip_null_defaults "$schema" > "$tmp"
  cargo typify --no-builder "$tmp" -o "$RUST_OUT/$name.rs"
  # typify ignores the schema discriminator and emits `#[serde(untagged)]` for
  # `type`-discriminated unions; re-tag them so they discriminate by `type`.
  python3 "$REPO/scripts/tag-rust-unions.py" "$RUST_OUT/$name.rs" "$schema"
  echo "  rust: wrote $RUST_OUT/$name.rs"
}

generate_ts() {
  local name="$1"
  local schema="$2"
  local tmp
  tmp="$(mktemp -t "avp-${name}-XXXXXX.json")"
  trap "rm -f '$tmp'" RETURN

  strip_null_defaults "$schema" > "$tmp"
  # json-schema-to-typescript: --unreachableDefinitions surfaces every $defs
  # entry (we want them all even if not referenced from the root).
  npx -y -p json-schema-to-typescript@^15 json2ts \
    --unreachableDefinitions \
    -i "$tmp" \
    -o "$TS_OUT/$name.ts" >/dev/null
  echo "  ts:   wrote $TS_OUT/$name.ts"
}

echo "Generating Rust bindings (cargo-typify)…"
generate_rust "commission" "$SPEC/commission.schema.json"
generate_rust "trajectory" "$SPEC/trajectory.schema.json"
generate_rust "agent_descriptor" "$SPEC/agent-descriptor.schema.json"

# Old generated files from previous schema/spec names; clean up to avoid
# stale code drifting in tree.
rm -f "$RUST_OUT/event.rs" "$RUST_OUT/supervisor_message.rs"
rm -f "$TS_OUT/event.ts" "$TS_OUT/supervisor-message.ts"

echo
echo "Generating TypeScript bindings (json-schema-to-typescript)…"
generate_ts "commission" "$SPEC/commission.schema.json"
generate_ts "trajectory" "$SPEC/trajectory.schema.json"
generate_ts "agent-descriptor" "$SPEC/agent-descriptor.schema.json"

echo
echo "Done."
