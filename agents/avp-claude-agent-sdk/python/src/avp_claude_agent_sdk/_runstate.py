"""Per-run state for AVP trajectory emission."""

from __future__ import annotations

import contextvars
import dataclasses
import time
from collections.abc import AsyncIterable
from typing import Any

from avp.content import AVPContentBlock
from avp.envelope import new_span_id
from avp.pricing import ModelPrice, compute_cost
from avp.sink import EventSink
from avp.trajectory import (
    AssistantMessageData,
    AssistantMessageEvent,
    Event,
    Usage,
)

_PROVIDER_NAME = "anthropic"


@dataclasses.dataclass
class TaskInfo:
    """Bookkeeping for a dispatched Task (subagent).

    Populated by `_on_task_started` when the SDK fires `TaskStartedMessage`;
    consumed by `_on_task_notification` to emit the matching
    `subagent_returned`. `span_id` is shared between the invoked and
    returned events (same frame, opened then closed), while
    `parent_span_id` (the turn's span) is what both events sit under.
    """

    # Subagent frame's span; reused by `subagent_returned` (same frame).
    span_id: str
    # Enclosing turn span; parent of both subagent_invoked and subagent_returned.
    parent_span_id: str
    # Turn step the dispatch belongs to.
    step: int
    # Subagent type / name (e.g. "general-purpose"); from `TaskStartedMessage.task_type`.
    task_type: str
    # Monotonic clock at dispatch; drives `subagent_returned.duration_ms`.
    started_at: float


@dataclasses.dataclass
class ToolSpan:
    """Bookkeeping for an in-flight tool dispatch.

    Populated by `avp_pretooluse_hook` on dispatch; popped by
    `avp_posttooluse_hook` on return to assemble the matching
    `tool_returned` (parent under `span_id`, reuse `step` and `name`,
    derive `duration_ms` from `started_at`).
    """

    # `tool_invoked.span_id`; becomes the return event's `parent_span_id`.
    span_id: str
    # Turn step the invocation belongs to; copied onto the return event.
    step: int
    # Tool name; the SDK's `ToolResultBlock` doesn't carry it back.
    name: str
    # Monotonic clock at dispatch; drives `tool_returned.duration_ms`.
    started_at: float


@dataclasses.dataclass
class Turn:
    """Buffered state for one open inference (one Anthropic `message_id`).

    Events produced inside the turn (tool_invoked, subagent_invoked, ...)
    are appended to `emissions` and flushed in arrival order after the
    turn's `assistant_message`. Captured timestamps on each event
    preserve original occurrence times across the deferred flush.
    """

    # Anthropic API response id; one inference per id.
    message_id: str | None
    # 1-based turn counter within the run.
    step: int
    # Monotonic clock at open; used for `duration_ms`.
    started_at: float = dataclasses.field(default_factory=time.monotonic)
    # Turn's own span identity; `parent_span_id` for buffered emissions.
    span_id: str = dataclasses.field(default_factory=new_span_id)
    # Model name from the first chunk (`AssistantMessage.model`).
    response_model: str | None = None
    # API response totals; chunks duplicate the same numbers so
    # last-write-wins converges to the inference's true total.
    usage: Usage = dataclasses.field(default_factory=lambda: Usage(input_tokens=0, output_tokens=0))
    # Last-seen `AssistantMessage.stop_reason` across the chunks.
    stop_reason: str | None = None
    # AVP blocks merged from each chunk in arrival order.
    content: list[AVPContentBlock] = dataclasses.field(default_factory=list)
    # Events captured during the turn; flushed after `assistant_message`.
    emissions: list[Event] = dataclasses.field(default_factory=list)
    # Live tool dispatches keyed by `tool_use_id`. Populated by the
    # PreToolUse hook, popped by the PostToolUse hook to pair returns.
    tool_spans: dict[str, ToolSpan] = dataclasses.field(default_factory=dict)
    # Anthropic service tier from `usage.service_tier`; affects pricing.
    meta_service_tier: str | None = None
    # Cache-creation tokens split by TTL bucket; Anthropic prices these differently.
    meta_cache_creation_5m: int = 0
    meta_cache_creation_1h: int = 0
    # Diagnostic: how many SDK AssistantMessage chunks merged into this turn.
    meta_chunks_merged: int = 0
    # Set once a tool-result for this turn arrives: the inference has ended, so
    # the next AssistantMessage opens a new turn even if it shares (or lacks) a
    # `message_id`. Drain is still deferred to that next message so parallel
    # tool results (which may span several UserMessages) all land on this turn.
    tool_resulted: bool = False


def _turn_has_output(turn: Turn) -> bool:
    """Whether a turn produced anything worth emitting: any buffered event
    (tool_invoked / subagent_*), or any content block other than an empty
    text block. A turn with no content (or only empty text) is degenerate
    and skipped."""
    if turn.emissions:
        return True
    return any(
        not (getattr(b, "type", None) == "text" and not getattr(b, "text", ""))
        for b in turn.content
    )


@dataclasses.dataclass
class RunState:
    """Flat per-run state. One instance per active run."""

    # Prompt the agent was started with
    prompt: str | AsyncIterable[dict[str, Any]] | None
    # Where every event for this run is written. Transport is the caller's choice.
    sink: EventSink
    # Supervisor-issued run identifier; CloudEvents `subject` on every event.
    run_id: str
    # OTel-style 16-byte hex trace id stamped on every event's `data`.
    trace_id: str
    # Per-model price catalog consumed by `compute_cost` at turn drain.
    prices: dict[str, ModelPrice]
    # Commission `enabled_builtin_tools` allow-list (None = expose all). Applied
    # to `agent_started.data.avp.tools` so the merged surface reflects the
    # Commission's subtractive filter over the descriptor's tool bag.
    enabled_builtin_tools: list[str] | None = None
    # Root agent span; parent of every turn / tool / subagent frame.
    # `None` until `agent_started` fires.
    agent_span_id: str | None = None
    # Currently open turn buffer; `None` between turns.
    turn: Turn | None = None
    # Live Task (subagent) dispatches keyed by `tool_use_id`. Populated by
    # `_on_task_started`, popped by `_on_task_notification`.
    #
    # Run-scoped, not turn-scoped. The `Agent` tool dispatches asynchronously:
    # its `tool_result` is a launch receipt that returns in milliseconds, and
    # the child's `TaskNotificationMessage` can arrive many turns later or not
    # at all. Keyed on the turn, the pairing entry died at turn rollover and
    # the frame was never closed. `TaskInfo` captures its own span / parent /
    # step at dispatch, so nothing here depends on the dispatching turn still
    # being open.
    tasks: dict[str, TaskInfo] = dataclasses.field(default_factory=dict)
    # Highest step actually emitted; the next turn opens at `last_step + 1`.
    # Tracked on the run (not derived from the just-drained turn) so a gated
    # empty turn doesn't consume a step number.
    last_step: int = 0
    # `True` once `agent_stopped` has fired; guards against double-emit.
    stopped: bool = False

    async def drain(self) -> Turn | None:
        """Close the open turn: emit one `assistant_message`, then flush
        every buffered event in arrival order. No-op when no turn is open,
        and a no-emit no-op when the turn produced nothing (an empty-output
        inference is not put on the wire, and does not consume a step).
        Clears `self.turn` so the next AssistantMessage opens a fresh one.
        Returns the just-drained `Turn` (or `None` if nothing was emitted).
        """
        if self.turn is None:
            return None
        if self.agent_span_id is None:
            raise RuntimeError("cannot drain turn before agent_started has fired")

        turn = self.turn
        self.turn = None

        if not _turn_has_output(turn):
            return None
        self.last_step = turn.step

        duration_ms = int((time.monotonic() - turn.started_at) * 1000)
        cost_usd, cost_source = compute_cost(
            turn.response_model or "",
            provider=_PROVIDER_NAME,
            input_tokens=turn.usage.input_tokens,
            output_tokens=turn.usage.output_tokens,
            cache_read=turn.usage.cache_read_input_tokens or 0,
            cache_write=turn.usage.cache_creation_input_tokens or 0,
            prices=self.prices,
        )
        meta: dict[str, Any] = {
            "anthropic.message_id": turn.message_id,
            "anthropic.service_tier": turn.meta_service_tier,
            "anthropic.cache_creation.ephemeral_5m_input_tokens": turn.meta_cache_creation_5m,
            "anthropic.cache_creation.ephemeral_1h_input_tokens": turn.meta_cache_creation_1h,
            "claude_agent_sdk.chunks_merged": turn.meta_chunks_merged,
        }
        await self.sink(
            AssistantMessageEvent(
                subject=self.run_id,
                data=AssistantMessageData(
                    trace_id=self.trace_id,
                    span_id=turn.span_id,
                    parent_span_id=self.agent_span_id,
                    meta=meta,
                    step=turn.step,
                    duration_ms=duration_ms,
                    content=turn.content,
                    provider_name=_PROVIDER_NAME,
                    request_model=turn.response_model,
                    response_model=turn.response_model,
                    response_finish_reasons=([turn.stop_reason] if turn.stop_reason else None),
                    usage=turn.usage,
                    cost_usd=cost_usd,
                    cost_source=cost_source,
                ),
            )
        )
        for event in turn.emissions:
            await self.sink(event)

        return turn


# ---------------------------------------------------------------------------
# Ambient run access (asyncio-task-scoped via contextvars)
# ---------------------------------------------------------------------------

_current: contextvars.ContextVar[RunState | None] = contextvars.ContextVar(
    "avp_claude_agent_run", default=None
)


def current_run() -> RunState | None:
    """Read the active `RunState` for this asyncio task / thread, or `None`."""
    return _current.get()


def set_run(state: RunState) -> contextvars.Token[RunState | None]:
    """Bind `state` as the active run; pair with `reset_run(token)` on cleanup."""
    return _current.set(state)


def reset_run(token: contextvars.Token[RunState | None]) -> None:
    """Restore the prior active run using the token returned by `set_run`."""
    _current.reset(token)
