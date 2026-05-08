"""Pluggable driver protocols for the reference AVP agent (v0.1).

Four drivers:

- ModelDriver       — produces the next ModelResponse given conversation history.
- ToolDriver        — executes locally-handled (non-RPC) tools.
- SupervisorDriver  — handles tool_exec RPC interactions.
- SubagentDriver    — executes declared subagent invocations (sub-loop).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    from avp.enums import StopReason
    from avp.types import RunStateSnapshot, Subagent

# ── Model driver ──────────────────────────────────────────────────────────────


@dataclass
class ScriptedToolCall:
    call_id: str
    tool: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class Refusal:
    """The model declined this turn — either via a provider-specific
    stop reason (Anthropic `refusal`/`sensitive`, Gemini `SAFETY`, …) or
    a dedicated refusal field (OpenAI's `refusal` on the assistant
    message).

    Drivers populate this when they detect a refusal-flavored signal in
    the response. `reason` carries the provider's verbatim code (so
    audit pipelines can match exact upstream strings); `message` is the
    refusal text the model produced when given; `category` is the
    provider's safety classification when given (Gemini's harm
    categories, OpenAI's filter classification, etc.); `provider` lets
    downstreams normalize across providers.

    A refusal terminates the turn — the agent emits
    `avp.refusal_recorded`, then stops with `StopReason.refused` (a
    higher-level supervisor can choose to reset history and retry).
    """

    reason: str
    message: str | None = None
    category: str | None = None
    provider: str | None = None


@dataclass
class ReasoningBlock:
    """A reasoning / thinking block the model produced this turn.

    Maps to the `reasoning_emitted` event. Drivers populate this from
    provider-specific shapes (Anthropic's `thinking` content blocks,
    `redacted_thinking` blocks, OpenAI o1/o3 reasoning summaries) so the
    agent doesn't need provider-specific parsing.

    `text` is the visible chain-of-thought (empty when redacted).
    `signature` carries the cryptographic signature when the provider
    returns one (Anthropic does for redacted_thinking); empty otherwise.
    `redacted` is True when the provider returned the block in
    encrypted-only form — the wire still records the occurrence so audit
    consumers can count thinking turns.
    """

    text: str = ""
    signature: str | None = None
    redacted: bool = False


@dataclass
class ServerToolCall:
    """A tool call the API/SDK ran server-side during this turn.

    Distinct from `ScriptedToolCall`: those are tool USES the model
    requested and the agent dispatches. A `ServerToolCall` already
    happened — the API ran the tool inline and returned the result in
    the same response (Anthropic's `mcp_tool_use` / `mcp_tool_result`
    blocks, server-side `web_search_tool_use`, etc.). Drivers populate
    this list so the agent can emit synthetic tool_invoked /
    tool_returned events for per-call wire fidelity, parented to the
    turn span. No agent dispatch happens — these events are
    informational only.
    """

    call_id: str
    tool: str
    input: dict[str, Any]
    output_text: str = ""
    output_structured: Any | None = None
    is_error: bool = False
    duration_ms: int = 0
    dispatch_target: Literal["mcp_server", "local"] = "mcp_server"
    server_id: str | None = None
    # `avp.tool.subtype` discriminator on the wire — `web_search`,
    # `code_execution`, etc. for provider-hosted tools that aren't MCP.
    # Lets consumers filter / count by hosted-tool kind without
    # parsing the tool name.
    subtype: str | None = None


@dataclass
class ModelResponse:
    tokens_input: int
    tokens_output: int
    cost_usd: float
    duration_ms: int
    text: str | None = None
    tool_calls: list[ScriptedToolCall] = field(default_factory=list)
    server_tool_calls: list[ServerToolCall] = field(default_factory=list)
    reasoning_blocks: list[ReasoningBlock] = field(default_factory=list)
    refusal: Refusal | None = None
    tokens_cache_read: int | None = None
    tokens_cache_write: int | None = None
    tokens_reasoning_output: int | None = None
    converged: bool = False
    # Provenance for the cost number — `computed` (we did the math locally),
    # `reported` (the API/SDK gave us the number), or `unknown` (no price
    # found, no provider report). Tagged on `model_turn_ended` and
    # `cost_recorded` events as `avp.cost.source` so audit consumers can
    # filter by trust.
    cost_source: str = "computed"
    # Streaming observability (OpenTelemetry GenAI conventions). Drivers SHOULD
    # populate these when the underlying API call streamed tokens; non-streaming
    # drivers leave them at None.
    streamed: bool | None = None
    time_to_first_chunk_s: float | None = None
    response_model: str | None = None
    finish_reasons: list[str] | None = None


class ModelDriver(Protocol):
    def step(self, history: list[dict[str, Any]]) -> ModelResponse: ...


# ── Tool driver ───────────────────────────────────────────────────────────────


@dataclass
class ToolOutcome:
    output: str | None = None
    output_json: Any | None = None
    error: str | None = None
    duration_ms: int = 1
    rejected: bool = False
    rejection_reason: str | None = None


class ToolDriver(Protocol):
    def is_local(self, tool: str) -> bool: ...
    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome: ...


# ── Supervisor driver (event sink) ──────────────────────────────────────────


class SupervisorDriver(Protocol):
    """Sink for agent-emitted events.

    v0.1 has no agent→supervisor RPC channel. Supervisor-side tool dispatch
    happens through MCP (Commission.mcp_servers); the agent doesn't talk to the
    supervisor mid-run. The driver's only job is `observe()` — in production
    that writes events to stdout (NDJSON); in tests it captures into a list.
    """

    def observe(self, event: BaseModel) -> None:
        """Called for every agent-emitted event."""
        ...


# ── Subagent driver ──────────────────────────────────────────────────────────


@dataclass
class SubagentOutcome:
    """Result of running one subagent invocation.

    `text` is the model-visible result returned to the parent (always set —
    becomes the parent's `tool_result`-equivalent). `structured` is optional;
    populated if the subagent's `output_schema` validates a structured result.
    `usage` is the subagent's own consumption rollup; the agent reflects it
    in the parent's cumulative state on `subagent_returned.data.avp.subagent.usage`.

    `error` and `error_code`, when set, mean the subagent failed and the
    agent SHOULD emit `subagent_failed` instead of `subagent_returned`.
    """

    text: str
    reason: StopReason
    duration_ms: int
    usage: RunStateSnapshot
    structured: Any | None = None
    error: str | None = None
    error_code: str | None = None


class SubagentDriver(Protocol):
    """Provider-specific subagent execution.

    The agent calls `invoke()` when the parent agent invokes a tool whose
    name matches a declared `Commission.subagents[*].name`. Implementations run
    the subagent's sub-loop (model + tools as declared on the Subagent
    object) and return the result + a usage rollup.

    Implementations MAY emit nested events via `parent_observer` so the
    subagent's internal turns observe as a span tree. Each emitted event's
    `data.parent_span_id` MUST be `parent_frame_span_id` (or descend from
    it) and `data.trace_id` MUST equal `parent_trace_id`. Implementations
    MAY skip nested observability — the parent will still emit
    `subagent_invoked` and `subagent_returned` regardless, so the lifecycle
    is on the wire even when the subagent is opaque to the agent (e.g.,
    when delegating into an external SDK that doesn't surface internals).
    """

    def invoke(
        self,
        subagent: Subagent,
        invocation_input: dict[str, Any],
        *,
        parent_trace_id: str,
        parent_frame_span_id: str,
        parent_observer: Callable[[BaseModel], None],
    ) -> SubagentOutcome: ...
