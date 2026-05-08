"""Pydantic v2 models for AEP v0.1 wire types.

The wire format is built on:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`, `source`,
  `type`, `subject`, `time`, `datacontenttype`, `data`).
- **OpenTelemetry GenAI** semantic conventions for token / cost / model /
  tool attribute names inside `data` (e.g., `gen_ai.usage.input_tokens`).
- **OpenTelemetry span identification** (`trace_id`, `span_id`,
  `parent_span_id`) so downstream consumers reconstruct the run's span tree.
- **JSON-RPC 2.0** for the RPC payloads inside `tool_exec_request.data` /
  `tool_exec_resolved.data`.
- **MCP** tool descriptors for `Config.tools[]` (camelCase `inputSchema`).
- **Agent Skills** for `SKILL.md` referenced by `Config.skills[]`.

AEP-specific concepts (verifier, boundary, no-mid-run-reach-in, trajectory
contract) live under the `aep.*` attribute namespace.

See `FOUNDATIONS.md` for the full mapping rationale and `SPEC.md` for
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
    field_validator,
    model_validator,
)

from aep.enums import (
    BUILT_IN_VERIFIER_TRIGGERS,
    ErrorCode,
    OnFailure,
    StopReason,
    VerifierError,
    is_on_tool_trigger,
    is_pre_tool_trigger,
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


# 16 zero hex chars — the OTel "absent parent" sentinel for top-level spans.
ZERO_SPAN_ID = "0" * 16


# ── Source URIs and event type names (CloudEvents reverse-DNS) ────────────────

SOURCE_RUNNER = "aep://runner"
SOURCE_SUPERVISOR = "aep://supervisor"


def source_for_mcp(server_id: str) -> str:
    """Source URI for an external MCP server's RPC reply."""
    return f"aep://mcp/{server_id}"


# Reverse-DNS event types per CloudEvents convention. All AEP-defined types
# live under the `aep.` namespace.
T_AGENT_STARTED = "aep.agent_started"
T_AGENT_STOPPED = "aep.agent_stopped"
T_MODEL_TURN_STARTED = "aep.model_turn_started"
T_MODEL_TURN_ENDED = "aep.model_turn_ended"
T_TOOL_INVOKED = "aep.tool_invoked"
T_TOOL_RETURNED = "aep.tool_returned"
T_TOOL_FAILED = "aep.tool_failed"
T_TEXT_EMITTED = "aep.text_emitted"
T_REASONING_EMITTED = "aep.reasoning_emitted"
T_REFUSAL_RECORDED = "aep.refusal_recorded"
T_COST_RECORDED = "aep.cost_recorded"
T_SKILL_LOADED = "aep.skill_loaded"
T_SKILL_EXECUTED = "aep.skill_executed"
T_ERROR_OCCURRED = "aep.error_occurred"
T_TOOL_EXEC_REQUEST = "aep.tool_exec_request"
T_TOOL_EXEC_RESOLVED = "aep.tool_exec_resolved"
T_TOOL_EXEC_TIMED_OUT = "aep.tool_exec_timed_out"
T_VERIFIER_EVALUATED = "aep.verifier_evaluated"
T_MCP_SERVER_CONNECTED = "aep.mcp_server_connected"
T_MCP_SERVER_DISCONNECTED = "aep.mcp_server_disconnected"
T_SUBAGENT_INVOKED = "aep.subagent_invoked"
T_SUBAGENT_RETURNED = "aep.subagent_returned"
T_SUBAGENT_FAILED = "aep.subagent_failed"
T_APPROVAL_REQUESTED = "aep.approval_requested"
T_APPROVAL_RESOLVED = "aep.approval_resolved"


# Pydantic model_config presets. `populate_by_name=True` lets parsers accept
# either the alias (wire form: dotted) or the Python attribute name. `by_alias`
# is passed at serialization time to emit the alias form on the wire.
_STRICT = ConfigDict(extra="forbid", populate_by_name=True, ser_json_omit_default=False)
_OPEN = ConfigDict(extra="allow", populate_by_name=True)


# ── Config: value objects ─────────────────────────────────────────────────────


class Boundary(BaseModel):
    """Hard limits the agent enforces. Strict-greater per SPEC §9.2.

    Cost / tokens / duration are CONSUMPTION boundaries — checked after
    each turn and tool, and may overshoot a max by one final event because
    the cost/token spend of the next call can't be projected pre-call.
    Step is a PROJECTION boundary — checked before starting the next turn,
    so `max_steps: N` runs EXACTLY N turns.
    """

    model_config = _STRICT
    max_cost_usd: float | None = Field(default=None, gt=0)
    max_steps: int | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, gt=0)
    max_duration_seconds: float | None = Field(default=None, gt=0)


class Skill(BaseModel):
    """Reference to a SKILL.md following the agentskills.io specification.

    `name` MUST follow agentskills.io rules (1-64 chars, lowercase a-z digits
    hyphens, no leading/trailing hyphen, no consecutive hyphens). The
    `aep_source` and `aep_config` fields are AEP extensions; agentskills.io
    doesn't define a remote-load scheme.
    """

    model_config = _STRICT
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    aep_source: str = Field(alias="aep.source", min_length=1)
    aep_config: dict[str, Any] | None = Field(default=None, alias="aep.config")


class Tool(BaseModel):
    """MCP-shaped tool descriptor. Per the MCP 2025-11-25 spec.

    `inputSchema` and `outputSchema` are camelCase per MCP. The optional
    `_meta.aep.timeout_ms` is AEP's extension (MCP defines `_meta` as the
    extension slot).
    """

    model_config = _STRICT
    name: str = Field(min_length=1)
    description: str | None = None
    title: str | None = None
    inputSchema: dict[str, Any] = Field(alias="inputSchema")  # camelCase per MCP
    outputSchema: dict[str, Any] | None = Field(default=None, alias="outputSchema")
    meta: dict[str, Any] | None = Field(default=None, alias="_meta")


class VerifierSourceShell(BaseModel):
    """Shell-source verifier: pass/fail comes from the exit code of a
    subprocess. Deterministic; runs in-process on the runner's host."""

    model_config = _STRICT
    shell: str


class _ApprovalSpec(BaseModel):
    """The body of `{approval: {...}}` — the prompt and any future
    knobs that describe what the supervisor is being asked to approve."""

    model_config = _STRICT
    prompt: str | None = None


class VerifierSourceApproval(BaseModel):
    """Approval-source verifier: pass/fail comes from the supervisor's
    response to an `aep.approval_requested` RPC. Used at gate triggers
    (typically `pre_tool:<name>`) where a human or policy decides
    whether the agent proceeds. Approved → pass; denied or timed-out →
    fail. Distinct from shell sources because the decision is non-
    deterministic and originates outside the runner."""

    model_config = _STRICT
    approval: _ApprovalSpec


# Untagged discriminated union: each variant has a distinct top-level
# field (`shell` vs `approval`) so Pydantic resolves it unambiguously.
VerifierSource = VerifierSourceShell | VerifierSourceApproval


class Verifier(BaseModel):
    """Declarative check at a trigger point. AEP-specific (no upstream).

    Two reaction polarities:
      - `on_failure` (default `continue`): action when the check FAILS.
        The common case — invariants that fail trigger correction or halt.
      - `on_success` (default `continue`): action when the check PASSES.
        Use `on_success: halt` for declarative convergence — "stop when
        this condition is met". Halt-on-success terminates with
        `reason=converged`; halt-on-failure terminates with
        `reason=verifier_failed`.

    Sources:
      - `{shell: "..."}` — deterministic subprocess; exit 0 = pass.
      - `{approval: {prompt?: "..."}}` — pings the supervisor for a
        human or policy decision via the `approval_requested` /
        `approval_resolved` RPC pair. Approved = pass; denied or timed
        out = fail. Use with `pre_tool:<name>` triggers for human-in-
        the-loop gates on destructive actions.

    A check can set both: e.g. `on_success: halt` + `on_failure: continue`
    means "halt when this passes, otherwise keep going". Setting both to
    `halt` is allowed but unusual (halts no matter what — useful for
    forced checkpoints).
    """

    model_config = _STRICT
    name: str = Field(min_length=1)
    trigger: str
    source: VerifierSource
    on_failure: OnFailure = OnFailure.continue_
    on_success: OnFailure = OnFailure.continue_
    correction_message: str | None = None
    timeout_ms: int = Field(default=30000, gt=0)

    @field_validator("trigger")
    @classmethod
    def _validate_trigger(cls, v: str) -> str:
        if v in BUILT_IN_VERIFIER_TRIGGERS or is_on_tool_trigger(v) or is_pre_tool_trigger(v):
            return v
        raise ValueError(
            f"verifier trigger {v!r} must be one of "
            f"{sorted(BUILT_IN_VERIFIER_TRIGGERS)}, 'on_tool:<name>', "
            f"or 'pre_tool:<name>'"
        )

    @model_validator(mode="after")
    def _inject_correction_requires_message(self) -> Verifier:
        if (
            self.on_failure == OnFailure.inject_correction
            or self.on_success == OnFailure.inject_correction
        ) and not self.correction_message:
            raise ValueError(
                "Verifier.correction_message is required when "
                "on_failure or on_success is 'inject_correction'"
            )
        return self


class McpHttpAuth(BaseModel):
    """Auth for an MCP server reachable via HTTP."""

    model_config = _STRICT
    type: Literal["bearer"] = "bearer"
    token_env: str = Field(min_length=1)


class McpServer(BaseModel):
    """External MCP server endpoint. The runner connects, runs initialize +
    tools/list, and merges returned tools into the effective surface."""

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=r"^[a-z0-9_-]+$")
    transport: Literal["http", "stdio"]
    # http transport
    url: str | None = None
    auth: McpHttpAuth | None = None
    # stdio transport
    command: list[str] | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    # common
    init_timeout_ms: int = Field(default=30000, gt=0)
    meta: dict[str, Any] | None = Field(default=None, alias="_meta")

    @model_validator(mode="after")
    def _transport_fields_consistent(self) -> McpServer:
        if self.transport == "http":
            if not self.url:
                raise ValueError("McpServer with transport='http' requires `url`")
            if self.command or self.args or self.env:
                raise ValueError("McpServer with transport='http' cannot set stdio fields")
        elif self.transport == "stdio":
            if not self.command:
                raise ValueError("McpServer with transport='stdio' requires `command`")
            if self.url or self.auth:
                raise ValueError("McpServer with transport='stdio' cannot set http fields")
        return self


class Subagent(BaseModel):
    """Declares a sub-agent the parent can delegate to.

    Sits alongside `tools` and `skills` as a top-level Config primitive: the
    supervisor declares the full set of subagents up front, the parent agent
    invokes one by name at runtime. The model surface is MCP-shaped (`name`,
    `description`, `inputSchema`) so the model sees a subagent the same way
    it sees a tool. The wire surface is its own lifecycle —
    `subagent_invoked` / `subagent_returned` / `subagent_failed` — so
    nested turns and tool calls observe as their own span tree rather than
    flatten into a single tool call.

    A Subagent carries an environment slice that mirrors Config (its own
    `system_prompt`, `model`, `tools`, `skills`, `verifiers`, `boundary`,
    `output_schema`). The subagent runs in a fresh conversation —
    `inherit_tools=False` by default (matches Google ADK; safer than the
    Claude Agent SDK default of inheriting). Skills and prompt context are
    never inherited.
    """

    model_config = _STRICT
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    description: str = Field(min_length=1)
    inputSchema: dict[str, Any] | None = Field(default=None, alias="inputSchema")

    system_prompt: str | None = None
    model: str | None = None

    inherit_tools: bool = False
    allowed_tools: list[str] | None = None
    tools: list[Tool] | None = None
    mcp_servers: list[McpServer] | None = None
    skills: list[Skill] | None = None
    verifiers: list[Verifier] | None = None
    boundary: Boundary | None = None
    output_schema: dict[str, Any] | None = None

    subagents: list[Subagent] | None = None


class RunStateSnapshot(BaseModel):
    """Cumulative run-state used in cost_recorded and agent_stopped data.
    Open model — supervisor SDKs can carry implementation-specific fields."""

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


# ── Config ────────────────────────────────────────────────────────────────────


class Config(BaseModel):
    """Supervisor's complete declaration of the agent's environment."""

    model_config = _STRICT

    schema_version: Literal["0.1"]
    run_id: str = Field(min_length=1)

    # Supervisor plane (the environment)
    tools: list[Tool] | None = None
    mcp_servers: list[McpServer] | None = None
    allowed_tools: list[str] | None = None
    verifiers: list[Verifier] | None = None
    boundary: Boundary | None = None
    output_schema: dict[str, Any] | None = None
    subagents: list[Subagent] | None = None

    # Runner plane (what the agent runs)
    prompt: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    skills: list[Skill] | None = None

    # Metadata
    thread_id: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None


# ── Data payloads (per-event-type) ────────────────────────────────────────────
#
# Every AEP event's `data` field carries an OTel span triple plus the
# event-type-specific attributes. Field names with dots (the OTel/MCP/JSON-RPC
# wire form) are declared via Pydantic aliases; Python attribute names use
# underscores. `model_dump(by_alias=True)` produces the wire form on emit.


class _SpanData(BaseModel):
    """Span identification carried by every AEP event's `data` payload.

    `extra="allow"` lets vendor-namespaced extension attributes (e.g.,
    `vendor.priority`, `vendor.trace_id`) round-trip through the trajectory
    verbatim. Spec-defined attributes are validated; unknown keys pass through.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    trace_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    span_id: str = Field(min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")
    parent_span_id: str = Field(min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")


class _ToolDecl(BaseModel):
    """Tool descriptor in `agent_started.data.tools` — MCP-shaped + AEP fields."""

    model_config = _OPEN
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] | None = Field(default=None, alias="inputSchema")
    aep_dispatch_target: Literal["supervisor_rpc", "mcp_server", "local"] | None = Field(
        default=None, alias="aep.dispatch_target"
    )
    aep_mcp_server_id: str | None = Field(default=None, alias="aep.mcp_server_id")


class _SubagentDecl(BaseModel):
    """Subagent descriptor in `agent_started.data.subagents` — what the
    parent model sees when deciding whether to delegate. Same MCP-shaped
    triple (`name`, `description`, `inputSchema`) tools use, so adapters
    can render subagents to the model's tool list with no translation.

    `description` is optional to match `_ToolDecl`: when surfacing a
    runner-built-in subagent (e.g. the Claude Agent SDK's `general-purpose`)
    the runner has authoritative knowledge of the name but not the prose
    description. Honest-null beats authored-prose-that-drifts."""

    model_config = _OPEN
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] | None = Field(default=None, alias="inputSchema")


class AgentStartedData(_SpanData):
    """Payload of aep.agent_started events."""

    gen_ai_provider_name: str | None = Field(default=None, alias="gen_ai.provider.name")
    gen_ai_operation_name: Literal["invoke_agent", "chat"] | None = Field(
        default=None, alias="gen_ai.operation.name"
    )
    gen_ai_request_model: str | None = Field(default=None, alias="gen_ai.request.model")
    prompt: str | None = None
    system_prompt: str | None = None
    tools: list[_ToolDecl] | None = None
    skills: list[str] | None = None
    subagents: list[_SubagentDecl] | None = None
    aep_thread_id: str | None = Field(default=None, alias="aep.thread_id")
    aep_session_id: str | None = Field(default=None, alias="aep.session_id")
    aep_tags: list[str] | None = Field(default=None, alias="aep.tags")
    aep_meta: dict[str, Any] | None = Field(default=None, alias="aep.meta")
    aep_schema_version: Literal["0.1"] = Field(default="0.1", alias="aep.schema_version")


class AgentStoppedData(_SpanData):
    aep_reason: StopReason = Field(alias="aep.reason")
    aep_state: RunStateSnapshot = Field(alias="aep.state")
    # Convenience aliases. When non-null these MUST equal the matching
    # field on `aep.state` (validator below enforces). Existed historically
    # as one-hop reads for consumers who only want the headline numbers
    # from the terminator event. New consumers SHOULD read `aep.state.*`
    # instead — it's the canonical surface and the same shape that ships
    # on every `cost_recorded` event. Marked for removal in v0.2.
    aep_total_tokens: int | None = Field(default=None, ge=0, alias="aep.total_tokens")
    aep_total_cost_usd: float | None = Field(default=None, ge=0, alias="aep.total_cost_usd")
    aep_total_turns: int | None = Field(default=None, ge=0, alias="aep.total_turns")
    aep_duration_ms: int | None = Field(default=None, ge=0, alias="aep.duration_ms")
    aep_output: Any | None = Field(default=None, alias="aep.output")

    @model_validator(mode="after")
    def _convenience_aliases_match_state(self) -> AgentStoppedData:
        """The top-level convenience fields MUST agree with `aep.state.*`
        when populated. Catches drift at construction time (so a runner
        that forgets to keep them in sync fails its own validation rather
        than shipping inconsistent events the supervisor has to reconcile)."""
        pairs = [
            ("aep.total_tokens", self.aep_total_tokens, self.aep_state.total_tokens),
            ("aep.total_cost_usd", self.aep_total_cost_usd, self.aep_state.total_cost_usd),
            ("aep.total_turns", self.aep_total_turns, self.aep_state.total_turns),
            ("aep.duration_ms", self.aep_duration_ms, self.aep_state.duration_ms),
        ]
        for alias, top, snap in pairs:
            if top is None or snap is None:
                continue
            if top != snap:
                raise ValueError(
                    f"agent_stopped.{alias}={top!r} disagrees with "
                    f"aep.state.{alias.removeprefix('aep.')}={snap!r}; "
                    "the top-level field MUST equal the snapshot field "
                    "(see SPEC §11.1). Either populate from the snapshot or "
                    "leave the top-level None."
                )
        return self


class ModelTurnStartedData(_SpanData):
    step: int = Field(ge=0)
    aep_context_messages: int | None = Field(default=None, ge=0, alias="aep.context_messages")
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
    aep_cost_usd: float = Field(ge=0, alias="aep.cost_usd")
    aep_cost_source: Literal["computed", "reported", "unknown"] | None = Field(
        default=None, alias="aep.cost.source"
    )


class ToolInvokedData(_SpanData):
    step: int = Field(ge=0)
    gen_ai_tool_call_id: str = Field(min_length=1, alias="gen_ai.tool.call.id")
    gen_ai_tool_name: str = Field(alias="gen_ai.tool.name")
    gen_ai_tool_call_arguments: dict[str, Any] = Field(alias="gen_ai.tool.call.arguments")
    aep_tool_dispatch_target: Literal["supervisor_rpc", "mcp_server", "local"] | None = Field(
        default=None, alias="aep.tool.dispatch_target"
    )
    aep_tool_subtype: str | None = Field(default=None, alias="aep.tool.subtype")


class ToolReturnedData(_SpanData):
    step: int = Field(ge=0)
    gen_ai_tool_call_id: str = Field(min_length=1, alias="gen_ai.tool.call.id")
    gen_ai_tool_name: str = Field(alias="gen_ai.tool.name")
    duration_ms: int = Field(ge=0)
    aep_tool_result_text: str = Field(alias="aep.tool.result.text")
    aep_tool_result_structured: Any | None = Field(default=None, alias="aep.tool.result.structured")
    aep_tool_rejected: bool | None = Field(default=None, alias="aep.tool.rejected")
    aep_tool_rejection_reason: str | None = Field(default=None, alias="aep.tool.rejection_reason")


class ToolFailedData(_SpanData):
    step: int = Field(ge=0)
    gen_ai_tool_call_id: str = Field(min_length=1, alias="gen_ai.tool.call.id")
    gen_ai_tool_name: str = Field(alias="gen_ai.tool.name")
    aep_tool_error: str = Field(alias="aep.tool.error")
    aep_tool_error_code: int | None = Field(default=None, alias="aep.tool.error.code")


class SubagentInvokedData(_SpanData):
    """Parent agent delegates to a declared subagent.

    The event's `span_id` IS the subagent's frame span. Events emitted by
    the subagent's sub-loop set `parent_span_id` to this frame (or chain
    through descendants of it), so the trajectory reconstructs as a nested
    tree. Per OTel GenAI semconv §invoke_agent, `gen_ai.operation.name` is
    `invoke_agent` and `gen_ai.agent.name` carries the subagent's declared
    name.
    """

    step: int = Field(ge=0)
    gen_ai_agent_name: str = Field(alias="gen_ai.agent.name")
    gen_ai_agent_description: str | None = Field(default=None, alias="gen_ai.agent.description")
    gen_ai_operation_name: Literal["invoke_agent"] = Field(
        default="invoke_agent", alias="gen_ai.operation.name"
    )
    aep_subagent_invocation_id: str = Field(min_length=1, alias="aep.subagent.invocation_id")
    aep_subagent_input: dict[str, Any] = Field(alias="aep.subagent.input")


class SubagentReturnedData(_SpanData):
    """Closes the subagent's frame. `span_id` matches the corresponding
    `subagent_invoked` event so consumers can pair them. `aep.subagent.usage`
    rolls up the subagent's own consumption (cost, tokens, turns) — this
    rollup is also reflected in the parent run's cumulative state, but the
    breakdown is preserved here so consumers can attribute spend to the
    subagent that incurred it."""

    step: int = Field(ge=0)
    gen_ai_agent_name: str = Field(alias="gen_ai.agent.name")
    aep_subagent_invocation_id: str = Field(min_length=1, alias="aep.subagent.invocation_id")
    duration_ms: int = Field(ge=0)
    aep_subagent_result_text: str = Field(alias="aep.subagent.result.text")
    aep_subagent_result_structured: Any | None = Field(
        default=None, alias="aep.subagent.result.structured"
    )
    aep_subagent_reason: StopReason = Field(alias="aep.subagent.reason")
    aep_subagent_usage: RunStateSnapshot = Field(alias="aep.subagent.usage")


class SubagentFailedData(_SpanData):
    """Subagent invocation errored. The parent treats the error as a
    tool-call failure: the model receives an `Error: ...` string in place
    of the result and may retry or proceed."""

    step: int = Field(ge=0)
    gen_ai_agent_name: str = Field(alias="gen_ai.agent.name")
    aep_subagent_invocation_id: str = Field(min_length=1, alias="aep.subagent.invocation_id")
    duration_ms: int = Field(ge=0)
    aep_subagent_error: str = Field(alias="aep.subagent.error")
    aep_subagent_error_code: str | None = Field(default=None, alias="aep.subagent.error.code")


class TextEmittedData(_SpanData):
    step: int = Field(ge=0)
    aep_text: str = Field(alias="aep.text")


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

    AEP normalizes to a provider-agnostic shape: `reason` is the
    provider's raw code (verbatim, so audit pipelines can match exact
    upstream strings), `message` is the model's refusal text when given,
    `category` is the provider's safety category (free-form because
    every provider names them differently), `provider` lets downstream
    consumers normalize the reason code without context-guessing.

    A refusal terminates the turn — the model produced no useful text or
    tool call. Whether the *run* terminates is a runner decision (the
    reference runner stops with `StopReason.refused`); a higher-level
    supervisor may choose to reset history and retry.
    """

    step: int = Field(ge=0)
    aep_refusal_reason: str = Field(min_length=1, alias="aep.refusal.reason")
    aep_refusal_message: str | None = Field(default=None, alias="aep.refusal.message")
    aep_refusal_category: str | None = Field(default=None, alias="aep.refusal.category")
    aep_refusal_provider: str | None = Field(default=None, alias="aep.refusal.provider")


class ReasoningEmittedData(_SpanData):
    """The model produced a reasoning / thinking block during this turn.

    Distinct from `text_emitted` — reasoning is not user-facing output;
    it's the model's internal chain-of-thought that some providers
    expose (Anthropic extended thinking, OpenAI o1/o3 reasoning summaries,
    etc.). Consumers can filter on this event type to redact / collapse
    chain-of-thought from displays without losing it from the audit log.

    `aep.reasoning.signature` rides along when the provider returns a
    cryptographic signature on the thinking block (Anthropic does this
    for redacted_thinking blocks); empty when the provider doesn't.
    `aep.reasoning.redacted` flags blocks the provider has returned in
    encrypted-only form (no plaintext) — the wire still records the
    occurrence so audit consumers can count thinking turns.
    """

    step: int = Field(ge=0)
    aep_reasoning_text: str = Field(alias="aep.reasoning.text")
    aep_reasoning_signature: str | None = Field(default=None, alias="aep.reasoning.signature")
    aep_reasoning_redacted: bool | None = Field(default=None, alias="aep.reasoning.redacted")


class CostRecordedData(_SpanData):
    aep_state: RunStateSnapshot = Field(alias="aep.state")
    # Provenance of the snapshot's running cost total. Set to `reported`
    # on the reconciliation event a runner emits after the API/SDK hands
    # back an authoritative total (Claude Agent SDK's
    # ResultMessage.total_cost_usd, etc.). Per-turn cost_recorded events
    # leave it unset because the running total is a mix of per-turn
    # numbers — `aep.cost.source` on each `model_turn_ended` event is
    # the authoritative tag for individual turn costs.
    aep_cost_source: Literal["computed", "reported", "unknown"] | None = Field(
        default=None, alias="aep.cost.source"
    )


class SkillLoadedData(_SpanData):
    step: int = Field(ge=0)
    aep_skill_name: str = Field(alias="aep.skill.name")
    aep_skill_source: str | None = Field(default=None, alias="aep.skill.source")


class SkillExecutedData(_SpanData):
    step: int = Field(ge=0)
    aep_skill_name: str = Field(alias="aep.skill.name")


class ErrorOccurredData(_SpanData):
    aep_error_code: ErrorCode = Field(alias="aep.error.code")
    aep_error_message: str = Field(alias="aep.error.message")


class JsonRpcRequestPayload(BaseModel):
    """JSON-RPC 2.0 request payload — what tool_exec_request.data carries.

    Per MCP convention, `method` is `"tools/call"` and `params` is
    `{name, arguments}`.
    """

    model_config = _OPEN
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int = Field(union_mode="left_to_right")
    method: str
    params: dict[str, Any]


class JsonRpcError(BaseModel):
    model_config = _OPEN
    code: int
    message: str
    data: Any | None = None


class JsonRpcResponsePayload(BaseModel):
    """JSON-RPC 2.0 response payload — what tool_exec_resolved.data carries.

    Exactly one of `result` or `error` MUST be present per the JSON-RPC spec.
    """

    model_config = _OPEN
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: JsonRpcError | None = None

    @model_validator(mode="after")
    def _exactly_one_of_result_error(self) -> JsonRpcResponsePayload:
        has_result = self.result is not None
        has_error = self.error is not None
        if has_result == has_error:
            raise ValueError("JSON-RPC response MUST have exactly one of `result` or `error`")
        return self


class ToolExecRequestData(_SpanData):
    """Wraps the JSON-RPC request alongside AEP-side bookkeeping.

    `gen_ai.tool.name` is duplicated at the top of `data` (OTel convention)
    even though it's also inside `rpc.params.name` per MCP — this keeps tool
    filtering on the trajectory uniform across `tool_invoked` /
    `tool_exec_request` / `tool_returned`.
    """

    step: int = Field(ge=0)
    aep_request_id: str = Field(min_length=1, alias="aep.request_id")
    gen_ai_tool_call_id: str = Field(min_length=1, alias="gen_ai.tool.call.id")
    aep_timeout_ms: int = Field(gt=0, alias="aep.timeout_ms")
    aep_tool_dispatch_target: Literal["supervisor_rpc", "mcp_server"] = Field(
        alias="aep.tool.dispatch_target"
    )
    aep_mcp_server_id: str | None = Field(default=None, alias="aep.mcp_server_id")
    gen_ai_tool_name: str = Field(alias="gen_ai.tool.name")
    rpc: JsonRpcRequestPayload


class ToolExecResolvedData(_SpanData):
    """Wraps the JSON-RPC response. `source` URI on the envelope identifies
    who answered (supervisor or mcp/<server_id>).

    `gen_ai.tool.name` echoes the request's tool name for observability —
    consumers shouldn't need to cross-reference the request to filter replies.
    """

    aep_request_id: str = Field(min_length=1, alias="aep.request_id")
    gen_ai_tool_name: str | None = Field(default=None, alias="gen_ai.tool.name")
    rpc: JsonRpcResponsePayload


class ToolExecTimedOutData(_SpanData):
    step: int = Field(ge=0)
    aep_request_id: str = Field(min_length=1, alias="aep.request_id")
    gen_ai_tool_call_id: str = Field(min_length=1, alias="gen_ai.tool.call.id")
    gen_ai_tool_name: str = Field(alias="gen_ai.tool.name")
    aep_timeout_ms: int = Field(gt=0, alias="aep.timeout_ms")


# ── Approval RPC (used by approval-source verifiers; see Verifier) ───────────


class ApprovalRequestedData(_SpanData):
    """Runner emits this when an approval-source verifier fires.

    Carries the context the supervisor needs to decide: which verifier
    requested it, the optional prompt, and (for `pre_tool:<name>`
    gates) the tool call this approval covers. The supervisor MUST
    reply with an `approval_resolved` referencing the same
    `aep.approval.id` within `aep.timeout_ms`; missing replies are
    treated as denials.
    """

    step: int = Field(ge=0)
    aep_approval_id: str = Field(min_length=1, alias="aep.approval.id")
    aep_timeout_ms: int = Field(gt=0, alias="aep.timeout_ms")
    aep_verifier_name: str = Field(min_length=1, alias="aep.verifier.name")
    aep_approval_prompt: str | None = Field(default=None, alias="aep.approval.prompt")
    # Tool context — populated when the verifier's trigger is `pre_tool:<name>`.
    gen_ai_tool_name: str | None = Field(default=None, alias="gen_ai.tool.name")
    gen_ai_tool_call_id: str | None = Field(default=None, alias="gen_ai.tool.call.id")
    gen_ai_tool_call_arguments: dict[str, Any] | None = Field(
        default=None, alias="gen_ai.tool.call.arguments"
    )


class ApprovalResolvedData(_SpanData):
    """Supervisor's decision for a pending `approval_requested`.

    `approved` is the load-bearing field. `reason` is free-text
    intended for the trajectory consumer (and for surfacing to the
    model on `pre_tool:` denials via the resulting `tool_failed.error`).
    """

    aep_approval_id: str = Field(min_length=1, alias="aep.approval.id")
    aep_approval_approved: bool = Field(alias="aep.approval.approved")
    aep_approval_reason: str | None = Field(default=None, alias="aep.approval.reason")


class VerifierEvaluatedData(_SpanData):
    """The result of a deterministic Boolean check."""

    aep_verifier_name: str = Field(min_length=1, alias="aep.verifier.name")
    aep_verifier_passed: bool = Field(alias="aep.verifier.passed")
    aep_verifier_duration_ms: int = Field(ge=0, alias="aep.verifier.duration_ms")
    step: int | None = Field(default=None, ge=0)
    aep_verifier_error: VerifierError | None = Field(default=None, alias="aep.verifier.error")
    aep_verifier_subject_call_ids: list[str] | None = Field(
        default=None, alias="aep.verifier.subject_call_ids"
    )
    aep_verifier_subject_request_ids: list[str] | None = Field(
        default=None, alias="aep.verifier.subject_request_ids"
    )
    aep_verifier_data: dict[str, Any] | None = Field(default=None, alias="aep.verifier.data")

    @model_validator(mode="after")
    def _error_implies_failed(self) -> VerifierEvaluatedData:
        if self.aep_verifier_error is not None and self.aep_verifier_passed:
            raise ValueError(
                "verifier_evaluated.data: aep.verifier.error set but aep.verifier.passed=true; "
                "mutually exclusive"
            )
        return self


class McpServerConnectedData(_SpanData):
    aep_mcp_server_id: str = Field(min_length=1, alias="aep.mcp.server_id")
    aep_mcp_protocol_version: str = Field(alias="aep.mcp.protocol_version")
    aep_mcp_tool_count: int = Field(ge=0, alias="aep.mcp.tool_count")
    aep_mcp_server_name: str | None = Field(default=None, alias="aep.mcp.server_name")
    aep_mcp_server_version: str | None = Field(default=None, alias="aep.mcp.server_version")
    # Per-server tool list, populated by runners that actually drive the
    # MCP handshake (e.g. aep-claude-agent calling
    # `ClaudeSDKClient.get_mcp_status()` after connect). Null when the
    # runner emits a stub event (e.g. the reference runner — its
    # mcp_server_connected events are placeholders without live transport).
    # Each entry is the same `_ToolDecl` shape used on
    # `agent_started.data.tools`, with `aep.dispatch_target=mcp_server`
    # and `aep.mcp_server_id` matching this event's server id.
    aep_mcp_tools: list[_ToolDecl] | None = Field(default=None, alias="aep.mcp.tools")
    # SDK-reported connection status, mirroring the Claude Agent SDK's
    # McpServerStatus.status enum. Default null because pre-live-transport
    # stub emitters didn't have this signal.
    aep_mcp_status: Literal["connected", "failed", "needs-auth", "pending", "disabled"] | None = (
        Field(default=None, alias="aep.mcp.status")
    )
    # Error message when status indicates failure (failed / needs-auth).
    # Surfaces the SDK's `error` field verbatim. Null on healthy connects.
    aep_mcp_error: str | None = Field(default=None, alias="aep.mcp.error")


class McpServerDisconnectedData(_SpanData):
    aep_mcp_server_id: str = Field(min_length=1, alias="aep.mcp.server_id")
    aep_mcp_disconnect_reason: Literal["clean", "error"] = Field(alias="aep.mcp.disconnect_reason")
    aep_mcp_disconnect_message: str | None = Field(default=None, alias="aep.mcp.disconnect_message")


# ── CloudEvents 1.0 envelope (event types) ────────────────────────────────────
#
# Each event is a CloudEvent. `type` discriminates the union. `source` is the
# producer URI. `subject` carries the run_id. `data` carries the typed payload.


class _CloudEventBase(BaseModel):
    """Shared CloudEvents 1.0 envelope fields. Specific events override
    `type` and `source` with Literal constants and define `data: <Type>Data`.

    Per CloudEvents §1: required `specversion`, `id`, `source`, `type`.
    Optional: `subject`, `time`, `datacontenttype`, `dataschema`. AEP uses
    `subject` to carry run_id.
    """

    model_config = _STRICT
    specversion: Literal["1.0"] = "1.0"
    id: str = Field(min_length=1, default_factory=new_event_id)
    time: Iso8601 = Field(default_factory=now_iso)
    subject: str | None = Field(default=None, min_length=1)  # run_id
    datacontenttype: str | None = "application/json"
    dataschema: str | None = None
    aep_correlation_id: str | None = Field(default=None, min_length=1, alias="aep.correlation_id")


class AgentStartedEvent(_CloudEventBase):
    type: Literal["aep.agent_started"] = T_AGENT_STARTED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: AgentStartedData


class AgentStoppedEvent(_CloudEventBase):
    type: Literal["aep.agent_stopped"] = T_AGENT_STOPPED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: AgentStoppedData


class ModelTurnStartedEvent(_CloudEventBase):
    type: Literal["aep.model_turn_started"] = T_MODEL_TURN_STARTED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ModelTurnStartedData


class ModelTurnEndedEvent(_CloudEventBase):
    type: Literal["aep.model_turn_ended"] = T_MODEL_TURN_ENDED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ModelTurnEndedData


class ToolInvokedEvent(_CloudEventBase):
    type: Literal["aep.tool_invoked"] = T_TOOL_INVOKED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ToolInvokedData


class ToolReturnedEvent(_CloudEventBase):
    type: Literal["aep.tool_returned"] = T_TOOL_RETURNED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ToolReturnedData


class ToolFailedEvent(_CloudEventBase):
    type: Literal["aep.tool_failed"] = T_TOOL_FAILED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ToolFailedData


class SubagentInvokedEvent(_CloudEventBase):
    type: Literal["aep.subagent_invoked"] = T_SUBAGENT_INVOKED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: SubagentInvokedData


class SubagentReturnedEvent(_CloudEventBase):
    type: Literal["aep.subagent_returned"] = T_SUBAGENT_RETURNED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: SubagentReturnedData


class SubagentFailedEvent(_CloudEventBase):
    type: Literal["aep.subagent_failed"] = T_SUBAGENT_FAILED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: SubagentFailedData


class TextEmittedEvent(_CloudEventBase):
    type: Literal["aep.text_emitted"] = T_TEXT_EMITTED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: TextEmittedData


class ReasoningEmittedEvent(_CloudEventBase):
    type: Literal["aep.reasoning_emitted"] = T_REASONING_EMITTED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ReasoningEmittedData


class RefusalRecordedEvent(_CloudEventBase):
    type: Literal["aep.refusal_recorded"] = T_REFUSAL_RECORDED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: RefusalRecordedData


class CostRecordedEvent(_CloudEventBase):
    type: Literal["aep.cost_recorded"] = T_COST_RECORDED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: CostRecordedData


class SkillLoadedEvent(_CloudEventBase):
    type: Literal["aep.skill_loaded"] = T_SKILL_LOADED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: SkillLoadedData


class SkillExecutedEvent(_CloudEventBase):
    type: Literal["aep.skill_executed"] = T_SKILL_EXECUTED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: SkillExecutedData


class ErrorOccurredEvent(_CloudEventBase):
    type: Literal["aep.error_occurred"] = T_ERROR_OCCURRED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ErrorOccurredData


class ToolExecRequestEvent(_CloudEventBase):
    """Agent calls into an external service (supervisor RPC or MCP server).

    `source` is `aep://runner` because the runner emits this event when the
    agent decides to call a tool whose implementation is external.
    """

    type: Literal["aep.tool_exec_request"] = T_TOOL_EXEC_REQUEST
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ToolExecRequestData


class ToolExecResolvedEvent(_CloudEventBase):
    """RPC reply recorded into the trajectory verbatim. `source` is the URI
    of the responding service: `aep://supervisor` or `aep://mcp/<server_id>`."""

    type: Literal["aep.tool_exec_resolved"] = T_TOOL_EXEC_RESOLVED
    source: str = Field(min_length=1)  # constrained at validation time
    data: ToolExecResolvedData

    @field_validator("source")
    @classmethod
    def _source_must_be_supervisor_or_mcp(cls, v: str) -> str:
        if v != SOURCE_SUPERVISOR and not v.startswith("aep://mcp/"):
            raise ValueError(
                f"tool_exec_resolved.source must be {SOURCE_SUPERVISOR!r} or "
                f"'aep://mcp/<server_id>'; got {v!r}"
            )
        return v


class ToolExecTimedOutEvent(_CloudEventBase):
    type: Literal["aep.tool_exec_timed_out"] = T_TOOL_EXEC_TIMED_OUT
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ToolExecTimedOutData


class ApprovalRequestedEvent(_CloudEventBase):
    """Runner asks the supervisor to approve (or deny) something —
    typically a tool dispatch gated by a pre_tool: + approval-source
    verifier. The supervisor MUST reply with `approval_resolved`."""

    type: Literal["aep.approval_requested"] = T_APPROVAL_REQUESTED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: ApprovalRequestedData


class ApprovalResolvedEvent(_CloudEventBase):
    """Supervisor's decision recorded into the trajectory verbatim.
    `source` is `aep://supervisor`."""

    type: Literal["aep.approval_resolved"] = T_APPROVAL_RESOLVED
    source: str = Field(min_length=1)
    data: ApprovalResolvedData

    @field_validator("source")
    @classmethod
    def _source_must_be_supervisor(cls, v: str) -> str:
        if v != SOURCE_SUPERVISOR:
            raise ValueError(f"approval_resolved.source must be {SOURCE_SUPERVISOR!r}; got {v!r}")
        return v


class VerifierEvaluatedEvent(_CloudEventBase):
    type: Literal["aep.verifier_evaluated"] = T_VERIFIER_EVALUATED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: VerifierEvaluatedData


class McpServerConnectedEvent(_CloudEventBase):
    type: Literal["aep.mcp_server_connected"] = T_MCP_SERVER_CONNECTED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: McpServerConnectedData


class McpServerDisconnectedEvent(_CloudEventBase):
    type: Literal["aep.mcp_server_disconnected"] = T_MCP_SERVER_DISCONNECTED
    source: Literal["aep://runner"] = SOURCE_RUNNER
    data: McpServerDisconnectedData


# ── Discriminated unions ──────────────────────────────────────────────────────


_RUNNER_EVENT_TYPES = (
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
    SkillExecutedEvent,
    ErrorOccurredEvent,
    ToolExecRequestEvent,
    ToolExecTimedOutEvent,
    ApprovalRequestedEvent,
    VerifierEvaluatedEvent,
    McpServerConnectedEvent,
    McpServerDisconnectedEvent,
)

# v0.1: the supervisor channel carries RPC replies for two protocols —
# tool_exec and approval. Both are agent-initiated; the supervisor only
# speaks in response.
_SUPERVISOR_EVENT_TYPES = (ToolExecResolvedEvent, ApprovalResolvedEvent)

Event = Annotated[
    AgentStartedEvent
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
    | SkillExecutedEvent
    | ErrorOccurredEvent
    | ToolExecRequestEvent
    | ToolExecResolvedEvent
    | ToolExecTimedOutEvent
    | ApprovalRequestedEvent
    | ApprovalResolvedEvent
    | VerifierEvaluatedEvent
    | McpServerConnectedEvent
    | McpServerDisconnectedEvent,
    Field(discriminator="type"),
]

SupervisorMessage = ToolExecResolvedEvent | ApprovalResolvedEvent

_TYPE_TO_MODEL: dict[str, type[BaseModel]] = {}
for _cls in _RUNNER_EVENT_TYPES + _SUPERVISOR_EVENT_TYPES:
    _TYPE_TO_MODEL[_cls.model_fields["type"].default] = _cls


# Required CloudEvents-envelope fields every parsed event MUST carry, even
# unknown (custom) event types. Per CloudEvents §1.
_REQUIRED_ENVELOPE_FIELDS = ("specversion", "id", "source", "type", "time", "data")


def parse_event(payload: dict[str, Any]) -> BaseModel | dict[str, Any]:
    """Parse a runner-emitted event payload.

    Known types validate against their Pydantic model. Unknown types pass
    through as a dict (per SPEC §12: consumers MUST pass through unknown
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


def parse_supervisor_message(payload: dict[str, Any]) -> BaseModel:
    """Parse a supervisor- or MCP-server-emitted message. Only RPC replies are valid in v0.1."""
    t = payload.get("type")
    cls = _TYPE_TO_MODEL.get(t) if isinstance(t, str) else None
    if cls is None or cls not in _SUPERVISOR_EVENT_TYPES:
        valid = sorted(c.model_fields["type"].default for c in _SUPERVISOR_EVENT_TYPES)
        raise ValueError(
            f"unknown or unsupported supervisor message type {t!r}; expected one of {valid}"
        )
    return cls.model_validate(payload)


def event_to_wire(event: BaseModel) -> dict[str, Any]:
    """Serialize an event Pydantic model to the wire-form dict.

    Always uses aliases (the dotted forms like `gen_ai.usage.input_tokens`)
    so the output is what consumers see on the wire.
    """
    return event.model_dump(by_alias=True, exclude_none=True, mode="json")
