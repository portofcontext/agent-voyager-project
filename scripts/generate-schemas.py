#!/usr/bin/env python3
"""Generate JSON Schema 2020-12 files from the Pydantic v2 models in `avp.types`.

The Pydantic models in `python/avp/src/avp/types.py` are the source of truth
for the wire format. This script regenerates the canonical schema files
under `spec/v0.1/` so they cannot drift from the implementation.

Run from repo root:

    uv run python scripts/generate-schemas.py

Outputs:
    spec/v0.1/commission.schema.json   — the Commission message
    spec/v0.1/event.schema.json        — agent-emitted Event union
    spec/v0.1/avp.schema.json          — top-level bundle (oneOf over both)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "avp" / "src"))

from pydantic import TypeAdapter  # noqa: E402

from avp.types import Commission, Event  # noqa: E402

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

    config_schema = render(
        TypeAdapter(Commission),
        schema_id=f"{SCHEMA_BASE}/commission.schema.json",
        title="AVP v0.1 Commission",
        description=(
            "Supervisor → agent setup message. Declares the agent's complete "
            "environment (mcp_servers, allowed_tools, skills, subagents, prompts). "
            "Sent once at startup. The supervisor MUST NOT modify the environment "
            "mid-run."
        ),
    )
    write_json(out_dir / "commission.schema.json", config_schema)

    event_schema = render(
        TypeAdapter(Event),
        schema_id=f"{SCHEMA_BASE}/event.schema.json",
        title="AVP v0.1 Event",
        description=(
            "Agent → supervisor event. Each event is a CloudEvent 1.0 envelope "
            "carrying a typed `data` payload. The `type` field is the discriminator "
            "(reverse-DNS, `avp.*` namespace). Attribute names inside `data` follow "
            "OpenTelemetry GenAI semantic conventions and OTel span identification "
            "(`trace_id`, `span_id`, `parent_span_id`); AVP-specific attributes are "
            "namespaced `avp.*`."
        ),
    )
    write_json(out_dir / "event.schema.json", event_schema)

    # v0.1 has no supervisor → agent channel — `Commission` goes in via stdin
    # once, no replies flow back. Delete the supervisor-message schema if a
    # previous run wrote it; otherwise the bundle ref below dangles.
    sup_path = out_dir / "supervisor-message.schema.json"
    if sup_path.exists():
        sup_path.unlink()
        print(f"  removed {sup_path.relative_to(ROOT)}")

    bundle = {
        "$schema": SCHEMA_DRAFT,
        "$id": f"{SCHEMA_BASE}/avp.schema.json",
        "title": "Agent Voyage Protocol (AVP) v0.1",
        "description": (
            "Wire format for the Agent Voyage Protocol. Built on CloudEvents "
            "1.0 (envelopes), OpenTelemetry GenAI semantic conventions and span "
            "identification (data attribute names), MCP (tool descriptors and "
            "supervisor-side tool dispatch), Agent Skills (SKILL.md), and JSON "
            "Schema 2020-12 (this document). AVP-specific concepts — the "
            "no-mid-run-reach-in topology, the trajectory-as-source-of-truth "
            "contract — live under the `avp.*` attribute namespace. See "
            "FOUNDATIONS.md for the full mapping rationale."
        ),
        "oneOf": [
            {"$ref": "commission.schema.json"},
            {"$ref": "event.schema.json"},
        ],
    }
    write_json(out_dir / "avp.schema.json", bundle)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
