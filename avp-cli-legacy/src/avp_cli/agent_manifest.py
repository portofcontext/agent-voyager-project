"""How the CLI invokes an installed agent (the `avp-conformance.json` shape).

An agent ships an `avp-conformance.json` manifest describing how to spawn it.
The supervisor (this CLI) reads that file to run the agent, on the host for
`describe`/`list` and inside a sandbox for `eval`/`run` (the `container` block).
This is a deployment contract the supervisor owns; the conformance harness keeps
its own copy for the same file, since spawning agents is a deployment concern and
the shared `avp` wire-types package deliberately stays out of it.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from avp.envelope import _STRICT


class ContainerSpec(BaseModel):
    """How a supervisor installs and runs this agent inside a Linux sandbox.

    `install` steps are Dockerfile RUN shell strings executed at image-build
    time (network available); `command` is the in-sandbox argv prefix honoring
    the same run contract as the host `command`.
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
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables the agent requires inside the sandbox.",
    )


class AgentManifest(BaseModel):
    """How the CLI spawns the agent subprocess.

    `cwd` is resolved relative to the manifest file's location, not the CLI's
    working directory. Resolution is the caller's responsibility; this model
    only validates shape.
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
