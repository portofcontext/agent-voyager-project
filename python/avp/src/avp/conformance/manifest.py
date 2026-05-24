"""Pydantic model for the AVP conformance agent manifest.

The manifest tells `avp-conformance run` how to invoke the SDK under test as
a subprocess. See `AGENT-PROCESS.md` for the wire-level contract the
subprocess itself must honor (stdin payload, stdout NDJSON, exit codes).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from avp.envelope import _STRICT


class AgentManifest(BaseModel):
    """How the conformance CLI invokes the SDK under test.

    `cwd` is resolved relative to the manifest file's location, not the
    CLI's working directory. Resolution is the caller's responsibility;
    this model only validates shape.
    """

    model_config = _STRICT

    command: list[str] = Field(
        min_length=1,
        description="Argv list used to spawn the agent subprocess.",
    )
    cwd: Path = Field(
        default=Path("."),
        description="Working directory, relative to the manifest's location.",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables passed to the subprocess.",
    )
    description: str | None = Field(
        default=None,
        description="Human-readable label for CLI output.",
    )
