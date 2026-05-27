"""Pluggable driver protocols for the reference AVP agent (v0.1).

Three drivers:

- ModelDriver       — produces the next ModelResponse given conversation history.
- ToolDriver        — executes locally-handled (built-in / agent-internal) tools.
- ResolverDriver    — dereferences supervisor-managed Commission refs (mcp_server,
                      skill, subagent) via the AVP resolver protocol; spawns
                      managed subagents on demand.
- SupervisorDriver  — sink for agent-emitted events (NDJSON to stdout in
                      production; capture-into-list in tests). Not an RPC channel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, JsonValue

if TYPE_CHECKING:
    from avp.enums import ErrorCode, StopReason
    from avp.trajectory import ManagedKind, RunStateSnapshot

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


class ModelDriverError(Exception):
    """Raised by ModelDriver.step() when a provider call fails.

    Carries an `ErrorCode` hint so the agent can emit
    `error_occurred(code=...)` with the right wire-level classification
    instead of falling back to `unknown` for everything.

    Drivers wrap provider-specific exceptions:

      - 429 / RateLimitError       → ErrorCode.rate_limit
      - 401 / AuthenticationError  → ErrorCode.auth_error
      - 400 / context-window-msg   → ErrorCode.context_limit
      - everything else            → ErrorCode.unknown

    Untyped exceptions propagating past `step()` are caught by the agent
    and treated as `agent_crash` (an unexpected internal failure).
    """

    def __init__(self, message: str, *, code: ErrorCode) -> None:
        super().__init__(message)
        self.code = code


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

    The supervisor observes the trajectory but does NOT push messages to
    the agent — v0.1 has no supervisor → agent push channel. The driver's
    only job is `observe()`: in production it writes events to stdout
    (NDJSON); in tests it captures into a list.
    """

    def observe(self, event: BaseModel) -> None:
        """Called for every agent-emitted event."""
        ...


# ── Resolver driver (AVP resolver protocol) ─────────────────────────────────


class ResolveError(Exception):
    """Raised by `ResolverDriver.resolve` when the resolver service rejects
    the request, is unreachable, or returns malformed material. Carries
    optional `code` (free-form string from the resolver / transport layer)
    that lands on `avp.managed_ref_resolve_failed.data["avp.resolve.error.code"]`.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class SubagentSpawnOutcome:
    """Result of an `avp.spawn_subagent` call.

    `child_run_id` is the supervisor-assigned `run_id` for the subagent's
    child trajectory; the parent agent stamps it on
    `subagent_invoked.data["avp.subagent.run_id"]` so consumers can join
    parent and child trajectories.

    The remaining fields are the inline summary the parent's loop hands
    back to the model as the tool result. They mirror what was previously
    `SubagentOutcome` so consumers (the model, the trajectory's
    `subagent_returned` event) see the same shape regardless of whether
    the subagent ran in-process or via the resolver.
    """

    child_run_id: str
    text: str
    reason: StopReason
    duration_ms: int
    usage: RunStateSnapshot
    structured: Any | None = None
    error: str | None = None
    error_code: str | None = None


class ResolverDriver(Protocol):
    """Driver that dereferences Commission-declared managed refs against
    the supervisor's resolver service (the AVP resolver protocol).

    Two methods, both agent-initiated, both crossing the only
    supervisor↔agent runtime boundary AVP defines:

    - `resolve(kind, id, ref)` — startup-only. Called once per
      `Commission.{mcp_servers,skills,subagents}[]` entry. Returns the
      connection material / content / metadata the supervisor wants the
      agent to use. The result shape varies by `kind` (see
      `spec/v0.1/resolver.md` §3.2); the agent's runtime layer interprets
      it.
    - `spawn_subagent(...)` — on-demand. Called when the parent's model
      invokes a Commission-declared subagent. Returns the child run id
      plus the inline summary the parent's loop hands back to the model.

    Production drivers dial `AVP_RESOLVER_URL` over HTTP/JSON-RPC. Tests
    inject `ScriptedResolver` from `avp.agent.mock` for canned outcomes.
    """

    def resolve(self, *, kind: ManagedKind, id: str, ref: JsonValue) -> dict[str, Any]:
        """Dereference one managed ref. Raise `ResolveError` on failure;
        the agent will emit `managed_ref_resolve_failed` and stop."""
        ...

    def spawn_subagent(
        self,
        *,
        run_id: str,
        id: str,
        ref: JsonValue,
        input: dict[str, Any],
    ) -> SubagentSpawnOutcome:
        """Invoke a managed subagent. Raise on transport errors; return an
        outcome with `error` set when the subagent itself failed (the parent
        emits `subagent_failed` either way)."""
        ...
