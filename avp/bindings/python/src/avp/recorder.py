"""avp.recorder — the trajectory's ordering and span rules, in one place.

An adapter reports what its harness did; the :class:`Recorder` decides what
goes on the wire and in what order. It is a plain object the adapter calls:
no base class, no agent loop, no callbacks into the adapter.

    rec = Recorder(sink, provider="anthropic")
    await rec.prelude(commission, descriptor)        # run_requested, agent_described
    await rec.start(request_model=..., tools=...)    # agent_started
    await rec.assistant(content, usage, model=...)   # assistant_message + tool_invoked
    await rec.tool_result(call_id, "ok")             # tool_returned
    await rec.stop(StopReason.converged)             # agent_stopped

The Recorder owns:

- ``run_id``, ``trace_id``, span minting and the span tree: agent span, then
  turn span, then ``tool_invoked``, then ``tool_returned`` (subagent frames sit
  beside ``tool_invoked`` under the turn span).
- The step counter. A turn with no output (no content beyond empty text, no
  events) is not put on the wire and does not consume a step.
- Turn buffering: ``assistant_message`` first, then the events the turn
  triggered in arrival order, each keeping the timestamp it was reported at.
- ``tool_invoked`` derived from the ``tool_use`` / ``server_tool_use`` blocks in
  an assistant turn's content, and ``tool_returned`` paired to it by call id
  (``server_tool_result`` blocks pair inline).
- Subagent frames, run-scoped; frames still open at stop close as
  ``abandoned`` and downgrade a ``converged`` stop to ``abandoned``.
- Cost from the price table (``reported`` when the adapter passes
  ``cost_usd``; ``unknown`` when the model is unpriced or the turn carries no
  token counts).
- Idempotent ``stop``, and ``error`` parented under the agent span once started.

While a turn is open, every event reported (tool results, subagent frames,
errors) buffers onto it and lands after its ``assistant_message``, which is
stamped with the time of the turn's last chunk.

Turn delivery. ``assistant(..., turn_key=k)`` merges into the open turn while
``k`` matches and none of the turn's tool calls has returned; a new key, or no
key, closes the previous turn. A turn reported with no key closes at once.
Harnesses that deliver one complete message per inference pass no key;
harnesses that stream one inference as several chunks pass the inference's id.

Behavior is pinned by the language-neutral vectors under
``avp/core/conformance/src/avp_conformance/recorder/v0.1/``; the Rust and
TypeScript Recorders run the same vectors.
"""

from __future__ import annotations

import dataclasses
import json
import time
from collections.abc import Callable
from typing import Any, Literal, Protocol

from avp.commission import Commission
from avp.content import (
    AVPContentBlock,
    ServerToolResultBlock,
    ServerToolUseBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from avp.descriptor import AgentDescriptor, McpServerDecl, SkillDecl, SubagentDecl, ToolDecl
from avp.envelope import ZERO_SPAN_ID, new_event_id, new_span_id, new_trace_id, now_iso
from avp.pricing import COST_SOURCE_REPORTED, COST_SOURCE_UNKNOWN, PriceTable, compute_cost
from avp.sink import EventSink
from avp.trajectory import (
    AgentDescribedData,
    AgentDescribedEvent,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    AssistantMessageData,
    AssistantMessageEvent,
    ErrorCode,
    ErrorOccurredData,
    ErrorOccurredEvent,
    Event,
    RunRequestedData,
    RunRequestedEvent,
    StopReason,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentReturnedData,
    SubagentReturnedEvent,
    SubagentUsage,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    Usage,
)

DispatchTarget = Literal["mcp_server", "local"]

ABANDONED_SUBAGENT_TEXT = (
    "Run ended while this subagent was still running; it never reported a result."
)


class Clock(Protocol):
    """Time source. ``now_iso`` stamps event ``time``; ``monotonic`` (seconds)
    drives every ``duration_ms``."""

    def now_iso(self) -> str: ...
    def monotonic(self) -> float: ...


class Ids(Protocol):
    """Id source for the trace, spans, and CloudEvents ``id``."""

    def trace_id(self) -> str: ...
    def span_id(self) -> str: ...
    def event_id(self) -> str: ...


class SystemClock:
    def now_iso(self) -> str:
        return now_iso()

    def monotonic(self) -> float:
        return time.monotonic()


class RandomIds:
    def trace_id(self) -> str:
        return new_trace_id()

    def span_id(self) -> str:
        return new_span_id()

    def event_id(self) -> str:
        return new_event_id()


@dataclasses.dataclass
class _Call:
    """A tool call seen in assistant content. Kept for the whole run so a
    subagent started by the call can find its turn and input after the call's
    own result has already returned."""

    span_id: str
    turn_span_id: str
    step: int
    name: str
    input: dict[str, Any]
    started_at: float


@dataclasses.dataclass
class _Frame:
    """An open subagent frame; the same span closes it."""

    span_id: str
    parent_span_id: str
    step: int
    name: str
    started_at: float


@dataclasses.dataclass
class _Turn:
    key: str | None
    step: int
    span_id: str
    opened_at: float
    last_chunk_at: float
    # Event `time` for the turn's `assistant_message`: when its last chunk was
    # reported, so it never sorts after the events the turn triggered.
    last_chunk_iso: str
    content: list[AVPContentBlock] = dataclasses.field(default_factory=list)
    usage: Usage | None = None
    response_model: str | None = None
    request_model: str | None = None
    finish_reasons: list[str] | None = None
    meta: dict[str, Any] = dataclasses.field(default_factory=dict)
    cost_usd: float | None = None
    duration_ms: int | None = None
    emissions: list[Event] = dataclasses.field(default_factory=list)
    call_ids: set[str] = dataclasses.field(default_factory=set)
    # A tool call made in this turn has returned: the inference is over, so the
    # next `assistant` opens a new turn even under the same key.
    tool_resulted: bool = False


def _has_output(turn: _Turn) -> bool:
    if turn.emissions:
        return True
    return any(not (b.type == "text" and not b.text) for b in turn.content)  # type: ignore[union-attr]


class Recorder:
    """Builds one run's trajectory from what the adapter reports.

    Args:
        sink: Where events go.
        run_id: CloudEvents ``subject`` on every event; a fresh UUID if omitted.
        provider: ``avp.provider.name`` on ``agent_started`` and every turn,
            and the provider used to resolve bare model names in ``prices``.
        prices: Price table for computed cost. Without one, every turn's cost
            is ``unknown`` unless the adapter reports it.
        dispatch_target: Classifies a tool name as ``mcp_server`` / ``local``
            for ``tool_invoked``. Defaults to the catalog passed to ``start``:
            a tool whose decl carries ``avp.mcp_server_id`` is ``mcp_server``.
        clock, ids: Time and id sources; injectable for deterministic tests.
    """

    def __init__(
        self,
        sink: EventSink,
        *,
        run_id: str | None = None,
        provider: str | None = None,
        prices: PriceTable | None = None,
        dispatch_target: Callable[[str], DispatchTarget] | None = None,
        clock: Clock | None = None,
        ids: Ids | None = None,
    ) -> None:
        self._sink = sink
        self._clock = clock or SystemClock()
        self._ids = ids or RandomIds()
        self.run_id = run_id or self._ids.event_id()
        self.trace_id = self._ids.trace_id()
        self.provider = provider
        self._prices: PriceTable = prices or {}
        self._dispatch_override = dispatch_target
        self._catalog: dict[str, ToolDecl] = {}
        self.agent_span_id: str | None = None
        self._turn: _Turn | None = None
        self._last_step = 0
        self._calls: dict[str, _Call] = {}
        self._open_calls: set[str] = set()
        self._frames: dict[str, _Frame] = {}
        self.stopped = False

    # ── envelope ──────────────────────────────────────────────────────────

    def _envelope(self) -> dict[str, Any]:
        return {"id": self._ids.event_id(), "time": self._clock.now_iso(), "subject": self.run_id}

    def _span(self, span_id: str, parent_span_id: str) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "span_id": span_id, "parent_span_id": parent_span_id}

    def _elapsed_ms(self, since: float) -> int:
        return max(0, int((self._clock.monotonic() - since) * 1000))

    async def _emit_or_buffer(self, event: Event) -> None:
        """Buffer onto the open turn (flushed after its `assistant_message`),
        or emit directly when no turn is open."""
        if self._turn is not None:
            self._turn.emissions.append(event)
        else:
            await self._sink(event)

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def prelude(self, commission: Commission | None, descriptor: AgentDescriptor) -> None:
        """Emit `run_requested` (carrying the Commission and its supervisor
        attribution) then `agent_described`."""
        supervisor = commission.supervisor if commission else None
        await self._sink(
            RunRequestedEvent(
                **self._envelope(),
                data=RunRequestedData(
                    **self._span(self._ids.span_id(), ZERO_SPAN_ID),
                    supervisor_name=supervisor.name if supervisor else None,
                    supervisor_version=supervisor.version if supervisor else None,
                    commission=commission,
                ),
            )
        )
        await self._sink(
            AgentDescribedEvent(
                **self._envelope(),
                data=AgentDescribedData(
                    **self._span(self._ids.span_id(), ZERO_SPAN_ID), descriptor=descriptor
                ),
            )
        )

    async def start(
        self,
        *,
        request_model: str | None = None,
        prompt: str | None = None,
        system_prompt: str | None = None,
        tools: list[ToolDecl] | None = None,
        mcp_servers: list[McpServerDecl] | None = None,
        skills: list[SkillDecl] | None = None,
        subagents: list[SubagentDecl] | None = None,
        session_id: str | None = None,
        thread_id: str | None = None,
        tags: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Emit `agent_started` and open the agent span. ``tools`` is also the
        catalog `tool_invoked` dispatch targets resolve against."""
        self.agent_span_id = self._ids.span_id()
        self._catalog = {t.name: t for t in tools or []}
        await self._sink(
            AgentStartedEvent(
                **self._envelope(),
                data=AgentStartedData(
                    **self._span(self.agent_span_id, ZERO_SPAN_ID),
                    meta=meta or None,
                    provider_name=self.provider,
                    operation_name="invoke_agent",
                    request_model=request_model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    tools=tools,
                    mcp_servers=mcp_servers,
                    skills=skills,
                    subagents=subagents,
                    session_id=session_id,
                    thread_id=thread_id,
                    tags=tags,
                ),
            )
        )

    async def error(self, code: ErrorCode, message: str) -> None:
        """Report `error_occurred` under the agent span (the root before
        `start`). Like every event reported while a turn is open, it lands
        after that turn's `assistant_message`. Not terminal; follow with
        `stop` when the run ends."""
        await self._emit_or_buffer(
            ErrorOccurredEvent(
                **self._envelope(),
                data=ErrorOccurredData(
                    **self._span(self._ids.span_id(), self.agent_span_id or ZERO_SPAN_ID),
                    error_code=code,
                    error_message=message,
                ),
            )
        )

    async def stop(self, reason: StopReason, output: Any = None) -> None:
        """Close the open turn and any open subagent frames, then emit
        `agent_stopped`. Idempotent: only the first call emits."""
        if self.stopped:
            return
        self.stopped = True
        await self.close_turn()
        if self._frames:
            for invocation_id in list(self._frames):
                await self._close_frame(
                    invocation_id, ABANDONED_SUBAGENT_TEXT, StopReason.abandoned
                )
            if reason is StopReason.converged:
                reason = StopReason.abandoned
        await self._sink(
            AgentStoppedEvent(
                **self._envelope(),
                data=AgentStoppedData(
                    **self._span(self._ids.span_id(), self.agent_span_id or ZERO_SPAN_ID),
                    reason=reason,
                    output=output,
                ),
            )
        )

    # ── turns ─────────────────────────────────────────────────────────────

    async def assistant(
        self,
        content: list[AVPContentBlock],
        usage: Usage | None = None,
        *,
        model: str | None = None,
        request_model: str | None = None,
        turn_key: str | None = None,
        finish_reasons: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        cost_usd: float | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Report model output for one inference (or one chunk of it).

        ``model`` is the response model: it goes on the wire as
        ``avp.response.model`` and is the price-table key. When the table
        doesn't know it, cost is computed for ``request_model`` instead.

        Within a turn: content appends, ``usage`` / ``finish_reasons`` /
        ``cost_usd`` / ``duration_ms`` are last-write-wins, ``model`` is
        first-write-wins, and ``meta`` keys merge with later chunks winning.
        Without ``duration_ms`` the turn's duration runs from its first chunk
        to its last.
        """
        if self.agent_span_id is None:
            raise RuntimeError("Recorder.assistant called before start")
        turn = self._turn
        if turn is not None and (
            turn.tool_resulted or turn_key is None or turn.key is None or turn_key != turn.key
        ):
            await self.close_turn()
            turn = None
        now = self._clock.monotonic()
        if turn is None:
            turn = _Turn(
                key=turn_key,
                step=self._last_step + 1,
                span_id=self._ids.span_id(),
                opened_at=now,
                last_chunk_at=now,
                last_chunk_iso=self._clock.now_iso(),
            )
            self._turn = turn
        turn.last_chunk_at = now
        turn.last_chunk_iso = self._clock.now_iso()
        turn.content.extend(content)
        if usage is not None:
            turn.usage = usage
        if turn.response_model is None:
            turn.response_model = model
        if turn.request_model is None:
            turn.request_model = request_model
        if finish_reasons is not None:
            turn.finish_reasons = finish_reasons
        if meta:
            turn.meta.update(meta)
        if cost_usd is not None:
            turn.cost_usd = cost_usd
        if duration_ms is not None:
            turn.duration_ms = duration_ms

        for block in content:
            if isinstance(block, ToolUseBlock | ServerToolUseBlock):
                self._invoke(turn, block.id, block.name, block.input)
            elif isinstance(block, ServerToolResultBlock):
                await self.tool_result(
                    block.tool_use_id,
                    ToolResultBlock(
                        tool_use_id=block.tool_use_id,
                        content=_result_content(block.content),
                        is_error=bool(block.is_error),
                    ),
                )

        if turn_key is None:
            await self.close_turn()

    def _invoke(self, turn: _Turn, call_id: str, name: str, tool_input: dict[str, Any]) -> None:
        span_id = self._ids.span_id()
        self._calls[call_id] = _Call(
            span_id=span_id,
            turn_span_id=turn.span_id,
            step=turn.step,
            name=name,
            input=tool_input,
            started_at=self._clock.monotonic(),
        )
        self._open_calls.add(call_id)
        turn.call_ids.add(call_id)
        turn.emissions.append(
            ToolInvokedEvent(
                **self._envelope(),
                data=ToolInvokedData(
                    **self._span(span_id, turn.span_id),
                    step=turn.step,
                    tool_call_id=call_id,
                    tool_name=name,
                    tool_input=tool_input,
                    tool_dispatch_target=self._dispatch_target(name),
                ),
            )
        )

    def _dispatch_target(self, name: str) -> DispatchTarget:
        if self._dispatch_override is not None:
            return self._dispatch_override(name)
        decl = self._catalog.get(name)
        return "mcp_server" if decl is not None and decl.mcp_server_id else "local"

    async def close_turn(self) -> None:
        """Close the open turn now: emit its `assistant_message` (with cost),
        then its buffered events. A turn with no output emits nothing and
        frees its step. No-op when no turn is open.

        Adapters rarely need this directly: a new turn key, a keyless turn,
        and `stop` all close the open turn."""
        turn = self._turn
        if turn is None:
            return
        self._turn = None
        if not _has_output(turn):
            return
        self._last_step = turn.step
        usage = turn.usage or Usage(input_tokens=0, output_tokens=0)
        if turn.cost_usd is not None:
            cost_usd, cost_source = turn.cost_usd, COST_SOURCE_REPORTED
        elif usage.input_tokens == 0 and usage.output_tokens == 0:
            cost_usd, cost_source = 0.0, COST_SOURCE_UNKNOWN
        else:
            # Providers often answer with a dated snapshot id the table lacks
            # (`gpt-4o-mini-2024-07-18`); price it as the requested model then.
            for model in dict.fromkeys(m for m in (turn.response_model, turn.request_model) if m):
                cost_usd, cost_source = compute_cost(
                    model,
                    provider=self.provider,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read=usage.cache_read_input_tokens or 0,
                    cache_write=usage.cache_creation_input_tokens or 0,
                    prices=self._prices,
                )
                if cost_source != COST_SOURCE_UNKNOWN:
                    break
            else:
                cost_usd, cost_source = 0.0, COST_SOURCE_UNKNOWN
        duration_ms = (
            turn.duration_ms
            if turn.duration_ms is not None
            else max(0, int((turn.last_chunk_at - turn.opened_at) * 1000))
        )
        assert self.agent_span_id is not None
        await self._sink(
            AssistantMessageEvent(
                **{**self._envelope(), "time": turn.last_chunk_iso},
                data=AssistantMessageData(
                    **self._span(turn.span_id, self.agent_span_id),
                    meta=turn.meta or None,
                    step=turn.step,
                    duration_ms=duration_ms,
                    content=turn.content,
                    provider_name=self.provider,
                    request_model=turn.request_model or turn.response_model,
                    response_model=turn.response_model,
                    response_finish_reasons=turn.finish_reasons,
                    usage=usage,
                    cost_usd=cost_usd,
                    cost_source=cost_source,
                ),
            )
        )
        for event in turn.emissions:
            await self._sink(event)

    # ── tools ─────────────────────────────────────────────────────────────

    async def tool_result(
        self,
        call_id: str,
        content: str | list[Any] | ToolResultBlock,
        *,
        is_error: bool = False,
        structured_content: dict[str, Any] | None = None,
    ) -> None:
        """Report the result of a tool call seen in assistant content. Emits
        the paired `tool_returned`; a result for an unknown or already
        returned call id is dropped."""
        if call_id not in self._open_calls:
            return
        self._open_calls.discard(call_id)
        call = self._calls[call_id]
        block = (
            content
            if isinstance(content, ToolResultBlock)
            else ToolResultBlock(
                tool_use_id=call_id,
                content=content,
                structured_content=structured_content,
                is_error=is_error,
            )
        )
        event = ToolReturnedEvent(
            **self._envelope(),
            data=ToolReturnedData(
                **self._span(self._ids.span_id(), call.span_id),
                step=call.step,
                tool_call_id=call_id,
                tool_name=call.name,
                duration_ms=self._elapsed_ms(call.started_at),
                tool_result=block,
            ),
        )
        if self._turn is not None and call_id in self._turn.call_ids:
            self._turn.tool_resulted = True
        await self._emit_or_buffer(event)

    # ── subagents ─────────────────────────────────────────────────────────

    async def subagent_start(
        self,
        invocation_id: str,
        name: str,
        input: dict[str, Any] | None = None,
        *,
        description: str | None = None,
    ) -> None:
        """Open a subagent frame. When ``invocation_id`` is a tool call seen in
        assistant content, the frame sits under that call's turn and defaults
        its input to the call's input."""
        call = self._calls.get(invocation_id)
        if call is not None:
            parent, step = call.turn_span_id, call.step
            frame_input = call.input if input is None else input
        elif self._turn is not None:
            parent, step = self._turn.span_id, self._turn.step
            frame_input = input or {}
        else:
            parent, step = self.agent_span_id or ZERO_SPAN_ID, self._last_step
            frame_input = input or {}
        span_id = self._ids.span_id()
        self._frames[invocation_id] = _Frame(
            span_id=span_id,
            parent_span_id=parent,
            step=step,
            name=name,
            started_at=self._clock.monotonic(),
        )
        await self._emit_or_buffer(
            SubagentInvokedEvent(
                **self._envelope(),
                data=SubagentInvokedData(
                    **self._span(span_id, parent),
                    step=step,
                    subagent_name=name,
                    subagent_description=description,
                    subagent_invocation_id=invocation_id,
                    subagent_input=frame_input,
                ),
            )
        )

    async def subagent_result(
        self,
        invocation_id: str,
        text: str,
        reason: StopReason = StopReason.converged,
        *,
        usage: SubagentUsage | None = None,
        structured: Any = None,
    ) -> None:
        """Close a subagent frame. A result for an unknown or already closed
        frame is dropped."""
        if invocation_id in self._frames:
            await self._close_frame(invocation_id, text, reason, usage=usage, structured=structured)

    async def _close_frame(
        self,
        invocation_id: str,
        text: str,
        reason: StopReason,
        *,
        usage: SubagentUsage | None = None,
        structured: Any = None,
    ) -> None:
        frame = self._frames.pop(invocation_id)
        await self._emit_or_buffer(
            SubagentReturnedEvent(
                **self._envelope(),
                data=SubagentReturnedData(
                    **self._span(frame.span_id, frame.parent_span_id),
                    step=frame.step,
                    subagent_name=frame.name,
                    subagent_invocation_id=invocation_id,
                    duration_ms=self._elapsed_ms(frame.started_at),
                    subagent_result_text=text,
                    subagent_result_structured=structured,
                    subagent_reason=reason,
                    subagent_usage=usage,
                ),
            )
        )


def _result_content(content: Any) -> str:
    """Coerce a server tool's inline result (provider-shaped, not AVP blocks)
    into `ToolResultBlock.content`: strings pass through, anything else is
    JSON-encoded."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, default=str)
    except (TypeError, ValueError):
        return str(content)
