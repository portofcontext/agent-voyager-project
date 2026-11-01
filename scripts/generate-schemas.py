"""Generate the AVP v0.1 JSON Schemas from the Python SDK's wire models.

The models in `avp-sdk/python` are the source of truth. Run from the repo root
in the SDK's environment, since the root workspace still installs the old `avp`:

    uv run --project avp-sdk/python python scripts/generate-schemas.py

Writes to `spec/v0.1/`, next to the specs they describe:

    commission.schema.json        the Commission
    trajectory.schema.json        one trajectory Event
    agent-descriptor.schema.json  the Agent Descriptor
    avp.schema.json               a bundle: oneOf the three above
"""

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.trajectory import Event

OUT_DIR = Path(__file__).resolve().parent.parent / "spec" / "v0.1"
SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_BASE = "https://www.agentvoyagerproject.com/schema/v0.1"

SCHEMAS: list[tuple[str, Any, str, str]] = [
    (
        "commission.schema.json",
        Commission,
        "AVP v0.1 Commission",
        "The message a supervisor sends once to start an agent run. See commission.md.",
    ),
    (
        "trajectory.schema.json",
        Event,
        "AVP v0.1 Trajectory Event",
        "One CloudEvents 1.0 event of the trajectory an agent emits. See trajectory.md.",
    ),
    (
        "agent-descriptor.schema.json",
        AgentDescriptor,
        "AVP v0.1 Agent Descriptor",
        "An agent's description of itself and its built-ins. See agent-descriptor.md.",
    ),
]


def write_json(name: str, schema: dict[str, Any]) -> None:
    path = OUT_DIR / name
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(OUT_DIR.parent.parent)}")


def main() -> None:
    for name, model, title, description in SCHEMAS:
        schema = TypeAdapter(model).json_schema(by_alias=True, ref_template="#/$defs/{model}")
        write_json(
            name,
            {
                "$schema": SCHEMA_DRAFT,
                "$id": f"{SCHEMA_BASE}/{name}",
                **schema,
                "title": title,
                "description": description,
            },
        )

    write_json(
        "avp.schema.json",
        {
            "$schema": SCHEMA_DRAFT,
            "$id": f"{SCHEMA_BASE}/avp.schema.json",
            "title": "AVP v0.1",
            "description": "Any AVP v0.1 wire object: a Commission, a trajectory Event, or an Agent Descriptor.",
            "oneOf": [{"$ref": name} for name, *_ in SCHEMAS],
        },
    )


if __name__ == "__main__":
    main()
