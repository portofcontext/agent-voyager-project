#!/usr/bin/env python3
"""Generate JSON Schema 2020-12 files from the Pydantic v2 models in `aep.types`.

The Pydantic models in `python/aep/src/aep/types.py` are the source of truth
for the wire format. This script regenerates the four canonical schema files
under `spec/v0.1/` so they cannot drift from the implementation.

Run from repo root:

    uv run python scripts/generate-schemas.py

Outputs:
    spec/v0.1/config.schema.json              — the Config message
    spec/v0.1/event.schema.json               — runner-emitted Event union
    spec/v0.1/supervisor-message.schema.json  — SupervisorMessage union
    spec/v0.1/aep.schema.json                 — top-level bundle referencing all three
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "aep" / "src"))

from pydantic import TypeAdapter  # noqa: E402

from aep.types import Config, Event, SupervisorMessage  # noqa: E402

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_BASE = "https://aep.dev/schema/v0.1"


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

    print("Generating AEP v0.1 JSON schemas from Pydantic models…")

    config_schema = render(
        TypeAdapter(Config),
        schema_id=f"{SCHEMA_BASE}/config.schema.json",
        title="AEP v0.1 Config",
        description=(
            "Supervisor → runner setup message. Declares the agent's complete "
            "environment (boundary, tools, mcp_servers, skills, verifiers, prompts). "
            "Sent once at startup. The supervisor MUST NOT modify the environment "
            "mid-run."
        ),
    )
    write_json(out_dir / "config.schema.json", config_schema)

    event_schema = render(
        TypeAdapter(Event),
        schema_id=f"{SCHEMA_BASE}/event.schema.json",
        title="AEP v0.1 Event",
        description=(
            "Runner → supervisor event. Each event is a CloudEvent 1.0 envelope "
            "carrying a typed `data` payload. The `type` field is the discriminator "
            "(reverse-DNS, `aep.*` namespace). Attribute names inside `data` follow "
            "OpenTelemetry GenAI semantic conventions and OTel span identification "
            "(`trace_id`, `span_id`, `parent_span_id`); AEP-specific attributes are "
            "namespaced `aep.*`."
        ),
    )
    write_json(out_dir / "event.schema.json", event_schema)

    supervisor_schema = render(
        TypeAdapter(SupervisorMessage),
        schema_id=f"{SCHEMA_BASE}/supervisor-message.schema.json",
        title="AEP v0.1 SupervisorMessage",
        description=(
            "Supervisor (or MCP server) → runner reply. v0.1 carries only "
            "`aep.tool_exec_resolved` events. `source` is `aep://supervisor` for "
            "supervisor-routed RPCs or `aep://mcp/<server_id>` for MCP-server-routed "
            "RPCs. The payload's `data.rpc` is a JSON-RPC 2.0 response."
        ),
    )
    write_json(out_dir / "supervisor-message.schema.json", supervisor_schema)

    bundle = {
        "$schema": SCHEMA_DRAFT,
        "$id": f"{SCHEMA_BASE}/aep.schema.json",
        "title": "Agent Execution Protocol (AEP) v0.1",
        "description": (
            "Wire format for the Agent Execution Protocol. Built on CloudEvents "
            "1.0 (envelopes), OpenTelemetry GenAI semantic conventions and span "
            "identification (data attribute names), JSON-RPC 2.0 (RPC payloads), "
            "MCP (tool descriptors), Agent Skills (SKILL.md), and JSON Schema "
            "2020-12 (this document). AEP-specific concepts — verifier, boundary, "
            "the no-mid-run-reach-in topology, the trajectory-as-source-of-truth "
            "contract — live under the `aep.*` attribute namespace. See "
            "FOUNDATIONS.md for the full mapping rationale."
        ),
        "oneOf": [
            {"$ref": "config.schema.json"},
            {"$ref": "event.schema.json"},
            {"$ref": "supervisor-message.schema.json"},
        ],
    }
    write_json(out_dir / "aep.schema.json", bundle)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
