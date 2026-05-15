"""avp.commission — Pydantic types for the AVP Commission Spec.

Defines the Commission shape (supervisor → agent setup message) and the
opaque managed-asset refs the supervisor declares. This module mirrors
the [Commission spec](../../../../spec/v0.1/commission.md).

Consumers wanting only the run-config object can:

    from avp.commission import Commission, McpServerRef, SubagentRef

…without dragging in Trajectory / Descriptor / Resolver API types.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, JsonValue

from avp._envelope import _STRICT

# An opaque, supervisor-defined reference resolved by the AVP resolver
# protocol. AVP does not constrain the shape; it can be a string (UUID, ARN,
# content hash, URL, anything the supervisor's resolver understands), an
# object (the supervisor's own structured shape, e.g. Anthropic Managed
# Agents' `{type, skill_id, version}`), or any other JSON value. The agent
# round-trips the value verbatim to the resolver and uses the returned
# connection material; the agent never interprets it.
_ID_PATTERN = r"^[a-z0-9_-]+$"


class McpServerRef(BaseModel):
    """Reference to a supervisor-managed MCP server.

    The agent resolves this entry at startup by calling `avp.resolve` with
    `{kind: "mcp_server", id, ref}`. The resolver returns the connection
    material (transport, URL, auth, etc.) the agent uses to dial the actual
    MCP server. Per-`kind` result schemas are pinned in the Resolver API
    spec (`spec/v0.1/resolver.md` §3.2). Auth and transport are deployment
    concerns; AVP does not constrain them.
    """

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    ref: JsonValue


class SkillRef(BaseModel):
    """Reference to a supervisor-managed skill.

    The agent resolves this entry at startup by calling `avp.resolve` with
    `{kind: "skill", id, ref}`. The resolver returns the SKILL.md content
    (or a location the agent fetches and reads); agentskills.io's content
    model still applies; the resolver just hands the content back from
    whatever store the supervisor uses.
    """

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    ref: JsonValue


class SubagentRef(BaseModel):
    """Reference to a supervisor-managed subagent.

    The agent resolves this entry at startup by calling `avp.resolve` with
    `{kind: "subagent", id, ref}`; the resolver returns the model-facing
    metadata (`name`, `description`, `inputSchema`) so the parent's model
    can decide whether to delegate. When the model invokes the subagent at
    runtime, the agent calls `avp.spawn_subagent` with the same ref to
    obtain a child `run_id`. The subagent run carries its own complete
    trajectory; the parent's `subagent_invoked.data["avp.subagent.run_id"]`
    references it.
    """

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    ref: JsonValue


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

    All asset entries (`mcp_servers`, `skills`, `subagents`) are opaque refs
    resolved by the AVP Resolver API at startup (see `spec/v0.1/resolver.md`).
    The
    supervisor never embeds connection material, file paths, or inline
    asset definitions on the wire; those land in `run_requested.data`
    on the trajectory and would leak secrets to consumers.

    Anything the agent provides on its own (in-process tools, baked-in
    skills, internally-defined subagents) is invisible to AVP and the
    Commission entirely. The agent's own contribution surfaces in
    `agent_described.data["avp.descriptor"]` so consumers can audit what the
    agent showed up with. The agent's runtime layer merges its internal
    contribution with the resolved managed assets into one bag the loop
    dispatches against; collisions on `id` are a startup error.
    """

    model_config = _STRICT

    schema_version: Literal["0.1"]
    run_id: str = Field(min_length=1)

    # Supervisor identity. Optional but RECOMMENDED. When present, the agent
    # stamps `run_requested.data.avp.supervisor.*` from this field so the
    # trajectory records who requested the run. When absent, the agent
    # still emits `run_requested` but with `avp.supervisor.name="unknown"`.
    supervisor: SupervisorPreamble | None = None

    # Supervisor-managed assets. Each entry is `{id, ref}` where `ref` is
    # opaque to AVP and to the agent. Resolution timing:
    #   - mcp_servers, skills: at startup (fail-fast on resolver error)
    #   - subagents: metadata at startup; spawn on-demand via
    #     `avp.spawn_subagent` when the model invokes the subagent
    mcp_servers: list[McpServerRef] | None = None
    skills: list[SkillRef] | None = None
    subagents: list[SubagentRef] | None = None

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
    "McpServerRef",
    "SkillRef",
    "SubagentRef",
    "SupervisorPreamble",
]
