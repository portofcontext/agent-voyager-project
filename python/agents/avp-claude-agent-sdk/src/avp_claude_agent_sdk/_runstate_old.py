"""Per-run state holder for AVP trajectory emission."""

from __future__ import annotations

import contextvars
import dataclasses

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
    `TaskUsage` rollup. `subagent_invoked` fires lazily when the parent
    turn closes (after which the dispatch's `ToolUseBlock` has landed in
    `assistant_message.content` per spec §3 ordering); `subagent_returned`
    fires either inline at close (if the terminal notification already
    arrived) or from `_on_task_notification` (if the notification
    arrives after close).
    """

    task_id: str
    description: str
    task_type: str | None = None
    status: str | None = None
    summary: str | None = None
    usage: dict[str, int] | None = None


@dataclasses.dataclass
class RunState:
    """Flat per-run state. One instance per active run, stored in a context-var."""

    trace_id: str
    run_id: str
    sink: EventSink
    prices: dict[str, ModelPrice]
    agent_span_id: str | None = None
    current_turn_span_id: str | None = None
    # The Anthropic Messages API `id` of the inference owning the open
    # turn. One API call → one `message_id`; the Claude CLI fans the
    # response's content blocks out as one AssistantMessage Python
    # object per block, all stamped with the same id. A turn stays open
    # across every chunk sharing this id, including across interleaved
    # `TaskStartedMessage`s. Reset by `_open_turn`; set on first
    # AssistantMessage of a new turn; transition to a different non-None
    # id is the producer-side close trigger.
    current_message_id: str | None = None
    step: int = 0
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
    # Per-turn accumulator. Filled by every AssistantMessage merged into
    # the open turn; drained on turn close into one avp.assistant_message.
    turn_started_at: float | None = None
    turn_content: list[AVPContentBlock] = dataclasses.field(default_factory=list)
    # Per-turn usage observation. AssistantMessage chunks of one
    # `message_id` carry the API call's response totals (identical on
    # every chunk per the SDK), so we overwrite this on every chunk —
    # last write wins and equals the API total for the inference.
    turn_usage: dict[str, int] = dataclasses.field(
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
