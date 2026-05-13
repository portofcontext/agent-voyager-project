"""avp.descriptor — Pydantic types for the AVP Agent Descriptor Spec.

Defines `AgentDescriptor` (the agent's self-description shape) plus the
internal declaration types it carries (`_ToolDecl`, `_SubagentDecl`,
`_SkillDecl`, `_ResourceDecl`). This module mirrors the
[Agent Descriptor spec](../../../../spec/v0.1/agent-descriptor.md).

Consumers wanting only the agent-self-description surface can:

    from avp.descriptor import AgentDescriptor

…without dragging in Trajectory / Commission / Resolver API types.

The built-in declaration types (`_ToolDecl`, `_SubagentDecl`,
`_SkillDecl`, `_ResourceDecl`) are intentionally internal: the
Descriptor's public surface is the top-level `AgentDescriptor` model
which carries lists of them, and downstream typed access goes through
the Pydantic model attributes (`descriptor.built_in_tools[0].name`).
They are imported by `avp.trajectory` for the events that re-use the
same shape (`agent_started.data.tools`, `mcp_server_connected.data.avp.mcp.tools`,
`mcp_server_connected.data.avp.mcp.resources`); the leading underscore
signals "do not depend on these directly from outside the package."
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from avp._envelope import _OPEN, _STRICT


class _ToolDecl(BaseModel):
    """Tool descriptor in `agent_started.data.tools`: MCP-shaped plus AVP fields."""

    model_config = _OPEN
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] | None = Field(default=None, alias="inputSchema")
    avp_dispatch_target: Literal["mcp_server", "local"] | None = Field(
        default=None, alias="avp.dispatch_target"
    )
    avp_mcp_server_id: str | None = Field(default=None, alias="avp.mcp_server_id")


class _SubagentDecl(BaseModel):
    """Subagent descriptor in `agent_started.data.subagents`: what the
    parent model sees when deciding whether to delegate. Same MCP-shaped
    triple (`name`, `description`, `inputSchema`) tools use, so adapters
    can render subagents to the model's tool list with no translation.

    `description` is optional to match `_ToolDecl`: when surfacing a
    agent-built-in subagent (e.g. the Claude Agent SDK's `general-purpose`)
    the agent has authoritative knowledge of the name but not the prose
    description. Honest-null beats authored-prose-that-drifts."""

    model_config = _OPEN
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] | None = Field(default=None, alias="inputSchema")
    avp_agent_type: str | None = Field(default=None, alias="avp.agent_type")


class _SkillDecl(BaseModel):
    """Skill descriptor in `agent_started.data.skills`: name plus
    optional metadata about each skill loaded for the run.

    Replaces the v0.1-prototype `list[str]` shape (names-only) with a
    structured decl matching `_ToolDecl` / `_SubagentDecl`. Description
    comes from the SKILL.md frontmatter when the agent surfaces it
    (e.g. via `ClaudeSDKClient.get_context_usage()` which returns a
    `skills` breakdown including frontmatter); `avp.source` is the
    SKILL.md path / URI when known.

    All fields except `name` are optional so agents that only know
    the name (Commission-declared without enrichment) still emit valid
    decls."""

    model_config = _OPEN
    name: str
    description: str | None = None
    avp_source: str | None = Field(default=None, alias="avp.source")


class _ResourceDecl(BaseModel):
    """MCP resource descriptor in `mcp_server_connected.data.avp.mcp.resources`.

    Mirrors MCP's `Resource` type from the protocol spec; `uri` is the
    primary identifier the agent uses to fetch via `resources/read`,
    `name` and `description` are display/discovery metadata, `mimeType`
    hints at the content format. Skills sourced as `mcp://<server-id>/<path>`
    in `Commission.skills[].avp.source` resolve through this catalog."""

    model_config = _OPEN
    uri: str = Field(min_length=1)
    name: str | None = None
    description: str | None = None
    mimeType: str | None = Field(default=None, alias="mimeType")


class AgentDescriptor(BaseModel):
    """Self-description of an AVP agent: who it is, what it brings.

    Every AVP-compliant agent MUST publish a Descriptor that enumerates
    everything triggerable without supervisor configuration: SDK preset
    tools, runtime-bundled subagents, runtime-bundled skills, plus the
    agent's name / version / supported AVP spec version. Consumers use
    the Descriptor in two ways:

      1. **Pre-flight**: `<agent> describe` prints the Descriptor as
         JSON to stdout. A supervisor authoring a Commission can
         introspect what the agent offers before invoking it.

      2. **On the wire**: the agent emits an `agent_described` event
         right after `run_requested` and right before `agent_started`.
         The on-wire payload MUST equal what `describe` prints for the
         same agent build, so the audit trail records exactly what the
         consumer would have seen at pre-flight time.

    Scope: SDK defaults only. The Descriptor does NOT include
    supervisor-declared surfaces (`Commission.mcp_servers`,
    `Commission.subagents`, `Commission.skills`) and does NOT include
    environment-discovered surfaces (filesystem skills under
    `~/.claude/skills/`, MCP servers discovered at startup,
    user-installed plugins). Those appear on `agent_started` (the
    merged-view event) and `mcp_server_connected` respectively. The
    Descriptor is the agent's identity, not the run's.
    """

    model_config = _STRICT
    agent_name: str = Field(min_length=1)
    agent_version: str = Field(min_length=1)
    avp_spec_version: Literal["0.1"]
    default_model: str | None = None
    # Optional whitelist of models the agent's driver / wrapped SDK can run.
    # Each entry is a glob pattern matched against `Commission.model`
    # (fnmatch semantics): "claude-*" matches any Claude model,
    # "claude-haiku-4-5-*" pins to Haiku 4.5 builds, "gpt-*" matches
    # any GPT. When None, the agent advertises support for any model
    # the supervisor provides, but the driver may still fail at the
    # provider call. When set, an agent SHOULD validate `Commission.model`
    # at startup and emit `error_occurred(code: "unsupported_model")` +
    # `agent_stopped(reason: "error")` before any model turn if the
    # provided model is not matched.
    supported_models: list[str] | None = None
    built_in_tools: list[_ToolDecl] | None = None
    built_in_subagents: list[_SubagentDecl] | None = None
    built_in_skills: list[_SkillDecl] | None = None
    capabilities: list[str] | None = None


__all__ = [
    "AgentDescriptor",
]
