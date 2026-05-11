#!/usr/bin/env python3
"""Generate JSON Schema 2020-12 files from the Pydantic v2 models in `avp.types`.

The Pydantic models in `python/avp/src/avp/types.py` are the source of truth
for the wire format. This script regenerates the canonical schema files
under `spec/v0.1/` so they cannot drift from the implementation.

Run from repo root:

    uv run python scripts/generate-schemas.py

One entry-point schema per AVP v0.1 spec, plus the unified bundle:

    spec/v0.1/commission.schema.json        — the Commission shape
    spec/v0.1/trajectory.schema.json        — agent-emitted Event union
    spec/v0.1/agent-descriptor.schema.json  — AgentDescriptor shape
    spec/v0.1/avp.schema.json               — top-level bundle (oneOf of all three)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "avp" / "src"))

from pydantic import TypeAdapter  # noqa: E402

from avp.types import AgentDescriptor, Commission, Event  # noqa: E402

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_BASE = "https://avp.dev/schema/v0.1"


def render(adapter: TypeAdapter, *, schema_id: str, title: str, description: str) -> dict[str, Any]:
    schema = adapter.json_schema(by_alias=True, ref_template="#/$defs/{model}")
    schema["$schema"] = SCHEMA_DRAFT
    schema["$id"] = schema_id
    schema["title"] = title
    schema["description"] = description
    return schema


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


def main() -> int:
    out_dir = ROOT / "spec" / "v0.1"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Generating AVP v0.1 JSON schemas from Pydantic models…")

    commission_schema = render(
        TypeAdapter(Commission),
        schema_id=f"{SCHEMA_BASE}/commission.schema.json",
        title="AVP v0.1 Commission",
        description=(
            "Supervisor → agent setup message. Declares prompt, model, and "
            "supervisor-managed assets (mcp_servers, skills, subagents) as "
            "opaque {id, ref} pairs the agent dereferences via the AVP "
            "Resolver API at startup. Sent once at startup. See "
            "spec/v0.1/commission.md."
        ),
    )
    write_json(out_dir / "commission.schema.json", commission_schema)

    trajectory_schema = render(
        TypeAdapter(Event),
        schema_id=f"{SCHEMA_BASE}/trajectory.schema.json",
        title="AVP v0.1 Trajectory (Event)",
        description=(
            "Agent → supervisor event. Each event is a CloudEvent 1.0 "
            "envelope carrying a typed `data` payload. The `type` field is "
            "the discriminator (reverse-DNS, `avp.*` namespace). Attribute "
            "names inside `data` follow OpenTelemetry GenAI semantic "
            "conventions and OTel span identification "
            "(`trace_id`, `span_id`, `parent_span_id`); AVP-specific "
            "attributes are namespaced `avp.*`. See "
            "spec/v0.1/trajectory.md."
        ),
    )
    write_json(out_dir / "trajectory.schema.json", trajectory_schema)

    descriptor_schema = render(
        TypeAdapter(AgentDescriptor),
        schema_id=f"{SCHEMA_BASE}/agent-descriptor.schema.json",
        title="AVP v0.1 Agent Descriptor",
        description=(
            "The agent's self-description. Enumerates built-in tools, "
            "subagents, and skills triggerable without supervisor "
            "configuration, plus the agent's identity, capabilities, and "
            "supported models. Pre-flight (`<agent> describe` stdout) and "
            "run-time (`agent_described.data['avp.descriptor']`) views MUST "
            "match for the same agent build. See "
            "spec/v0.1/agent-descriptor.md."
        ),
    )
    write_json(out_dir / "agent-descriptor.schema.json", descriptor_schema)

    # Clean up files we no longer produce.
    for old in ("event.schema.json", "supervisor-message.schema.json"):
        old_path = out_dir / old
        if old_path.exists():
            old_path.unlink()
            print(f"  removed {old_path.relative_to(ROOT)}")

    bundle = {
        "$schema": SCHEMA_DRAFT,
        "$id": f"{SCHEMA_BASE}/avp.schema.json",
        "title": "Agent Voyager Project (AVP) v0.1",
        "description": (
            "Umbrella bundle for the AVP v0.1 wire format. Built on "
            "CloudEvents 1.0 (envelopes), OpenTelemetry GenAI semantic "
            "conventions and span identification (data attribute names), "
            "JSON-RPC 2.0 (Resolver API), MCP (tool descriptors and "
            "supervisor-side tool dispatch), Agent Skills (SKILL.md), "
            "and JSON Schema 2020-12 (this document). AVP-specific "
            "concepts — the no-mid-run-reach-in topology, the "
            "trajectory-as-source-of-truth contract — live under the "
            "`avp.*` attribute namespace. See FOUNDATIONS.md and the "
            "per-spec entry-point schemas: commission.schema.json, "
            "trajectory.schema.json, agent-descriptor.schema.json."
        ),
        "oneOf": [
            {"$ref": "commission.schema.json"},
            {"$ref": "trajectory.schema.json"},
            {"$ref": "agent-descriptor.schema.json"},
        ],
    }
    write_json(out_dir / "avp.schema.json", bundle)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
