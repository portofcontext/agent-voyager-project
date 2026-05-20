"""avp.commission — Pydantic types for the AVP Commission Spec.

Defines the Commission shape (supervisor → agent setup message) and the
managed-asset entries the supervisor declares inline. This module mirrors
the [Commission spec](../../../../spec/v0.1/commission.md).

Consumers wanting only the run-config object can:

    from avp.commission import Commission, McpServerHttp, McpServerStdio

…without dragging in Trajectory / Descriptor types.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

from avp._envelope import _STRICT

_ID_PATTERN = r"^[a-z0-9_-]+$"


class McpServerHttp(BaseModel):
    """Inline HTTP MCP server entry in Commission.mcp_servers."""

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    type: Literal["http"]
    url: str = Field(min_length=1)
    headers: dict[str, str] | None = None


class McpServerStdio(BaseModel):
    """Inline stdio MCP server entry in Commission.mcp_servers."""

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    type: Literal["stdio"]
    command: list[str] = Field(min_length=1)
    args: list[str] | None = None
    env: dict[str, str] | None = None


McpServer = Annotated[McpServerHttp | McpServerStdio, Field(discriminator="type")]


class Skill(BaseModel):
    """Inline skill entry in Commission.skills."""

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    files: dict[str, str]

    @field_validator("files")
    @classmethod
    def _require_skill_md(cls, v: dict[str, str]) -> dict[str, str]:
        if "SKILL.md" not in v:
            raise ValueError("files must contain 'SKILL.md'")
        return v

    def _frontmatter_value(self, key: str) -> str | None:
        content = self.files.get("SKILL.md", "")
        if not content.startswith("---"):
            return None
        end = content.find("---", 3)
        if end == -1:
            return None
        for line in content[3:end].splitlines():
            if line.startswith(f"{key}:"):
                return line[len(key) + 1 :].strip() or None
        return None

    @property
    def name(self) -> str | None:
        return self._frontmatter_value("name")

    @property
    def description(self) -> str | None:
        return self._frontmatter_value("description")



class SupervisorPreamble(BaseModel):
    """Identifies the supervisor that is requesting the run.

    Carried inside `Commission.supervisor` and projected onto the
    `run_requested` event's `data` (`avp.supervisor.name` +
    `avp.supervisor.version`) so a trajectory consumer can attribute the
    run to the originating supervisor without an out-of-band lookup. The
    event's `source` is `avp://agent` (the agent is the sole producer on
    the wire); supervisor attribution lives inside `data`.

    `name` SHOULD be a stable identifier for the supervisor implementation
    or instance (e.g. `"simple-supervisor-example"`, `"acme.scheduler"`).
    `version` is optional but recommended; it travels with the trajectory
    and lets auditors correlate a run with the exact supervisor build
    that requested it.
    """

    model_config = _STRICT
    name: str = Field(min_length=1)
    version: str | None = None


class Commission(BaseModel):
    """Supervisor's declaration of the supervisor-managed environment slice.

    Managed asset entries (`mcp_servers`, `skills`) carry inline connection
    material; no resolver round-trip is needed. The agent dials MCP servers
    and injects skill content directly from these fields at startup.

    Anything the agent provides on its own (in-process tools, baked-in
    skills) is invisible to AVP and the Commission entirely. The agent's own
    contribution surfaces in `agent_described.data["avp.descriptor"]` so
    consumers can audit what the agent showed up with. The agent's runtime
    layer merges its internal contribution with the Commission-managed assets
    into one bag the loop dispatches against; collisions on `id` are a
    startup error.
    """

    model_config = _STRICT

    schema_version: Literal["0.1"]
    run_id: str = Field(min_length=1)

    # Supervisor identity. Optional but RECOMMENDED. When present, the agent
    # stamps `run_requested.data.avp.supervisor.*` from this field so the
    # trajectory records who requested the run. When absent, the agent
    # still emits `run_requested` but with `avp.supervisor.name="unknown"`.
    supervisor: SupervisorPreamble | None = None

    # Supervisor-managed assets. Connection material is inline; agents dial
    # MCP servers and load skill content directly at startup.
    mcp_servers: list[McpServer] | None = None
    skills: list[Skill] | None = None

    # Allow-lists over the agent's Descriptor-declared surface. Each list
    # gates the parallel `descriptor.*` field for this run.
    #
    #   - None (absent) → every descriptor entry of that kind is exposed
    #                     (default).
    #   - []            → none are exposed.
    #   - [n1, n2, …]   → only the listed names/ids are exposed; the agent
    #                     hides the rest from the model and runtime-blocks
    #                     any hallucinated invocation with a `tool_returned`
    #                     (isError=True) / `subagent_failed`.
    #
    # Names MUST appear in the corresponding descriptor field at startup or
    # the agent emits `error_occurred(code: "commission_collision")` and
    # stops with `reason=error`. Subtractive-only: these have no effect on
    # supervisor-managed assets (those are gated by being-in-the-Commission).
    # `enabled_builtin_mcp_servers` filters `descriptor.mcp_servers[].id`;
    # disabling a server prevents the agent from dialing it, so its tools
    # are unavailable for the run.
    enabled_builtin_tools: list[str] | None = None
    enabled_builtin_subagents: list[str] | None = None
    enabled_builtin_skills: list[str] | None = None
    enabled_builtin_mcp_servers: list[str] | None = None

    output_schema: dict[str, Any] | None = None

    # Agent plane (what the agent runs)
    prompt: str | None = None
    system_prompt: str | None = None
    model: str | None = None

    # Metadata
    thread_id: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None


__all__ = [
    "Commission",
    "McpServer",
    "McpServerHttp",
    "McpServerStdio",
    "Skill",
    "SupervisorPreamble",
]
