#!/usr/bin/env python3
"""Generate JSON Schema 2020-12 files from the Pydantic v2 models in `avp.types`.

The Pydantic models in `python/avp/src/avp/types.py` are the source of truth
for the wire format. This script regenerates the canonical schema files
under `spec/<spec>/<version>/` so they cannot drift from the implementation.

Run from repo root:

    uv run python scripts/generate-schemas.py

One schema per AVP spec; each lives under its own versioned directory:

    spec/trajectory/v0.1/trajectory.schema.json                   (Stable)
    spec/agent-descriptor/v0.1/agent-descriptor.schema.json       (Stable)
    spec/commission/v0.1-beta/commission.schema.json              (Beta)
    (resolver has no JSON Schema; it's an RPC protocol)
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "avp" / "src"))

from pydantic import TypeAdapter  # noqa: E402

from avp.types import AgentDescriptor, Commission, Event  # noqa: E402

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
RAW_BASE = "https://raw.githubusercontent.com/portofcontext/agent-voyager-project/main"


@dataclass
class SpecBuild:
    """One spec's schema build target."""

    name: str
    version: str
    title: str
    description: str
    adapter: TypeAdapter

    @property
    def out_dir(self) -> Path:
        return ROOT / "spec" / self.name / self.version

    @property
    def schema_path(self) -> Path:
        return self.out_dir / f"{self.name}.schema.json"

    @property
    def schema_id(self) -> str:
        return f"{RAW_BASE}/spec/{self.name}/{self.version}/{self.name}.schema.json"


def render(build: SpecBuild) -> dict[str, Any]:
    schema = build.adapter.json_schema(by_alias=True, ref_template="#/$defs/{model}")
    schema["$schema"] = SCHEMA_DRAFT
    schema["$id"] = build.schema_id
    schema["title"] = build.title
    schema["description"] = build.description
    return schema


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


def main() -> int:
    print("Generating AVP JSON schemas from Pydantic models…")

    builds = [
        SpecBuild(
            name="trajectory",
            version="v0.1",
            title="AVP Trajectory",
            description=(
                "Agent → observer event. Each event is a CloudEvent 1.0 "
                "envelope carrying a typed `data` payload. The `type` field is "
                "the discriminator (reverse-DNS, `avp.*` namespace). Attribute "
                "names inside `data` follow OpenTelemetry GenAI semantic "
                "conventions and OTel span identification "
                "(`trace_id`, `span_id`, `parent_span_id`); AVP-specific "
                "attributes are namespaced `avp.*`. See "
                "spec/trajectory/v0.1/trajectory.md."
            ),
            adapter=TypeAdapter(Event),
        ),
        SpecBuild(
            name="agent-descriptor",
            version="v0.1",
            title="AVP Agent Descriptor",
            description=(
                "The agent's self-description. Enumerates built-in tools, "
                "subagents, and skills triggerable without supervisor "
                "configuration, plus the agent's identity, capabilities, and "
                "supported models. Pre-flight (`<agent> describe` stdout) and "
                "run-time (`agent_described.data['avp.descriptor']`) views MUST "
                "match for the same agent build. See "
                "spec/agent-descriptor/v0.1/agent-descriptor.md."
            ),
            adapter=TypeAdapter(AgentDescriptor),
        ),
        SpecBuild(
            name="commission",
            version="v0.1-beta",
            title="AVP Commission (Beta)",
            description=(
                "Supervisor → agent setup message. Declares prompt, model, and "
                "supervisor-managed assets (mcp_servers, skills, subagents) as "
                "opaque {id, ref} pairs the agent dereferences via the AVP "
                "Resolver API at startup. Sent once at startup. See "
                "spec/commission/v0.1-beta/commission.md."
            ),
            adapter=TypeAdapter(Commission),
        ),
    ]

    for build in builds:
        write_json(build.schema_path, render(build))

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
