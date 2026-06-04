"""Pydantic model for the AVP conformance agent manifest.

The manifest tells `avp-conformance run` how to invoke the SDK under test as
a subprocess. See `AGENT-PROCESS.md` for the wire-level contract the
subprocess itself must honor (stdin payload, stdout NDJSON, exit codes).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from avp.envelope import _STRICT


class ContainerSpec(BaseModel):
    """How a supervisor installs and runs this agent inside a Linux sandbox.

    The conformance harness itself runs agents on the host and ignores this;
    it exists for container-based supervisors (e.g. the `avp` CLI, whose runs
    happen in sandboxes). `install` steps are Dockerfile RUN shell strings
    executed at image-build time (network available); `command` is the
    in-sandbox argv prefix honoring the same run contract as `command` above.
    """

    model_config = _STRICT

    install: list[str] = Field(
        default_factory=list,
        description="Image-build RUN steps that install a Linux build of the agent.",
    )
    command: list[str] = Field(
        min_length=1,
        description="Argv list used to run the agent inside the sandbox.",
    )


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
    container: ContainerSpec | None = Field(
        default=None,
        description="Optional: how to install and run this agent inside a sandbox.",
    )
