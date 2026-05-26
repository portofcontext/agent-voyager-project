#!/usr/bin/env python3
"""Make `type`-discriminated unions in cargo-typify output internally tagged.

typify emits `#[serde(untagged)]` for a `oneOf` of `$ref`s and ignores the
schema's OpenAPI `discriminator`, so the generated enums do not discriminate
by the `type` field: serde picks the first structurally-matching variant (an
`avp.agent_started` event deserializes as `RunRequestedEvent`). The schema is
correct; only this Rust codegen target is wrong, so we fix it here rather than
contorting the canonical schema (same philosophy as the `default: null` strip).

For each untagged enum whose variants are all newtype wrappers over structs
that carry a `type` const, this rewrites:

  - `#[serde(untagged)]` -> `#[serde(tag = "type")]` on the enum
  - adds `#[serde(rename = "<const>")]` to each variant (value from the schema)
  - adds `skip_serializing` to each member struct's `type_` field, so serde's
    internal tag is not emitted a second time by the struct on serialize

Tag values come from each `$defs` entry's `properties.type.const` in the
schema. Deterministic; safe to run inside the binding regen + drift check.

Usage: tag-rust-unions.py <generated.rs> <schema.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main() -> None:
    rs_path = Path(sys.argv[1])
    schema_path = Path(sys.argv[2])

    defs = json.loads(schema_path.read_text()).get("$defs", {})
    tag_by_struct: dict[str, str] = {}
    for name, d in defs.items():
        if isinstance(d, dict):
            t = d.get("properties", {}).get("type")
            if isinstance(t, dict) and "const" in t:
                tag_by_struct[name] = t["const"]

    src = rs_path.read_text()
    members: set[str] = set()

    # Untagged enum block: the attr, the `pub enum NAME {` header, the body up
    # to the first line that is just `}`. Newtype-variant enums (our targets)
    # contain no inner braces, so the non-greedy body match is exact.
    enum_re = re.compile(
        r"#\[serde\(untagged\)\]\n(pub enum (\w+) \{\n)(.*?\n)(\})",
        re.DOTALL,
    )
    variant_re = re.compile(r"^(\s*)(\w+)\((\w+)\),?\s*$")

    def transform_enum(m: re.Match[str]) -> str:
        header, body = m.group(1), m.group(3)
        variants = [variant_re.match(line) for line in body.split("\n")]
        variants = [v for v in variants if v]
        # Only enums where every variant is a newtype over a tagged struct.
        if not variants or not all(v.group(3) in tag_by_struct for v in variants):
            return m.group(0)
        out = []
        for line in body.split("\n"):
            v = variant_re.match(line)
            if v:
                indent, inner = v.group(1), v.group(3)
                members.add(inner)
                out.append(f'{indent}#[serde(rename = "{tag_by_struct[inner]}")]')
            out.append(line)
        return f'#[serde(tag = "type")]\n{header}{chr(10).join(out)}\n{m.group(4)}'

    src = enum_re.sub(transform_enum, src)

    # In each member struct, suppress the redundant `type` field on serialize.
    # `rename = "type"` -> `rename = "type", skip_serializing` is valid in both
    # the single-line and multi-line (trailing-comma) attribute forms typify emits.
    for inner in members:
        block_re = re.compile(r"pub struct " + re.escape(inner) + r" \{.*?\n\}", re.DOTALL)
        bm = block_re.search(src)
        if not bm:
            continue
        block = bm.group(0)
        # Idempotent: bail only if the `type` field itself is already patched.
        # (Other fields carry `skip_serializing_if`, which is unrelated.)
        if 'rename = "type", skip_serializing' in block:
            continue
        # Find the renamed-`type` field's serde attribute (single- or multi-line).
        attr_match = re.search(r'#\[serde\(rename = "type"[^\]]*\)\]', block)
        if attr_match is None:
            continue
        attr = attr_match.group(0)
        new_attr = attr.replace('rename = "type"', 'rename = "type", skip_serializing', 1)
        # Internally-tagged deserialization strips the tag before handing the
        # content to the variant struct, so the struct's renamed `type` field
        # needs a `default` to fill. Add one when the field lacks it (events
        # already carry `default = "defaults::..."`; the MCP-server structs do not).
        if "default" not in attr:
            new_attr = new_attr[:-2] + ", default)]"
        patched = block.replace(attr, new_attr, 1)
        src = src[: bm.start()] + patched + src[bm.end() :]

    rs_path.write_text(src)
    print(f"  tagged: {rs_path.name} ({len(members)} member structs)")


if __name__ == "__main__":
    main()
