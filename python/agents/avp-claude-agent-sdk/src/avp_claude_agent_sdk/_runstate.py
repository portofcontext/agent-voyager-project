"""Per-run state holder for AVP trajectory emission."""

from __future__ import annotations

import contextvars
import dataclasses
from typing import Any

from avp.agent.sink import EventSink
from avp.content import AVPContentBlock
from avp.pricing import ModelPrice


@dataclasses.dataclass
class ToolCallInfo:
    """Bookkeeping for an in-flight tool or subagent call.

    Recorded on `tool_invoked` / `subagent_invoked` emission and consumed
    on the matching `*_returned` event to: parent the result under the
    call's span, stamp the name (the SDK's `ToolResultBlock` doesn't
    carry it), report `duration_ms`, and keep the result on the same
    `step` as the call. The same shape works for both tool and subagent
    bracketing since both pair by `tool_use_id`.

    `parent_span_id` is the span this call was emitted under (the
    closing turn's `assistant_message` span). Tool returns parent under
    `span_id` (the invocation's span); subagent returns reuse `span_id`
    as the frame and parent under `parent_span_id` instead, per spec §6.
    """

    span_id: str
    parent_span_id: str
    name: str
    step: int
    started_at: float


@dataclasses.dataclass
class TaskInfo:
    """SDK-side data accumulated across a Task subagent's lifecycle.

    `TaskStartedMessage` populates the descriptive head; the eventual
    `TaskNotificationMessage` fills in `status`, `summary`, and the
    `TaskUsage` rollup. Both arrive before the synthetic
    `UserMessage(ToolResultBlock)` that closes the parent's bracket, so
    `subagent_returned` / `subagent_failed` can be emitted with the full
    payload when that user message dispatches.
    """

    task_id: str
    description: str
    task_type: str | None = None
    status: str | None = None
    summary: str | None = None
    usage: dict[str, Any] | None = None


@dataclasses.dataclass
class RunState:
    """Flat per-run state. One instance per active run, stored in a context-var."""

    trace_id: str
    run_id: str
    sink: EventSink
    prices: dict[str, ModelPrice]
    agent_span_id: str | None = None
    current_turn_span_id: str | None = None
    # The span_id of the parent turn that owned the most recent
    # subagent-dispatch batch. Captured when `TaskStartedMessage` closes
    # the parent turn (so the closing `assistant_message` lands before
    # `subagent_invoked`) and reused so sibling dispatches in the same
    # parallel batch parent under the same turn span. Cleared by
    # `_open_turn` when a fresh parent turn opens.
    last_dispatch_turn_span_id: str | None = None
    step: int = 0
    # Set when a UserMessage with ToolResultBlock arrives; cleared when the
    # next AssistantMessage opens a fresh turn. Guards the merge gate in
    # handle_message: consecutive AssistantMessages without an intervening
    # tool result belong to the same LLM call (e.g. thinking + text blocks).
    tool_result_arrived: bool = False
    # tool_use_id → ToolCallInfo. Populated on tool_invoked; popped on
    # tool_returned (so an unmatched result is honestly dropped).
    tool_spans: dict[str, ToolCallInfo] = dataclasses.field(default_factory=dict)
    # tool_use_id → ToolCallInfo for Task tool invocations that resolved
    # to a subagent dispatch (TaskStartedMessage arrived). Populated on
    # subagent_invoked, popped on subagent_returned / subagent_failed.
    # Kept separate from tool_spans so the dispatch path stays explicit.
    subagent_spans: dict[str, ToolCallInfo] = dataclasses.field(default_factory=dict)
    # tool_use_id → TaskInfo. Populated by TaskStartedMessage on the way
    # in, updated with status / summary / usage by TaskNotificationMessage
    # before the synthetic UserMessage(ToolResultBlock) fires.
    task_info: dict[str, TaskInfo] = dataclasses.field(default_factory=dict)
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
