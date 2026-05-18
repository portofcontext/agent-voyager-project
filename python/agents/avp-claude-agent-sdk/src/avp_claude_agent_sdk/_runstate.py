"""Per-run state holder for AVP trajectory emission."""

from __future__ import annotations

import contextvars
import dataclasses

from avp.agent.sink import EventSink
from avp.content import AVPContentBlock
from avp.pricing import ModelPrice


@dataclasses.dataclass
class ToolCallInfo:
    """Bookkeeping for an in-flight tool call.

    Recorded on `tool_invoked` emission and consumed on `tool_returned`
    to: parent the result under the call's span, stamp `tool_name` (the
    SDK's `ToolResultBlock` doesn't carry it), report `duration_ms`, and
    keep the result on the same `step` as the call.
    """

    span_id: str
    name: str
    step: int
    started_at: float


@dataclasses.dataclass
class RunState:
    """Flat per-run state. One instance per active run, stored in a context-var."""

    trace_id: str
    run_id: str
    sink: EventSink
    prices: dict[str, ModelPrice]
    agent_span_id: str | None = None
    current_turn_span_id: str | None = None
    step: int = 0
    # Set when a UserMessage with ToolResultBlock arrives; cleared when the
    # next AssistantMessage opens a fresh turn. Guards the merge gate in
    # handle_message: consecutive AssistantMessages without an intervening
    # tool result belong to the same LLM call (e.g. thinking + text blocks).
    tool_result_arrived: bool = False
    # tool_use_id → ToolCallInfo. Populated on tool_invoked; popped on
    # tool_returned (so an unmatched result is honestly dropped).
    tool_spans: dict[str, ToolCallInfo] = dataclasses.field(default_factory=dict)
    # Double-stop guard. Flips on the first agent_stopped emit
    # (ResultMessage handler, exception handler, or disconnect() fallback);
    # later handlers no-op so the trajectory only ends once.
    stopped: bool = False
    # Cumulative usage tracking for delta computation across turns. Keys:
    # input, output, cache_read, cache_creation. Reset (silent rebase) when
    # an AssistantMessage reports a cumulative count lower than the last
    # one we saw -- the SDK does this on compaction / subagent dispatch.
    prev_cum: dict[str, int] = dataclasses.field(
        default_factory=lambda: {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_creation": 0,
        }
    )
    # Per-turn accumulator. Filled by every AssistantMessage merged into
    # the open turn; drained on turn close into one avp.assistant_message.
    turn_started_at: float | None = None
    turn_content: list[AVPContentBlock] = dataclasses.field(default_factory=list)
    turn_usage_delta: dict[str, int] = dataclasses.field(
        default_factory=lambda: {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_creation": 0,
        }
    )
    turn_response_model: str | None = None
    turn_stop_reason: str | None = None


_current: contextvars.ContextVar[RunState | None] = contextvars.ContextVar(
    "avp_claude_agent_run", default=None
)


def current_run() -> RunState | None:
    return _current.get()


def set_run(state: RunState) -> contextvars.Token[RunState | None]:
    return _current.set(state)


def reset_run(token: contextvars.Token[RunState | None]) -> None:
    _current.reset(token)
