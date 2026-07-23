"""avp.trajectory — Pydantic types for the AVP Trajectory Spec.

Defines the agent-emitted event stream: CloudEvents envelopes, typed
`data` payloads (one per event type), the `Event` discriminated union,
and the `parse_event` / `event_to_wire` helpers. This module mirrors
the [Trajectory spec](../../../../spec/v0.1/trajectory.md).

Consumers wanting only the event stream can:

    from avp.trajectory import (
        AgentStartedEvent,
        AssistantMessageEvent,
        parse_event,
    )

…without dragging in Commission / Descriptor types they don't use.

The wire format is built on:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`,
  `source`, `type`, `subject`, `time`, `datacontenttype`, `data`).
- **OpenTelemetry span identification** (`trace_id`, `span_id`,
  `parent_span_id`) so downstream consumers reconstruct the run's span
  tree.

All AVP-defined `data` attributes (token / cost / model / tool /
subagent / refusal / step / content) live under the single `avp.*` namespace.
See `spec/v0.1/trajectory.md` for the normative attribute reference.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from avp.commission import Commission
from avp.content import AVPContentBlock, ToolResultBlock
from avp.descriptor import (
    AgentDescriptor,
    McpServerDecl,
    SkillDecl,
    SubagentDecl,
    ToolDecl,
)
from avp.envelope import (
    _OPEN,
    SOURCE_AGENT,
    ZERO_SPAN_ID,
    _CloudEventBase,
    _SpanData,
    new_event_id,
    new_span_id,
    new_trace_id,
    now_iso,
)

# Reverse-DNS event types per CloudEvents convention. All AVP-defined types
# live under the `avp.` namespace.
T_RUN_REQUESTED = "avp.run_requested"
T_AGENT_DESCRIBED = "avp.agent_described"
T_AGENT_STARTED = "avp.agent_started"
T_AGENT_STOPPED = "avp.agent_stopped"
T_ASSISTANT_MESSAGE = "avp.assistant_message"
T_TOOL_INVOKED = "avp.tool_invoked"
T_TOOL_RETURNED = "avp.tool_returned"
T_ERROR_OCCURRED = "avp.error_occurred"
T_SUBAGENT_INVOKED = "avp.subagent_invoked"
T_SUBAGENT_RETURNED = "avp.subagent_returned"


class StopReason(StrEnum):
    """Why a run terminated. v0.1 keeps the enum tight: model said done,
    model declined, agent crashed, operator interrupted, or delegated work
    was left in flight. Cap-driven stop reasons (turn / token / cost /
    duration limits) are not part of v0.1; agents that need bounded
    execution wire it externally (subprocess timeouts, supervisor SIGKILL).

    `abandoned` is distinct from `converged` on purpose. A parent that
    dispatches a background subagent and stops before the child reports
    has produced no answer, however confident its final text sounds
    ("I'll wait for the agent to complete"). Scoring that as `converged`
    silently counts an unfinished run as a success, so it gets its own
    value rather than being folded into `converged` or `interrupted`
    (which means an operator or supervisor cut the run short).
    """

    converged = "converged"
    error = "error"
    interrupted = "interrupted"
    refused = "refused"
    abandoned = "abandoned"


class ErrorCode(StrEnum):
    rate_limit = "rate_limit"
    context_limit = "context_limit"
    auth_error = "auth_error"
    agent_crash = "agent_crash"
    unsupported_model = "unsupported_model"
    unsupported_provider = "unsupported_provider"
    unsupported_agent_version = "unsupported_agent_version"
    commission_collision = "commission_collision"
    mcp_connect_failed = "mcp_connect_failed"
    unknown = "unknown"


class Usage(BaseModel):
    """Per-turn token accounting carried on `assistant_message.avp.usage`.

    `input_tokens` is the total input tokens for the turn, INCLUDING
    cache-read tokens. `cache_read_input_tokens` and
    `cache_creation_input_tokens` are informational breakdowns already
    accounted for inside `input_tokens`; consumers MUST NOT double-count
    them when summing. `reasoning_output_tokens` is the subset of
    `output_tokens` the provider attributes to internal reasoning (o-series
    reasoning tokens, Anthropic extended-thinking output).

    `extra="allow"` so provider-specific token categories the spec
    doesn't enumerate (vision tokens, audio output tokens, ...) round-trip
    through `avp.usage` verbatim without requiring spec churn.
    """

    model_config = _OPEN
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_input_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_output_tokens: int | None = Field(default=None, ge=0)


class SubagentUsage(BaseModel):
    """Narrow totals carrier for the in-process subagent rollup.

    Used ONLY on `subagent_returned.data["avp.subagent.usage"]` when the
    parent agent's SDK does not expose the child's per-turn events (e.g.
    Claude Agent SDK's Task tool). `extra="allow"` so SDK-specific fields
    (total_tokens, tool_uses, duration_ms) round-trip verbatim.

    Every field is optional because SDKs report different subsets: Claude
    Agent SDK's `TaskUsage` carries a token total with no input/output split
    and no cost. Per spec §2.1, absence (not a 0 sentinel) is the signal
    that the parent could not measure a field, so a consumer summing
    `cost_usd` across a run can tell "the child spent nothing" from "nobody
    told us." Emitters MUST omit what they cannot measure rather than
    zero-filling it.
    """

    model_config = _OPEN
    cost_usd: float | None = Field(default=None, ge=0)
    tokens_input: int | None = Field(default=None, ge=0)
    tokens_output: int | None = Field(default=None, ge=0)
    turns: int | None = Field(default=None, ge=0)


# ── Data payloads (per-event-type) ────────────────────────────────────────────
#
# Every AVP event's `data` field carries an OTel span triple plus the
# event-type-specific attributes. Field names with dots (the OTel/MCP/JSON-RPC
# wire form) are declared via Pydantic aliases; Python attribute names use
# underscores. `model_dump(by_alias=True)` produces the wire form on emit.


class RunRequestedData(_SpanData):
    """Payload of avp.run_requested events.

    Anchors the trajectory. When relaying a Commission, carries the full
    snapshot under `avp.commission` plus `avp.supervisor.*` for attribution,
    making the trajectory self-contained for audit. Without a Commission
    (library-invocation path), those fields are absent — per spec §2.1,
    absence (not `"unknown"`) is the canonical signal.
    """

    supervisor_name: str | None = Field(default=None, min_length=1, alias="avp.supervisor.name")
    supervisor_version: str | None = Field(default=None, alias="avp.supervisor.version")
    commission: Commission | None = Field(default=None, alias="avp.commission")


class AgentDescribedData(_SpanData):
    """Payload of avp.agent_described events.

    The agent's published Descriptor, emitted between `run_requested`
    and `agent_started`. `avp.descriptor` SHOULD be consistent with what
    `<agent> describe` prints to stdout for the same agent build;
    pre-flight describe MAY omit MCP-surfaced tool entries (those whose
    `avp.mcp_server_id` is set) and per-server `mcp_servers[].status`,
    both of which require a startup dial.
    """

    descriptor: AgentDescriptor = Field(alias="avp.descriptor")


class AgentStartedData(_SpanData):
    """Payload of avp.agent_started events."""

    provider_name: str | None = Field(default=None, alias="avp.provider.name")
    operation_name: Literal["invoke_agent", "chat"] | None = Field(
        default=None, alias="avp.operation.name"
    )
    request_model: str | None = Field(default=None, alias="avp.request.model")
    prompt: str | None = Field(default=None, alias="avp.prompt")
    system_prompt: str | None = Field(default=None, alias="avp.system_prompt")
    tools: list[ToolDecl] | None = Field(default=None, alias="avp.tools")
    mcp_servers: list[McpServerDecl] | None = Field(default=None, alias="avp.mcp_servers")
    skills: list[SkillDecl] | None = Field(default=None, alias="avp.skills")
    subagents: list[SubagentDecl] | None = Field(default=None, alias="avp.subagents")
    thread_id: str | None = Field(default=None, alias="avp.thread_id")
    session_id: str | None = Field(default=None, alias="avp.session_id")
    tags: list[str] | None = Field(default=None, alias="avp.tags")


class AgentStoppedData(_SpanData):
    """Payload of avp.agent_stopped events. Terminator of the trajectory.

    Carries `avp.reason` (why the run ended) and an optional `avp.output`
    payload. The agent does NOT publish cumulative totals on this event.
    Per-turn deltas live on each `assistant_message`; consumers reduce
    the stream to compute totals.
    """

    reason: StopReason = Field(alias="avp.reason")
    output: Any | None = Field(default=None, alias="avp.output")


class AssistantMessageData(_SpanData):
    """Payload of avp.assistant_message events.

    Carries the full content the model produced this turn under
    `avp.content` (a `list[AVPContentBlock]`) plus per-turn token / cost
    deltas. Reconstructing a provider message array is a direct read of
    `avp.content` per turn, paired with the `avp.tool_result` blocks from
    intervening `tool_returned` events to form the user-role tool-result
    messages.

    Refusal metadata: when the provider declined the turn, the refusal
    text appears as a `RefusalBlock` (or `TextBlock` for providers that
    don't typify it) inside `avp.content`, the upstream finish-reason
    string surfaces on `avp.response.finish_reasons`, and the
    provider's safety category (when given, free-form because every
    provider names them differently) surfaces on `avp.refusal.category`.
    """

    step: int = Field(ge=0, alias="avp.step")
    duration_ms: int = Field(ge=0, alias="avp.duration_ms")
    content: list[AVPContentBlock] = Field(alias="avp.content")
    provider_name: str | None = Field(default=None, alias="avp.provider.name")
    request_model: str | None = Field(default=None, alias="avp.request.model")
    response_model: str | None = Field(default=None, alias="avp.response.model")
    response_finish_reasons: list[str] | None = Field(
        default=None, alias="avp.response.finish_reasons"
    )
    response_time_to_first_chunk: float | None = Field(
        default=None, ge=0, alias="avp.response.time_to_first_chunk"
    )
    usage: Usage = Field(alias="avp.usage")
    cost_usd: float = Field(ge=0, alias="avp.cost_usd")
    cost_source: Literal["computed", "reported", "unknown"] | None = Field(
        default=None, alias="avp.cost.source"
    )
    refusal_category: str | None = Field(default=None, alias="avp.refusal.category")


class ToolInvokedData(_SpanData):
    step: int = Field(ge=0, alias="avp.step")
    tool_call_id: str = Field(min_length=1, alias="avp.tool.call_id")
    tool_name: str = Field(alias="avp.tool.name")
    tool_input: dict[str, Any] = Field(alias="avp.tool.input")
    tool_dispatch_target: Literal["mcp_server", "local"] | None = Field(
        default=None, alias="avp.tool.dispatch_target"
    )


class ToolReturnedData(_SpanData):
    """Tool result sent back to the model.

    `avp.tool_result` is a `content.ToolResultBlock` carrying
    `tool_use_id`, `content` (string or nested text/image/document
    blocks), and `is_error`. Rejections set `is_error=True` with the
    reason in `content[0].text`. During reconstruction this block
    becomes one entry of the next user-role message's content array.
    """

    step: int = Field(ge=0, alias="avp.step")
    tool_call_id: str = Field(min_length=1, alias="avp.tool.call_id")
    tool_name: str = Field(alias="avp.tool.name")
    duration_ms: int = Field(ge=0, alias="avp.duration_ms")
    tool_result: ToolResultBlock = Field(alias="avp.tool_result")


class SubagentInvokedData(_SpanData):
    """Parent agent delegates to a declared subagent.

    The event's `span_id` IS the subagent's frame span. Events emitted by
    the subagent's sub-loop set `parent_span_id` to this frame (or chain
    through descendants of it), so the trajectory reconstructs as a nested
    tree. The subagent's declared name surfaces on `avp.subagent.name`;
    the event type itself signals an `invoke_agent`-style operation, so no
    separate operation-name field is carried on the wire.

    `avp.subagent.run_id` is reserved for future use when the subagent runs
    as a separate commissioned trajectory. Absent for in-process subagents.
    """

    step: int = Field(ge=0, alias="avp.step")
    subagent_name: str = Field(alias="avp.subagent.name")
    subagent_description: str | None = Field(default=None, alias="avp.subagent.description")
    subagent_invocation_id: str = Field(min_length=1, alias="avp.subagent.invocation_id")
    subagent_input: dict[str, Any] = Field(alias="avp.subagent.input")
    subagent_run_id: str | None = Field(default=None, min_length=1, alias="avp.subagent.run_id")


class SubagentReturnedData(_SpanData):
    """Closes the subagent's frame. `span_id` matches the corresponding
    `subagent_invoked` event so consumers can pair them.

    `avp.subagent.reason` is a `StopReason`; on the error path,
    `reason = error` and `avp.subagent.result.text` carries the error
    string. The paired `tool_returned` mirrors this: `is_error = true`
    when `reason = error`, with the same `Error: ...` content.

    `avp.subagent.usage` is OPTIONAL and intended only for the in-process
    fallback: parent agents whose SDK black-boxes the child loop (no
    per-turn AssistantMessages exposed to the parent) carry the child's
    totals here as the only signal the supervisor receives of the child's
    spend. Agents that emit the child's per-turn events into the parent's
    trajectory with proper span parentage (`parent_span_id` = this event's
    `span_id`) MUST omit this field; the supervisor reconstructs from the
    raw stream. Managed subagents (separate `run_id`, separate trajectory)
    MUST also omit it; the supervisor reads the child's trajectory.
    """

    step: int = Field(ge=0, alias="avp.step")
    subagent_name: str = Field(alias="avp.subagent.name")
    subagent_invocation_id: str = Field(min_length=1, alias="avp.subagent.invocation_id")
    duration_ms: int = Field(ge=0, alias="avp.duration_ms")
    subagent_result_text: str = Field(alias="avp.subagent.result.text")
    subagent_result_structured: Any | None = Field(
        default=None, alias="avp.subagent.result.structured"
    )
    subagent_reason: StopReason = Field(alias="avp.subagent.reason")
    subagent_usage: SubagentUsage | None = Field(default=None, alias="avp.subagent.usage")


class ErrorOccurredData(_SpanData):
    error_code: ErrorCode = Field(alias="avp.error.code")
    error_message: str = Field(alias="avp.error.message")


# ── CloudEvents 1.0 envelope (event types) ────────────────────────────────────
#
# Each event is a CloudEvent. `type` discriminates the union. `source` is the
# producer URI. `subject` carries the run_id. `data` carries the typed payload.


class RunRequestedEvent(_CloudEventBase):
    """First event of the trajectory. The agent is the sole producer on the
    wire (spec §8 conformance #1), so `source` is `avp://agent`. Supervisor
    attribution, when a Commission is in use, lives inside `data` as
    `avp.supervisor.*` plus the full `avp.commission` snapshot — that's what
    makes the trajectory self-contained for audit without resort to the
    envelope's `source` field.
    """

    type: Literal["avp.run_requested"] = T_RUN_REQUESTED
    source: Literal["avp://agent"] = SOURCE_AGENT
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


class AssistantMessageEvent(_CloudEventBase):
    type: Literal["avp.assistant_message"] = T_ASSISTANT_MESSAGE
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: AssistantMessageData


class ToolInvokedEvent(_CloudEventBase):
    type: Literal["avp.tool_invoked"] = T_TOOL_INVOKED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ToolInvokedData


class ToolReturnedEvent(_CloudEventBase):
    type: Literal["avp.tool_returned"] = T_TOOL_RETURNED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ToolReturnedData


class SubagentInvokedEvent(_CloudEventBase):
    type: Literal["avp.subagent_invoked"] = T_SUBAGENT_INVOKED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: SubagentInvokedData


class SubagentReturnedEvent(_CloudEventBase):
    type: Literal["avp.subagent_returned"] = T_SUBAGENT_RETURNED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: SubagentReturnedData


class ErrorOccurredEvent(_CloudEventBase):
    type: Literal["avp.error_occurred"] = T_ERROR_OCCURRED
    source: Literal["avp://agent"] = SOURCE_AGENT
    data: ErrorOccurredData


class UnknownEvent(_CloudEventBase):
    """Catch-all for CloudEvents whose `type` is not in the AVP-defined
    union. Validates the CloudEvents 1.0 envelope plus the AVP span
    triple on `data`; the rest of `data` is free-form. Consumers MUST
    pass through unknown event types without error (spec §4), so any
    well-formed CloudEvent — forward-compat AVP additions, vendor-
    namespaced events under `acme.*`, etc. — round-trips through here.

    `id` and `time` are re-declared without `default_factory` so missing
    envelope fields error rather than silently getting fabricated values.
    """

    id: str = Field(min_length=1)
    time: str = Field(min_length=1)
    source: str = Field(min_length=1)
    type: str = Field(min_length=1)
    data: _SpanData


# ── Discriminated unions ──────────────────────────────────────────────────────


_AGENT_EVENT_TYPES = (
    RunRequestedEvent,
    AgentDescribedEvent,
    AgentStartedEvent,
    AgentStoppedEvent,
    AssistantMessageEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    ErrorOccurredEvent,
)

Event = Annotated[
    RunRequestedEvent
    | AgentDescribedEvent
    | AgentStartedEvent
    | AgentStoppedEvent
    | AssistantMessageEvent
    | ToolInvokedEvent
    | ToolReturnedEvent
    | SubagentInvokedEvent
    | SubagentReturnedEvent
    | ErrorOccurredEvent,
    Field(discriminator="type"),
]


def parse_event(payload: dict[str, Any]) -> Event | UnknownEvent:
    """Parse an agent-emitted event payload.

    Known types validate via the `Event` discriminated-union TypeAdapter.
    Unknown types validate as `UnknownEvent`: envelope + span triple are
    enforced; the rest of `data` is opaque. Per spec/v0.1/README.md §4,
    consumers MUST pass through unknown types without error.
    """
    _adapter = TypeAdapter(Event)
    try:
        return _adapter.validate_python(payload)
    except ValidationError as e:
        if any(err.get("type") == "union_tag_invalid" for err in e.errors()):
            return UnknownEvent.model_validate(payload)
        raise


def event_to_wire(event: BaseModel) -> dict[str, Any]:
    """Serialize an event Pydantic model to the wire-form dict.

    Always uses aliases (the dotted forms like `avp.usage.input_tokens`)
    so the output is what consumers see on the wire.
    """
    return event.model_dump(by_alias=True, exclude_none=True, mode="json")


__all__ = [
    "SOURCE_AGENT",
    "T_AGENT_DESCRIBED",
    "T_AGENT_STARTED",
    "T_AGENT_STOPPED",
    "T_ASSISTANT_MESSAGE",
    "T_ERROR_OCCURRED",
    "T_RUN_REQUESTED",
    "T_SUBAGENT_INVOKED",
    "T_SUBAGENT_RETURNED",
    "T_TOOL_INVOKED",
    "T_TOOL_RETURNED",
    "ZERO_SPAN_ID",
    "AgentDescribedData",
    "AgentDescribedEvent",
    "AgentStartedData",
    "AgentStartedEvent",
    "AgentStoppedData",
    "AgentStoppedEvent",
    "AssistantMessageData",
    "AssistantMessageEvent",
    "ErrorOccurredData",
    "ErrorOccurredEvent",
    "Event",
    "RunRequestedData",
    "RunRequestedEvent",
    "SubagentInvokedData",
    "SubagentInvokedEvent",
    "SubagentReturnedData",
    "SubagentReturnedEvent",
    "SubagentUsage",
    "ToolInvokedData",
    "ToolInvokedEvent",
    "ToolReturnedData",
    "ToolReturnedEvent",
    "UnknownEvent",
    "Usage",
    "event_to_wire",
    "new_event_id",
    "new_span_id",
    "new_trace_id",
    "now_iso",
    "parse_event",
]
