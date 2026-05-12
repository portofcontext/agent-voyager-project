"""Pydantic v2 models for AVP v0.1 wire types.

The wire format is built on:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`, `source`,
  `type`, `subject`, `time`, `datacontenttype`, `data`).
- **OpenTelemetry GenAI** semantic conventions for token / cost / model /
  tool attribute names inside `data` (e.g., `gen_ai.usage.input_tokens`).
- **OpenTelemetry span identification** (`trace_id`, `span_id`,
  `parent_span_id`) so downstream consumers reconstruct the run's span tree.
- **JSON-RPC 2.0** for the AVP Resolver API. The agent calls
  `avp.resolve` (and `avp.spawn_subagent` for managed subagents) against a
  supervisor-stood-up resolver service to dereference opaque refs in
  `Commission.{mcp_servers,skills,subagents}[].ref`.

The Commission carries supervisor-managed assets as opaque refs only;
their resolved material (MCP connection details, skill content, subagent
metadata) is fetched via the Resolver API at startup. Anything the
agent provides on its own (in-process tools, baked-in skills) is invisible
to AVP and surfaced through the agent's Descriptor at run time.

AVP-specific concepts (no-mid-run-reach-in, trajectory contract) live
under the `avp.*` attribute namespace.

See `FOUNDATIONS.md` for the full mapping rationale and the four sub-specs
under `spec/v0.1/` (trajectory, commission, agent-descriptor, resolver) for
normative requirements.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from avp.enums import (
    ErrorCode,
    StopReason,
)

# ── Common helpers ───────────────────────────────────────────────────────────

Iso8601 = str


def now_iso() -> str:
    """ISO 8601 / RFC 3339 timestamp with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def new_event_id() -> str:
    """CloudEvents 1.0 requires `id` unique within `source`. UUID v4 satisfies that."""
    return str(uuid.uuid4())


def new_trace_id() -> str:
    """OTel trace ID: 16 random bytes, hex-encoded (32 lowercase chars)."""
    return secrets.token_hex(16)


def new_span_id() -> str:
    """OTel span ID: 8 random bytes, hex-encoded (16 lowercase chars)."""
    return secrets.token_hex(8)


# 16 zero hex chars: the OTel "absent parent" sentinel for top-level spans.
ZERO_SPAN_ID = "0" * 16


# ── Source URIs and event type names (CloudEvents reverse-DNS) ────────────────

SOURCE_AGENT = "avp://agent"
# `avp://supervisor` is used by the agent-relayed `run_requested` event;
# the agent stamps that source URI on the wire to attribute the run to
# the originating supervisor build (see Commission.supervisor). Supervisors
# do NOT directly emit events into the trajectory in v0.1.
SOURCE_SUPERVISOR = "avp://supervisor"


# Reverse-DNS event types per CloudEvents convention. All AVP-defined types
# live under the `avp.` namespace.
T_RUN_REQUESTED = "avp.run_requested"
T_AGENT_DESCRIBED = "avp.agent_described"
T_AGENT_STARTED = "avp.agent_started"
T_AGENT_STOPPED = "avp.agent_stopped"
T_MODEL_TURN_STARTED = "avp.model_turn_started"
T_MODEL_TURN_ENDED = "avp.model_turn_ended"
T_TOOL_INVOKED = "avp.tool_invoked"
T_TOOL_RETURNED = "avp.tool_returned"
T_TOOL_FAILED = "avp.tool_failed"
T_TEXT_EMITTED = "avp.text_emitted"
T_REASONING_EMITTED = "avp.reasoning_emitted"
T_REFUSAL_RECORDED = "avp.refusal_recorded"
T_COST_RECORDED = "avp.cost_recorded"
T_SKILL_LOADED = "avp.skill_loaded"
T_ERROR_OCCURRED = "avp.error_occurred"
T_MCP_SERVER_CONNECTED = "avp.mcp_server_connected"
T_MCP_SERVER_DISCONNECTED = "avp.mcp_server_disconnected"
T_SUBAGENT_INVOKED = "avp.subagent_invoked"
T_SUBAGENT_RETURNED = "avp.subagent_returned"
T_SUBAGENT_FAILED = "avp.subagent_failed"
T_MANAGED_REF_RESOLVED = "avp.managed_ref_resolved"
T_MANAGED_REF_RESOLVE_FAILED = "avp.managed_ref_resolve_failed"
# Supervisor-sourced bracket event marking a mid-run execution-backend
# swap (trajectory.md §7.3). Peer event; does not restart the span tree.
T_RUN_RESCUED = "avp.run_rescued"


# Pydantic model_config presets. `populate_by_name=True` lets parsers accept
# either the alias (wire form: dotted) or the Python attribute name. `by_alias`
# is passed at serialization time to emit the alias form on the wire.
_STRICT = ConfigDict(extra="forbid", populate_by_name=True, ser_json_omit_default=False)
_OPEN = ConfigDict(extra="allow", populate_by_name=True)


# ── Commission: value objects ─────────────────────────────────────────────────────


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


class RunStateSnapshot(BaseModel):
    """Cumulative run-state used in cost_recorded and agent_stopped data.
    Open model: supervisor SDKs can carry implementation-specific fields."""

    model_config = _OPEN
    total_cost_usd: float = Field(ge=0)
    total_tokens: int = Field(ge=0)
    total_turns: int = Field(ge=0)
    tokens_input_total: int | None = Field(default=None, ge=0)
    tokens_output_total: int | None = Field(default=None, ge=0)
    tokens_cache_read_total: int | None = Field(default=None, ge=0)
    tokens_cache_write_total: int | None = Field(default=None, ge=0)
    tools_invoked: dict[str, int] | None = None
    started_at: Iso8601 | None = None
    duration_ms: int | None = Field(default=None, ge=0)


# ── Supervisor identity (carried into the run_requested prelude) ──────────────


class SupervisorPreamble(BaseModel):
    """Identifies the supervisor that is requesting the run.

    Carried inside `Commission.supervisor` and stamped onto the
    `run_requested` event the agent emits as the first event of the
    trajectory (with `source: avp://supervisor`). Lets a trajectory
    consumer attribute the run to the originating supervisor without an
    out-of-band lookup.

    `name` SHOULD be a stable identifier for the supervisor implementation
    or instance (e.g. `"simple-supervisor-example"`, `"acme.scheduler"`).
    `version` is optional but recommended; it travels with the trajectory
    and lets auditors correlate a run with the exact supervisor build
    that requested it.
    """

    model_config = _STRICT
    name: str = Field(min_length=1)
    version: str | None = None


# ── Commission ────────────────────────────────────────────────────────────────────


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

    # Allow-lists over the agent's manifest-published built-ins. Each list
    # gates the parallel `manifest.built_in_*` surface for this run.
    #
    #   - None (absent) → every built-in of that kind is exposed (default).
    #   - []            → no built-in of that kind is exposed.
    #   - [n1, n2, …]   → only the listed names are exposed; the agent
    #                     hides the rest from the model and runtime-blocks
    #                     any hallucinated invocation with `tool_failed` /
    #                     `subagent_failed`.
    #
    # Names MUST appear in the corresponding manifest list at startup or
    # the agent emits `error_occurred(code: "commission_collision")` and
    # stops with `reason=error`. Has no effect on supervisor-managed
    # assets (those are gated by being-in-the-Commission).
    enabled_builtin_tools: list[str] | None = None
    enabled_builtin_subagents: list[str] | None = None
    enabled_builtin_skills: list[str] | None = None

    output_schema: dict[str, Any] | None = None

    # Agent plane (what the agent runs)
    prompt: str | None = None
    system_prompt: str | None = None
    model: str | None = None

    # Metadata
    thread_id: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None


# ── Data payloads (per-event-type) ────────────────────────────────────────────
#
# Every AVP event's `data` field carries an OTel span triple plus the
# event-type-specific attributes. Field names with dots (the OTel/MCP/JSON-RPC
# wire form) are declared via Pydantic aliases; Python attribute names use
# underscores. `model_dump(by_alias=True)` produces the wire form on emit.


class _SpanData(BaseModel):
    """Span identification carried by every AVP event's `data` payload.

    `extra="allow"` lets vendor-namespaced extension attributes (e.g.,
    `vendor.priority`, `vendor.trace_id`) round-trip through the trajectory
    verbatim. Spec-defined attributes are validated; unknown keys pass through.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    trace_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    span_id: str = Field(min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")
    parent_span_id: str = Field(min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")


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


class RunRequestedData(_SpanData):
    """Payload of avp.run_requested events.

    Anchors the trajectory: the supervisor's assertion that this run was
    requested with this Commission. Agent-relayed (the agent emits the
    event with `source: avp://supervisor` based on `Commission.supervisor`),
    so no I/O contract change beyond Commission, but attribution is the
    supervisor's, not the agent's.

    `avp.commission` is the full Commission snapshot the supervisor handed
    in. Carrying it on the wire makes the trajectory self-contained: an
    auditor can replay (or re-validate) the run from the trajectory
    alone, without an external Commission registry.
    """

    avp_supervisor_name: str = Field(min_length=1, alias="avp.supervisor.name")
    avp_supervisor_version: str | None = Field(default=None, alias="avp.supervisor.version")
    avp_commission: dict[str, Any] = Field(alias="avp.commission")


class AgentDescribedData(_SpanData):
    """Payload of avp.agent_described events.

    The agent's published Descriptor, emitted between `run_requested`
    and `agent_started`. `avp.descriptor` MUST equal what
    `<agent> describe` prints to stdout for the same agent build.
    """

    avp_descriptor: AgentDescriptor = Field(alias="avp.descriptor")


class AgentStartedData(_SpanData):
    """Payload of avp.agent_started events."""

    gen_ai_provider_name: str | None = Field(default=None, alias="gen_ai.provider.name")
    gen_ai_operation_name: Literal["invoke_agent", "chat"] | None = Field(
        default=None, alias="gen_ai.operation.name"
    )
    gen_ai_request_model: str | None = Field(default=None, alias="gen_ai.request.model")
    prompt: str | None = None
    system_prompt: str | None = None
    tools: list[_ToolDecl] | None = None
    skills: list[_SkillDecl] | None = None
    subagents: list[_SubagentDecl] | None = None
    avp_thread_id: str | None = Field(default=None, alias="avp.thread_id")
    avp_session_id: str | None = Field(default=None, alias="avp.session_id")
    avp_tags: list[str] | None = Field(default=None, alias="avp.tags")
    avp_meta: dict[str, Any] | None = Field(default=None, alias="avp.meta")
    avp_schema_version: Literal["0.1"] = Field(default="0.1", alias="avp.schema_version")


class AgentStoppedData(_SpanData):
    avp_reason: StopReason = Field(alias="avp.reason")
    avp_state: RunStateSnapshot = Field(alias="avp.state")
    # Convenience aliases. When non-null these MUST equal the matching
    # field on `avp.state` (validator below enforces). Existed historically
    # as one-hop reads for consumers who only want the headline numbers
    # from the terminator event. New consumers SHOULD read `avp.state.*`
    # instead; it's the canonical surface and the same shape that ships
    # on every `cost_recorded` event. Marked for removal in v0.2.
    avp_total_tokens: int | None = Field(default=None, ge=0, alias="avp.total_tokens")
    avp_total_cost_usd: float | None = Field(default=None, ge=0, alias="avp.total_cost_usd")
    avp_total_turns: int | None = Field(default=None, ge=0, alias="avp.total_turns")
    avp_duration_ms: int | None = Field(default=None, ge=0, alias="avp.duration_ms")
    avp_output: Any | None = Field(default=None, alias="avp.output")

    @model_validator(mode="after")
    def _convenience_aliases_match_state(self) -> AgentStoppedData:
        """The top-level convenience fields MUST agree with `avp.state.*`
        when populated. Catches drift at construction time (so an agent
        that forgets to keep them in sync fails its own validation rather
        than shipping inconsistent events the supervisor has to reconcile)."""
        pairs = [
            ("avp.total_tokens", self.avp_total_tokens, self.avp_state.total_tokens),
            ("avp.total_cost_usd", self.avp_total_cost_usd, self.avp_state.total_cost_usd),
            ("avp.total_turns", self.avp_total_turns, self.avp_state.total_turns),
            ("avp.duration_ms", self.avp_duration_ms, self.avp_state.duration_ms),
        ]
        for alias, top, snap in pairs:
            if top is None or snap is None:
                continue
            if top != snap:
                raise ValueError(
                    f"agent_stopped.{alias}={top!r} disagrees with "
                    f"avp.state.{alias.removeprefix('avp.')}={snap!r}; "
                    "the top-level field MUST equal the snapshot field "
                    "(see spec/v0.1/trajectory.md §7.1). Either populate from the snapshot or "
                    "leave the top-level None."
                )
        return self


class ModelTurnStartedData(_SpanData):
    step: int = Field(ge=0)
    avp_context_messages: int | None = Field(default=None, ge=0, alias="avp.context_messages")
    gen_ai_request_stream: bool | None = Field(default=None, alias="gen_ai.request.stream")


class ModelTurnEndedData(_SpanData):
    step: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    gen_ai_provider_name: str | None = Field(default=None, alias="gen_ai.provider.name")
    gen_ai_request_model: str | None = Field(default=None, alias="gen_ai.request.model")
    gen_ai_response_model: str | None = Field(default=None, alias="gen_ai.response.model")
    gen_ai_response_finish_reasons: list[str] | None = Field(
        default=None, alias="gen_ai.response.finish_reasons"
    )
    gen_ai_response_time_to_first_chunk: float | None = Field(
        default=None, ge=0, alias="gen_ai.response.time_to_first_chunk"
    )
    gen_ai_usage_input_tokens: int = Field(ge=0, alias="gen_ai.usage.input_tokens")
    gen_ai_usage_output_tokens: int = Field(ge=0, alias="gen_ai.usage.output_tokens")
    gen_ai_usage_cache_read_input_tokens: int | None = Field(
        default=None, ge=0, alias="gen_ai.usage.cache_read.input_tokens"
    )
    gen_ai_usage_cache_creation_input_tokens: int | None = Field(
        default=None, ge=0, alias="gen_ai.usage.cache_creation.input_tokens"
    )
    gen_ai_usage_reasoning_output_tokens: int | None = Field(
        default=None, ge=0, alias="gen_ai.usage.reasoning.output_tokens"
    )
    avp_cost_usd: float = Field(ge=0, alias="avp.cost_usd")
    avp_cost_source: Literal["computed", "reported", "unknown"] | None = Field(
        default=None, alias="avp.cost.source"
    )


class ToolInvokedData(_SpanData):
    step: int = Field(ge=0)
    gen_ai_tool_call_id: str = Field(min_length=1, alias="gen_ai.tool.call.id")
    gen_ai_tool_name: str = Field(alias="gen_ai.tool.name")
    gen_ai_tool_call_arguments: dict[str, Any] = Field(alias="gen_ai.tool.call.arguments")
    avp_tool_dispatch_target: Literal["mcp_server", "local"] | None = Field(
        default=None, alias="avp.tool.dispatch_target"
    )


class ToolReturnedData(_SpanData):
    step: int = Field(ge=0)
    gen_ai_tool_call_id: str = Field(min_length=1, alias="gen_ai.tool.call.id")
    gen_ai_tool_name: str = Field(alias="gen_ai.tool.name")
    duration_ms: int = Field(ge=0)
    avp_tool_result_text: str = Field(alias="avp.tool.result.text")
    avp_tool_result_structured: Any | None = Field(default=None, alias="avp.tool.result.structured")
    avp_tool_rejected: bool | None = Field(default=None, alias="avp.tool.rejected")
    avp_tool_rejection_reason: str | None = Field(default=None, alias="avp.tool.rejection_reason")


class ToolFailedData(_SpanData):
    step: int = Field(ge=0)
    gen_ai_tool_call_id: str = Field(min_length=1, alias="gen_ai.tool.call.id")
    gen_ai_tool_name: str = Field(alias="gen_ai.tool.name")
    avp_tool_error: str = Field(alias="avp.tool.error")
    avp_tool_error_code: str | None = Field(default=None, alias="avp.tool.error.code")


class SubagentInvokedData(_SpanData):
    """Parent agent delegates to a declared subagent.

    The event's `span_id` IS the subagent's frame span. Events emitted by
    the subagent's sub-loop set `parent_span_id` to this frame (or chain
    through descendants of it), so the trajectory reconstructs as a nested
    tree. Per OTel GenAI semconv §invoke_agent, `gen_ai.operation.name` is
    `invoke_agent` and `gen_ai.agent.name` carries the subagent's declared
    name.

    `avp.subagent.run_id` is set when the subagent is supervisor-managed:
    the parent's runtime calls `avp.spawn_subagent` and receives the child
    `run_id` of the subagent's separate, independently-trajectoried run.
    Consumers correlate the parent and child trajectories via this field.
    Absent (or null) when the subagent runs in-process (the parent's loop
    is the same process as the subagent's loop).
    """

    step: int = Field(ge=0)
    gen_ai_agent_name: str = Field(alias="gen_ai.agent.name")
    gen_ai_agent_description: str | None = Field(default=None, alias="gen_ai.agent.description")
    gen_ai_operation_name: Literal["invoke_agent"] = Field(
        default="invoke_agent", alias="gen_ai.operation.name"
    )
    avp_subagent_invocation_id: str = Field(min_length=1, alias="avp.subagent.invocation_id")
    avp_subagent_input: dict[str, Any] = Field(alias="avp.subagent.input")
    avp_subagent_run_id: str | None = Field(default=None, min_length=1, alias="avp.subagent.run_id")


class SubagentReturnedData(_SpanData):
    """Closes the subagent's frame. `span_id` matches the corresponding
    `subagent_invoked` event so consumers can pair them. `avp.subagent.usage`
    rolls up the subagent's own consumption (cost, tokens, turns); this
    rollup is also reflected in the parent run's cumulative state, but the
    breakdown is preserved here so consumers can attribute spend to the
    subagent that incurred it."""

    step: int = Field(ge=0)
    gen_ai_agent_name: str = Field(alias="gen_ai.agent.name")
    avp_subagent_invocation_id: str = Field(min_length=1, alias="avp.subagent.invocation_id")
    duration_ms: int = Field(ge=0)
    avp_subagent_result_text: str = Field(alias="avp.subagent.result.text")
    avp_subagent_result_structured: Any | None = Field(
        default=None, alias="avp.subagent.result.structured"
    )
    avp_subagent_reason: StopReason = Field(alias="avp.subagent.reason")
    avp_subagent_usage: RunStateSnapshot = Field(alias="avp.subagent.usage")


class SubagentFailedData(_SpanData):
    """Subagent invocation errored. The parent treats the error as a
    tool-call failure: the model receives an `Error: ...` string in place
    of the result and may retry or proceed."""

    step: int = Field(ge=0)
    gen_ai_agent_name: str = Field(alias="gen_ai.agent.name")
    avp_subagent_invocation_id: str = Field(min_length=1, alias="avp.subagent.invocation_id")
    duration_ms: int = Field(ge=0)
    avp_subagent_error: str = Field(alias="avp.subagent.error")
    avp_subagent_error_code: str | None = Field(default=None, alias="avp.subagent.error.code")


class TextEmittedData(_SpanData):
    step: int = Field(ge=0)
    avp_text: str = Field(alias="avp.text")


class RefusalRecordedData(_SpanData):
    """The model declined to generate a response or had its output filtered.

    Common across providers but each exposes a different slice:
      - Anthropic:  `stop_reason="refusal"` (or `"sensitive"`), no
                    structured category, sometimes a refusal-flavored
                    text block.
      - OpenAI:     `finish_reason="content_filter"` plus a dedicated
                    `refusal` field on the assistant message containing
                    the model's refusal text.
      - Gemini:     `finishReason` enum (`SAFETY`, `RECITATION`,
                    `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`) plus
                    per-category `safetyRatings`.

    AVP normalizes to a provider-agnostic shape: `reason` is the
    provider's raw code (verbatim, so audit pipelines can match exact
    upstream strings), `message` is the model's refusal text when given,
    `category` is the provider's safety category (free-form because
    every provider names them differently), `provider` lets downstream
    consumers normalize the reason code without context-guessing.

    A refusal terminates the turn; the model produced no useful text or
    tool call. Whether the *run* terminates is an agent decision (the
    reference agent stops with `StopReason.refused`); a higher-level
    supervisor may choose to reset history and retry.
    """

    step: int = Field(ge=0)
    avp_refusal_reason: str = Field(min_length=1, alias="avp.refusal.reason")
    avp_refusal_message: str | None = Field(default=None, alias="avp.refusal.message")
    avp_refusal_category: str | None = Field(default=None, alias="avp.refusal.category")
    avp_refusal_provider: str | None = Field(default=None, alias="avp.refusal.provider")


class ReasoningEmittedData(_SpanData):
    """The model produced a reasoning / thinking block during this turn.

    Distinct from `text_emitted`: reasoning is not user-facing output;
    it's the model's internal chain-of-thought that some providers
    expose (Anthropic extended thinking, OpenAI o1/o3 reasoning summaries,
    etc.). Consumers can filter on this event type to redact / collapse
    chain-of-thought from displays without losing it from the audit log.

    `avp.reasoning.signature` rides along when the provider returns a
    cryptographic signature on the thinking block (Anthropic does this
    for redacted_thinking blocks); empty when the provider doesn't.
    `avp.reasoning.redacted` flags blocks the provider has returned in
    encrypted-only form (no plaintext); the wire still records the
    occurrence so audit consumers can count thinking turns.
    """

    step: int = Field(ge=0)
    avp_reasoning_text: str = Field(alias="avp.reasoning.text")
    avp_reasoning_signature: str | None = Field(default=None, alias="avp.reasoning.signature")
    avp_reasoning_redacted: bool | None = Field(default=None, alias="avp.reasoning.redacted")


class CostRecordedData(_SpanData):
    avp_state: RunStateSnapshot = Field(alias="avp.state")
    # Provenance of the snapshot's running cost total. Set to `reported`
    # on the reconciliation event an agent emits after the API/SDK hands
    # back an authoritative total (Claude Agent SDK's
    # ResultMessage.total_cost_usd, etc.). Per-turn cost_recorded events
    # leave it unset because the running total is a mix of per-turn
    # numbers; `avp.cost.source` on each `model_turn_ended` event is
    # the authoritative tag for individual turn costs.
    avp_cost_source: Literal["computed", "reported", "unknown"] | None = Field(
        default=None, alias="avp.cost.source"
    )


class SkillLoadedData(_SpanData):
    """Payload of `avp.skill_loaded` events.

    Semantics: emitted when the SKILL.md body content has been added to
    the model's active context window. NOT a registration acknowledgment
    (the registration view is `agent_started.data.skills[]`).

    Two emission patterns, differentiated by the agent's
    `manifest.capabilities`:

      - `skills:eager`: agent injects all declared SKILL.md bodies at
        startup (e.g., as system_prompt suffix). Emit once per skill at
        `step=0`, after `agent_started` and `mcp_server_connected`.
      - `skills:progressive`: model decides per-turn which skill bodies
        to pull in (Anthropic Skills, Claude Code progressive disclosure).
        Emit when the body actually enters context, with `step=N` matching
        the turn it loaded in. MAY fire multiple times for the same
        skill (e.g., re-load after compaction).

    Agents whose SDK does not expose progressive-disclosure load events
    SHOULD NOT emit `skill_loaded` at all; `agent_started.data.skills[]`
    still records the registration. Honest-silent beats fabricated events.
    """

    step: int = Field(ge=0)
    avp_skill_name: str = Field(alias="avp.skill.name")
    avp_skill_source: str | None = Field(default=None, alias="avp.skill.source")


class ErrorOccurredData(_SpanData):
    avp_error_code: ErrorCode = Field(alias="avp.error.code")
    avp_error_message: str = Field(alias="avp.error.message")


class McpServerConnectedData(_SpanData):
    avp_mcp_server_id: str = Field(min_length=1, alias="avp.mcp.server_id")
    avp_mcp_protocol_version: str = Field(alias="avp.mcp.protocol_version")
    avp_mcp_tool_count: int = Field(ge=0, alias="avp.mcp.tool_count")
    avp_mcp_server_name: str | None = Field(default=None, alias="avp.mcp.server_name")
    avp_mcp_server_version: str | None = Field(default=None, alias="avp.mcp.server_version")
    # Per-server tool list, populated by agents that actually drive the
    # MCP handshake (e.g. avp-claude-agent calling
    # `ClaudeSDKClient.get_mcp_status()` after connect). Null when the
    # agent emits a stub event (e.g. the reference agent; its
    # mcp_server_connected events are placeholders without live transport).
    # Each entry is the same `_ToolDecl` shape used on
    # `agent_started.data.tools`, with `avp.dispatch_target=mcp_server`
    # and `avp.mcp_server_id` matching this event's server id.
    avp_mcp_tools: list[_ToolDecl] | None = Field(default=None, alias="avp.mcp.tools")
    # Live resource catalog from MCP's `resources/list`. Parallel to
    # `avp.mcp.tools`. Populated by agents that drive the MCP handshake;
    # null on stub emitters. Skills declared in `Commission.skills[]` with
    # `avp.source = "mcp://<server-id>/<resource-path>"` resolve against
    # this catalog: the agent calls `resources/read` on the named server
    # before turn 1 to pull the SKILL.md body into the model's context.
    avp_mcp_resources: list[_ResourceDecl] | None = Field(default=None, alias="avp.mcp.resources")
    # SDK-reported connection status, mirroring the Claude Agent SDK's
    # McpServerStatus.status enum. Default null because pre-live-transport
    # stub emitters didn't have this signal.
    avp_mcp_status: Literal["connected", "failed", "needs-auth", "pending", "disabled"] | None = (
        Field(default=None, alias="avp.mcp.status")
    )
    # Error message when status indicates failure (failed / needs-auth).
    # Surfaces the SDK's `error` field verbatim. Null on healthy connects.
    avp_mcp_error: str | None = Field(default=None, alias="avp.mcp.error")


class McpServerDisconnectedData(_SpanData):
    avp_mcp_server_id: str = Field(min_length=1, alias="avp.mcp.server_id")
    avp_mcp_disconnect_reason: Literal["clean", "error"] = Field(alias="avp.mcp.disconnect_reason")
    avp_mcp_disconnect_message: str | None = Field(default=None, alias="avp.mcp.disconnect_message")


# Kinds of asset the AVP resolver protocol can dereference. Carried on
# `managed_ref_resolved` / `managed_ref_resolve_failed` events to discriminate
# which asset class the resolution was for.
ManagedKind = Literal["mcp_server", "skill", "subagent"]


class ManagedRefResolvedData(_SpanData):
    """Audit event emitted when the agent successfully resolves one
    Commission-declared managed-asset ref via the AVP resolver protocol.

    Fires once per `Commission.{mcp_servers,skills,subagents}[]` entry the
    agent dereferences. For mcp_servers and skills the resolution is
    startup-only; for subagents this fires for the metadata-resolve at
    startup (the on-demand spawn at runtime is recorded on
    `subagent_invoked` instead). The opaque ref material is NOT re-recorded
    here; `run_requested.data["avp.commission"]` already has it. This
    event records only that the round-trip happened.
    """

    avp_managed_kind: ManagedKind = Field(alias="avp.managed.kind")
    avp_managed_id: str = Field(min_length=1, alias="avp.managed.id")
    duration_ms: int = Field(ge=0)


class ManagedRefResolveFailedData(_SpanData):
    """The resolver returned an error or could not be reached for one of
    the Commission's managed-asset refs. The agent MUST stop with
    `agent_stopped(reason: "error")` after emitting this event. Startup
    resolution is fail-fast (see `spec/v0.1/resolver.md` §5)."""

    avp_managed_kind: ManagedKind = Field(alias="avp.managed.kind")
    avp_managed_id: str = Field(min_length=1, alias="avp.managed.id")
    avp_resolve_error: str = Field(min_length=1, alias="avp.resolve.error")
    avp_resolve_error_code: str | None = Field(default=None, alias="avp.resolve.error.code")


class RunRescuedEndpoint(BaseModel):
    """One side of an `avp.run_rescued` event — describes either the
    runner the supervisor is swapping away from or the one it's
    swapping to. See trajectory.md §7.3."""

    model_config = _STRICT
    backend: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    model: str | None = Field(default=None, min_length=1)


class RunRescuedData(BaseModel):
    """`avp.run_rescued` payload. Peer event in the trajectory inserted
    by the supervisor between a failed runner's last event and the new
    runner's first event. Does not restart the span tree; the new
    runner continues the agent span opened by the original
    `agent_started`. Same `run_id` across the swap."""

    model_config = _STRICT
    from_endpoint: RunRescuedEndpoint = Field(alias="from")
    to_endpoint: RunRescuedEndpoint = Field(alias="to")
    reason: str = Field(min_length=1)
    last_completed_seq: int = Field(ge=0)


# ── CloudEvents 1.0 envelope (event types) ────────────────────────────────────
#
# Each event is a CloudEvent. `type` discriminates the union. `source` is the
# producer URI. `subject` carries the run_id. `data` carries the typed payload.


class _CloudEventBase(BaseModel):
    """Shared CloudEvents 1.0 envelope fields. Specific events override
    `type` and `source` with Literal constants and define `data: <Type>Data`.

    Per CloudEvents §1: required `specversion`, `id`, `source`, `type`.
    Optional: `subject`, `time`, `datacontenttype`, `dataschema`. AVP uses
    `subject` to carry run_id.
    """

    model_config = _STRICT
    specversion: Literal["1.0"] = "1.0"
    id: str = Field(min_length=1, default_factory=new_event_id)
    time: Iso8601 = Field(default_factory=now_iso)
    subject: str | None = Field(default=None, min_length=1)  # run_id
    datacontenttype: str | None = "application/json"
    dataschema: str | None = None
    avp_correlation_id: str | None = Field(default=None, min_length=1, alias="avp.correlation_id")


class RunRequestedEvent(_CloudEventBase):
    """First event of the trajectory. Agent-relayed but supervisor-attributed:
    the agent emits it from `Commission.supervisor` with `source: avp://supervisor`,
    so a downstream consumer reading the wire sees the supervisor as the
    asserter of "this run was requested with this Commission." Same relay
    pattern as `tool_exec_resolved`.
    """

    type: Literal["avp.run_requested"] = T_RUN_REQUESTED
    source: Literal["avp://supervisor"] = SOURCE_SUPERVISOR
    data: RunRequestedData


class AgentDescribedEvent(_CloudEventBase):
    """Second event of the trajectory. The agent's "whoami":
    self-published manifest of everything triggerable without supervisor
    configuration. Carries the same JSON `<agent> describe` prints to
    stdout for this agent build.
    """

    type: Literal["avp.agent_described"] = T_AGENT_DESCRIBED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: AgentDescribedData


class AgentStartedEvent(_CloudEventBase):
    type: Literal["avp.agent_started"] = T_AGENT_STARTED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: AgentStartedData


class AgentStoppedEvent(_CloudEventBase):
    type: Literal["avp.agent_stopped"] = T_AGENT_STOPPED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: AgentStoppedData


class ModelTurnStartedEvent(_CloudEventBase):
    type: Literal["avp.model_turn_started"] = T_MODEL_TURN_STARTED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ModelTurnStartedData


class ModelTurnEndedEvent(_CloudEventBase):
    type: Literal["avp.model_turn_ended"] = T_MODEL_TURN_ENDED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ModelTurnEndedData


class ToolInvokedEvent(_CloudEventBase):
    type: Literal["avp.tool_invoked"] = T_TOOL_INVOKED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ToolInvokedData


class ToolReturnedEvent(_CloudEventBase):
    type: Literal["avp.tool_returned"] = T_TOOL_RETURNED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ToolReturnedData


class ToolFailedEvent(_CloudEventBase):
    type: Literal["avp.tool_failed"] = T_TOOL_FAILED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ToolFailedData


class SubagentInvokedEvent(_CloudEventBase):
    type: Literal["avp.subagent_invoked"] = T_SUBAGENT_INVOKED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: SubagentInvokedData


class SubagentReturnedEvent(_CloudEventBase):
    type: Literal["avp.subagent_returned"] = T_SUBAGENT_RETURNED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: SubagentReturnedData


class SubagentFailedEvent(_CloudEventBase):
    type: Literal["avp.subagent_failed"] = T_SUBAGENT_FAILED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: SubagentFailedData


class TextEmittedEvent(_CloudEventBase):
    type: Literal["avp.text_emitted"] = T_TEXT_EMITTED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: TextEmittedData


class ReasoningEmittedEvent(_CloudEventBase):
    type: Literal["avp.reasoning_emitted"] = T_REASONING_EMITTED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ReasoningEmittedData


class RefusalRecordedEvent(_CloudEventBase):
    type: Literal["avp.refusal_recorded"] = T_REFUSAL_RECORDED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: RefusalRecordedData


class CostRecordedEvent(_CloudEventBase):
    type: Literal["avp.cost_recorded"] = T_COST_RECORDED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: CostRecordedData


class SkillLoadedEvent(_CloudEventBase):
    type: Literal["avp.skill_loaded"] = T_SKILL_LOADED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: SkillLoadedData


class ErrorOccurredEvent(_CloudEventBase):
    type: Literal["avp.error_occurred"] = T_ERROR_OCCURRED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ErrorOccurredData


class McpServerConnectedEvent(_CloudEventBase):
    type: Literal["avp.mcp_server_connected"] = T_MCP_SERVER_CONNECTED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: McpServerConnectedData


class McpServerDisconnectedEvent(_CloudEventBase):
    type: Literal["avp.mcp_server_disconnected"] = T_MCP_SERVER_DISCONNECTED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: McpServerDisconnectedData


class ManagedRefResolvedEvent(_CloudEventBase):
    type: Literal["avp.managed_ref_resolved"] = T_MANAGED_REF_RESOLVED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ManagedRefResolvedData


class ManagedRefResolveFailedEvent(_CloudEventBase):
    type: Literal["avp.managed_ref_resolve_failed"] = T_MANAGED_REF_RESOLVE_FAILED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ManagedRefResolveFailedData


class RunRescuedEvent(_CloudEventBase):
    """Supervisor-sourced peer event marking a mid-run execution-backend
    swap. The second supervisor-attributed event type in v0.1 alongside
    `run_requested`. See trajectory.md §7.3."""

    type: Literal["avp.run_rescued"] = T_RUN_RESCUED
    source: Literal["avp://supervisor"] = SOURCE_SUPERVISOR
    data: RunRescuedData


# ── Discriminated unions ──────────────────────────────────────────────────────


_AGENT_EVENT_TYPES = (
    RunRequestedEvent,
    AgentDescribedEvent,
    AgentStartedEvent,
    AgentStoppedEvent,
    ModelTurnStartedEvent,
    ModelTurnEndedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    ToolFailedEvent,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    SubagentFailedEvent,
    TextEmittedEvent,
    ReasoningEmittedEvent,
    RefusalRecordedEvent,
    CostRecordedEvent,
    SkillLoadedEvent,
    ErrorOccurredEvent,
    McpServerConnectedEvent,
    McpServerDisconnectedEvent,
    ManagedRefResolvedEvent,
    ManagedRefResolveFailedEvent,
    RunRescuedEvent,
)

Event = Annotated[
    RunRequestedEvent
    | AgentDescribedEvent
    | AgentStartedEvent
    | AgentStoppedEvent
    | ModelTurnStartedEvent
    | ModelTurnEndedEvent
    | ToolInvokedEvent
    | ToolReturnedEvent
    | ToolFailedEvent
    | SubagentInvokedEvent
    | SubagentReturnedEvent
    | SubagentFailedEvent
    | TextEmittedEvent
    | ReasoningEmittedEvent
    | RefusalRecordedEvent
    | CostRecordedEvent
    | SkillLoadedEvent
    | ErrorOccurredEvent
    | McpServerConnectedEvent
    | McpServerDisconnectedEvent
    | ManagedRefResolvedEvent
    | ManagedRefResolveFailedEvent
    | RunRescuedEvent,
    Field(discriminator="type"),
]

_TYPE_TO_MODEL: dict[str, type[BaseModel]] = {}
for _cls in _AGENT_EVENT_TYPES:
    _TYPE_TO_MODEL[_cls.model_fields["type"].default] = _cls


# Required CloudEvents-envelope fields every parsed event MUST carry, even
# unknown (custom) event types. Per CloudEvents §1.
_REQUIRED_ENVELOPE_FIELDS = ("specversion", "id", "source", "type", "time", "data")


def parse_event(payload: dict[str, Any]) -> BaseModel | dict[str, Any]:
    """Parse an agent-emitted event payload.

    Known types validate against their Pydantic model. Unknown types pass
    through as a dict (per spec/v0.1/README.md §4: consumers MUST pass through unknown
    types without error), provided they carry the CloudEvents-required
    envelope fields.
    """
    t = payload.get("type")
    if not isinstance(t, str):
        raise ValueError("event payload missing required 'type' string")
    cls = _TYPE_TO_MODEL.get(t)
    if cls is None:
        for required in _REQUIRED_ENVELOPE_FIELDS:
            if required not in payload:
                raise ValueError(
                    f"custom event {t!r} missing required CloudEvents field {required!r}"
                )
        return dict(payload)
    return cls.model_validate(payload)


def event_to_wire(event: BaseModel) -> dict[str, Any]:
    """Serialize an event Pydantic model to the wire-form dict.

    Always uses aliases (the dotted forms like `gen_ai.usage.input_tokens`)
    so the output is what consumers see on the wire.
    """
    return event.model_dump(by_alias=True, exclude_none=True, mode="json")
