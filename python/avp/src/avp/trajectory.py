"""avp.trajectory — Pydantic types for the AVP Trajectory Spec.

Defines the agent-emitted event stream: CloudEvents envelopes, typed
`data` payloads (one per event type), `RunStateSnapshot`, the
`Event` discriminated union, and the `parse_event` / `event_to_wire`
helpers. This module mirrors the
[Trajectory spec](../../../../spec/v0.1/trajectory.md).

Consumers wanting only the event stream can:

    from avp.trajectory import (
        AgentStartedEvent,
        ModelTurnEndedEvent,
        RunStateSnapshot,
        parse_event,
    )

…without dragging in Commission / Descriptor / Resolver API types they
don't use.

The wire format is built on:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`,
  `source`, `type`, `subject`, `time`, `datacontenttype`, `data`).
- **OpenTelemetry GenAI** semantic conventions for token / cost / model /
  tool attribute names inside `data` (e.g., `gen_ai.usage.input_tokens`).
- **OpenTelemetry span identification** (`trace_id`, `span_id`,
  `parent_span_id`) so downstream consumers reconstruct the run's span
  tree.

AVP-specific concepts (no-mid-run-reach-in, trajectory contract) live
under the `avp.*` attribute namespace. See `FOUNDATIONS.md` and
`spec/v0.1/trajectory.md` for the normative mapping.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from avp._envelope import (
    _OPEN,
    SOURCE_AGENT,
    SOURCE_SUPERVISOR,
    ZERO_SPAN_ID,
    Iso8601,
    _CloudEventBase,
    _SpanData,
    new_event_id,
    new_span_id,
    new_trace_id,
    now_iso,
)
from avp.descriptor import (
    AgentDescriptor,
    _ResourceDecl,
    _SkillDecl,
    _SubagentDecl,
    _ToolDecl,
)
from avp.enums import ErrorCode, StopReason

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


# ── Data payloads (per-event-type) ────────────────────────────────────────────
#
# Every AVP event's `data` field carries an OTel span triple plus the
# event-type-specific attributes. Field names with dots (the OTel/MCP/JSON-RPC
# wire form) are declared via Pydantic aliases; Python attribute names use
# underscores. `model_dump(by_alias=True)` produces the wire form on emit.


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
    # MCP handshake (e.g. avp-claude-agent-sdk calling
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


# ── CloudEvents 1.0 envelope (event types) ────────────────────────────────────
#
# Each event is a CloudEvent. `type` discriminates the union. `source` is the
# producer URI. `subject` carries the run_id. `data` carries the typed payload.


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
    | ManagedRefResolveFailedEvent,
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


__all__ = [
    "SOURCE_AGENT",
    "SOURCE_SUPERVISOR",
    "T_AGENT_DESCRIBED",
    "T_AGENT_STARTED",
    "T_AGENT_STOPPED",
    "T_COST_RECORDED",
    "T_ERROR_OCCURRED",
    "T_MANAGED_REF_RESOLVED",
    "T_MANAGED_REF_RESOLVE_FAILED",
    "T_MCP_SERVER_CONNECTED",
    "T_MCP_SERVER_DISCONNECTED",
    "T_MODEL_TURN_ENDED",
    "T_MODEL_TURN_STARTED",
    "T_REASONING_EMITTED",
    "T_REFUSAL_RECORDED",
    "T_RUN_REQUESTED",
    "T_SKILL_LOADED",
    "T_SUBAGENT_FAILED",
    "T_SUBAGENT_INVOKED",
    "T_SUBAGENT_RETURNED",
    "T_TEXT_EMITTED",
    "T_TOOL_FAILED",
    "T_TOOL_INVOKED",
    "T_TOOL_RETURNED",
    "ZERO_SPAN_ID",
    "AgentDescribedData",
    "AgentDescribedEvent",
    "AgentStartedData",
    "AgentStartedEvent",
    "AgentStoppedData",
    "AgentStoppedEvent",
    "CostRecordedData",
    "CostRecordedEvent",
    "ErrorOccurredData",
    "ErrorOccurredEvent",
    "Event",
    "ManagedKind",
    "ManagedRefResolveFailedData",
    "ManagedRefResolveFailedEvent",
    "ManagedRefResolvedData",
    "ManagedRefResolvedEvent",
    "McpServerConnectedData",
    "McpServerConnectedEvent",
    "McpServerDisconnectedData",
    "McpServerDisconnectedEvent",
    "ModelTurnEndedData",
    "ModelTurnEndedEvent",
    "ModelTurnStartedData",
    "ModelTurnStartedEvent",
    "ReasoningEmittedData",
    "ReasoningEmittedEvent",
    "RefusalRecordedData",
    "RefusalRecordedEvent",
    "RunRequestedData",
    "RunRequestedEvent",
    "RunStateSnapshot",
    "SkillLoadedData",
    "SkillLoadedEvent",
    "SubagentFailedData",
    "SubagentFailedEvent",
    "SubagentInvokedData",
    "SubagentInvokedEvent",
    "SubagentReturnedData",
    "SubagentReturnedEvent",
    "TextEmittedData",
    "TextEmittedEvent",
    "ToolFailedData",
    "ToolFailedEvent",
    "ToolInvokedData",
    "ToolInvokedEvent",
    "ToolReturnedData",
    "ToolReturnedEvent",
    "event_to_wire",
    "new_event_id",
    "new_span_id",
    "new_trace_id",
    "now_iso",
    "parse_event",
]
