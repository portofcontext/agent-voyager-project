"""avp.descriptor — Pydantic types for the AVP Agent Descriptor Spec.

Defines `AgentDescriptor` (the agent's self-description shape) and the
declaration types it carries: `ToolDecl`, `SubagentDecl`, `SkillDecl`,
`McpServerDecl`, `ResourceDecl`. This module mirrors the
[Agent Descriptor spec](../../../../spec/v0.1/agent-descriptor.md).

Implementors building an `agent_described` event construct
`AgentDescriptor` with typed decl lists:

    from avp.descriptor import AgentDescriptor, ToolDecl

    AgentDescriptor(
        agent_name="my-agent",
        agent_version="1.0.0",
        spec_version="0.1",
        tools=[ToolDecl(name="Read")],
    )

The decl types are also reused by `avp.trajectory` for events that share
the same shape (`agent_started.data["avp.tools"]`,
`mcp_server_connected.data.avp.mcp.tools`,
`mcp_server_connected.data.avp.mcp.resources`).

This module is self-contained: importing from it does not drag in
Trajectory / Commission / Resolver API types.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from avp.envelope import _OPEN, _STRICT


class ToolDecl(BaseModel):
    """Tool descriptor used by `AgentDescriptor.tools`,
    `agent_started.data["avp.tools"]`, and `mcp_server_connected.data.avp.mcp.tools`.

    MCP-shaped: `name` plus optional `description` and `inputSchema`. The
    decl describes a single tool's model-facing identity; how the tool is
    *dispatched* (local vs MCP server) is implicit from where the decl
    appears on the wire — `descriptor.tools` and `agent_started.data["avp.tools"]`
    are local-only; entries under `mcp_server_connected.data.avp.mcp.tools`
    are MCP-dispatched by virtue of being nested under a server. The
    per-invocation discriminator lives on `tool_invoked.data["avp.tool.dispatch_target"]`."""

    model_config = _OPEN
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] | None = Field(default=None, alias="inputSchema")


class SubagentDecl(BaseModel):
    """Subagent descriptor in `agent_started.data["avp.subagents"]`: what the
    parent model sees when deciding whether to delegate. Same MCP-shaped
    triple (`name`, `description`, `inputSchema`) tools use, so adapters
    can render subagents to the model's tool list with no translation.

    `description` is optional to match `ToolDecl`: when surfacing a
    agent-built-in subagent (e.g. the Claude Agent SDK's `general-purpose`)
    the agent has authoritative knowledge of the name but not the prose
    description. Honest-null beats authored-prose-that-drifts."""

    model_config = _OPEN
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] | None = Field(default=None, alias="inputSchema")
    agent_type: str | None = Field(default=None, alias="avp.agent_type")


class SkillDecl(BaseModel):
    """Skill descriptor in `AgentDescriptor.skills` and
    `agent_started.data["avp.skills"]`: name plus optional metadata about each
    skill the agent ships with or has loaded for the run.

    Replaces the v0.1-prototype `list[str]` shape (names-only) with a
    structured decl matching `ToolDecl` / `SubagentDecl`. Description
    comes from the SKILL.md frontmatter when the agent surfaces it
    (e.g. via `ClaudeSDKClient.get_context_usage()` which returns a
    `skills` breakdown including frontmatter); `version` is the skill's
    own version when known; `avp.source` is the SKILL.md path / URI.

    All fields except `name` are optional so agents that only know
    the name (Commission-declared without enrichment) still emit valid
    decls."""

    model_config = _OPEN
    name: str
    description: str | None = None
    version: str | None = None
    source: str | None = Field(default=None, alias="avp.source")


class McpServerDecl(BaseModel):
    """MCP server descriptor in `AgentDescriptor.mcp_servers`: identity only.

    Connection material (URLs, auth, command-lines) stays inside the agent
    process and is NOT carried on the descriptor wire. The descriptor
    records only the server's id, optional display name, and optional
    description; the tools the server surfaces are NOT enumerated on the
    descriptor — they appear at runtime on
    `mcp_server_connected.data["avp.mcp.tools"]`.

    `id` is the agent's correlation key for this server across the wire
    (descriptor entry, `mcp_server_connected` event, tool dispatch). It
    is intentionally looser than `Commission.McpServerRef.id`: the
    descriptor enumerates BOTH Commission-resolved servers (where `id` is
    the supervisor-authored slug) AND agent-baked-in / environment-resident
    servers (where `id` is whatever the environment names them, e.g.
    `"claude.ai Dashboard Builder"`). Forcing a slug here would either
    lose fidelity or require every agent to invent the same slugification
    rule. Commission-authored ids stay slug-clean by virtue of
    `Commission.McpServerRef.id`'s pattern; descriptor ids must only be
    non-empty and must match the `avp.mcp.server_id` the agent later
    surfaces on `mcp_server_connected` so consumers can correlate.

    `name` is the display name when the environment provides one distinct
    from `id` (typical for Commission-resolved servers: `id` is the
    Commission slug, `name` is the human-readable label from the resolved
    config). For environment-resident servers whose only identifier is
    the display name, `id` carries that string and `name` is omitted."""

    model_config = _OPEN
    id: str = Field(min_length=1)
    name: str | None = None
    description: str | None = None


class ResourceDecl(BaseModel):
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
    """Self-description of an AVP agent: the static surface it ships with.

    Identity, capabilities, supported models, system prompt, baked-in user
    prompt (for autonomous agents), MCP servers, tools, skills, subagents.
    Provenance inside the agent doesn't matter on the wire: an SDK preset
    tool (`Grep`), a runtime-bundled skill, and a hand-coded tool are all
    just "what's in the agent" to a Descriptor consumer.

    Two views, normatively the same payload:

      1. **Pre-flight**: `<agent> describe` prints the Descriptor as JSON.
      2. **On the wire**: `agent_described.data["avp.descriptor"]` carries
         the same payload during a run.

    The Descriptor is *static* (identical bytes for the same agent build).
    Anything that varies per invocation (per-call prompt, run_id, thread_id,
    additional supervisor-managed assets) belongs on the Commission, not
    here. Environment-discovered surfaces (filesystem skills under
    `~/.claude/skills/`, plugins, MCP servers discovered at startup) also
    don't appear here; they surface on `agent_started.data.*` and
    `mcp_server_connected` at run time.
    """

    model_config = _STRICT
    agent_name: str = Field(min_length=1)
    agent_version: str = Field(min_length=1)
    spec_version: Literal["0.1"]
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
    # System prompt the agent ships with. Commission.system_prompt overrides
    # when both are set (see spec §2.7).
    system_prompt: str | None = None
    # Baked-in user prompt for autonomous agents (cron-style runs with no
    # per-call user message). Commission.prompt overrides when both are set.
    prompt: str | None = None
    # MCP servers the agent dials at startup. Connection material stays
    # inside the agent process; only identity (id, description) is on the
    # wire. Tools surfaced by these servers are NOT enumerated under
    # `tools` (which is local-only); they appear at runtime on
    # `mcp_server_connected.data["avp.mcp.tools"]`.
    mcp_servers: list[McpServerDecl] | None = None
    tools: list[ToolDecl] | None = None
    subagents: list[SubagentDecl] | None = None
    skills: list[SkillDecl] | None = None
    capabilities: list[str] | None = None


__all__ = [
    "AgentDescriptor",
    "McpServerDecl",
    "ResourceDecl",
    "SkillDecl",
    "SubagentDecl",
    "ToolDecl",
]
