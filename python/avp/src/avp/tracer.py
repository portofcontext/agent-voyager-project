"""AVPTracer — drop-in AVP v0.1 instrumentation for an existing agent loop.

The `avp` package's `AVPAgent` owns the loop: you hand it a Commission and a
ModelDriver, it runs and emits events. That's the right shape for greenfield
agents. For agents you already wrote — a while-loop already calling some
provider SDK directly — you don't want to give up the loop. You just want
AVP events on the wire.

This module is for that case. The tracer:

  - Maintains the same `RunStateSnapshot` shape `AVPAgent` does.
  - Emits the same wire events through an `on_event` callback.
  - Surfaces subagent invocation as a context manager that opens a frame
    span and re-parents nested events under it — same wire shape as
    `AVPAgent` produces.

It does NOT:

  - Run a loop for you. You write the while.
  - Call the model. You call your SDK; you record the response.
  - Dispatch tools. You execute tools; you record their outputs.
  - Enforce caps. v0.1 leaves bounded execution to the caller; agents
    that need it wire it externally (subprocess timeouts, supervisor
    SIGKILL, etc.).

The wire events emitted MUST be byte-equivalent to what `AVPAgent` produces
for the same Commission and the same set of (turn, tool, subagent) operations.
That's the contract: consumers downstream of the wire can't tell whether the
trajectory came from a agent or a traced loop.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from avp.enums import ErrorCode, StopReason
from avp.types import (
    ZERO_SPAN_ID,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    Commission,
    CostRecordedData,
    CostRecordedEvent,
    ErrorOccurredData,
    ErrorOccurredEvent,
    ModelTurnEndedData,
    ModelTurnEndedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    RunStateSnapshot,
    Subagent,
    SubagentFailedData,
    SubagentFailedEvent,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentReturnedData,
    SubagentReturnedEvent,
    TextEmittedData,
    TextEmittedEvent,
    ToolFailedData,
    ToolFailedEvent,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    new_span_id,
    new_trace_id,
    now_iso,
)


def _monotonic_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


# ── Active-tracer registry (contextvar) ───────────────────────────────────────
#
# `with AVPTracer(...) as tracer:` pushes the tracer onto a ContextVar so
# instrumentation code (provider-specific traced clients) can find it
# without taking it as an explicit argument. Same shape as the OTel
# `current_span()` pattern.
#
# This is what lets `wrap_anthropic(client)` (a pure function returning a
# proxy) work: the proxy doesn't hold a tracer reference; it asks for the
# active one on every call. So a long-lived wrapped client picked up at
# module import time emits to whichever tracer is in scope at call time.

_ACTIVE_TRACER: ContextVar[AVPTracer | None] = ContextVar("avp_active_tracer", default=None)


def current_tracer() -> AVPTracer:
    """Return the active AVPTracer set by an enclosing `with AVPTracer(...)`.

    Raises RuntimeError if no tracer is active. Instrumentation code that
    REQUIRES a tracer (the model-call path inside wrap_anthropic, for
    instance) uses this to fail loudly rather than silently drop events.
    """
    t = _ACTIVE_TRACER.get()
    if t is None:
        raise RuntimeError(
            "No active AVPTracer. Wrap your code in "
            "`with AVPTracer(config, on_event=...):` before calling "
            "instrumented APIs."
        )
    return t


def get_current_tracer() -> AVPTracer | None:
    """Like current_tracer() but returns None instead of raising. Use this
    from code that should silently skip instrumentation when no tracer is
    active — most call sites prefer the strict form so a missing context
    is loud."""
    return _ACTIVE_TRACER.get()


# ── Run state (shared between top-level tracer and nested subagent scopes) ────


@dataclass
class _Frame:
    """Per-scope mutable state. Top-level run = the tracer's own _Frame;
    each `with tracer.subagent(...)` pushes a new Frame whose `parent_span_id`
    is the frame span of the subagent invocation. Tools/turns inside a
    subagent scope parent under the inner frame; the parent's accounting
    state is shared."""

    span_id: str
    trace_id: str
    parent_span_id_for_children: str  # what newly-created turn spans set as parent


@dataclass
class _RunState:
    """Cumulative run-level state. ONE per AVPTracer; subagent scopes
    contribute to it (their spend rolls up into the parent's snapshot)."""

    started_at: str
    started_monotonic_ms: int
    total_turns: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    tokens_input_total: int = 0
    tokens_output_total: int = 0
    tokens_cache_read_total: int = 0
    tokens_cache_write_total: int = 0
    tools_invoked: dict[str, int] = field(default_factory=dict)

    def snapshot(self) -> RunStateSnapshot:
        return RunStateSnapshot(
            total_cost_usd=self.total_cost_usd,
            total_tokens=self.total_tokens,
            total_turns=self.total_turns,
            tokens_input_total=self.tokens_input_total or None,
            tokens_output_total=self.tokens_output_total or None,
            tokens_cache_read_total=self.tokens_cache_read_total or None,
            tokens_cache_write_total=self.tokens_cache_write_total or None,
            tools_invoked=dict(self.tools_invoked) or None,
            started_at=self.started_at,
            duration_ms=max(0, _monotonic_ms() - self.started_monotonic_ms),
        )


# ── Public scope objects (returned from context managers) ────────────────────


class TurnRecorder:
    """Returned from `tracer.turn()` / `subagent.turn()`. Call `.record(...)`
    once with the model response's usage/text. The tracer emits
    `model_turn_ended` (and `text_emitted` if text was present) on
    `__exit__`."""

    def __init__(self, tracer: AVPTracer, span_id: str, parent_span_id: str, step: int) -> None:
        self._tracer = tracer
        self._span_id = span_id
        self._parent_span_id = parent_span_id
        self._step = step
        self._t0 = time.monotonic()
        self._recorded = False
        self._tokens_input = 0
        self._tokens_output = 0
        self._cost_usd = 0.0
        self._cost_source: str = "computed"
        self._cache_read: int | None = None
        self._cache_write: int | None = None
        self._reasoning_output: int | None = None
        self._text: str | None = None
        self._response_model: str | None = None
        self._finish_reasons: list[str] | None = None
        self._duration_ms: int | None = None
        self._tool_uses: list[dict[str, Any]] = []

    def record(
        self,
        *,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
        cost_source: str = "computed",
        text: str | None = None,
        cache_read: int | None = None,
        cache_write: int | None = None,
        reasoning_output: int | None = None,
        response_model: str | None = None,
        finish_reasons: list[str] | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Record the model's response for this turn. Single call per turn.

        `cost_source` tags the provenance of `cost_usd` on the wire under
        `avp.cost.source` (one of: "computed", "reported", "unknown").
        Defaults to "computed" — most callers compute cost from a local
        price table; pass "reported" if you're forwarding a number the
        API gave you back."""
        if self._recorded:
            raise RuntimeError("TurnRecorder.record() called twice for one turn")
        self._recorded = True
        self._tokens_input = tokens_input
        self._tokens_output = tokens_output
        self._cost_usd = cost_usd
        self._cost_source = cost_source
        self._cache_read = cache_read
        self._cache_write = cache_write
        self._reasoning_output = reasoning_output
        self._text = text
        self._response_model = response_model
        self._finish_reasons = finish_reasons
        self._duration_ms = duration_ms

    @property
    def span_id(self) -> str:
        """The model_turn span_id. Useful when the caller needs to parent
        sub-events (e.g., text emitted from inside this turn) themselves —
        though the tracer emits the text_emitted block automatically when
        `text=` is supplied to `record()`."""
        return self._span_id


class ToolCallRecorder:
    """Returned from `tracer.tool()`. Call `.record(output)` for success or
    `.fail(error)` for an execution error. If neither is called by `__exit__`,
    the tool is treated as failed with a generic message."""

    def __init__(
        self,
        tracer: AVPTracer,
        span_id: str,
        parent_span_id: str,
        step: int,
        *,
        call_id: str,
        name: str,
    ) -> None:
        self._tracer = tracer
        self._span_id = span_id
        self._parent_span_id = parent_span_id
        self._step = step
        self._call_id = call_id
        self._name = name
        self._t0 = time.monotonic()
        self._outcome: tuple[str, str | None, Any | None, str | None] | None = None
        # outcome: ("ok", text, structured, None) | ("error", err_msg, None, code) | ("rejected", text, None, reason)

    def record(self, output: str, *, structured: Any = None) -> None:
        """Record successful tool output. `structured` surfaces on
        `tool_returned.data["avp.tool.result.structured"]`."""
        self._outcome = ("ok", output, structured, None)

    def fail(self, error: str, *, code: int | None = None) -> None:
        """Record an execution error. Emits `tool_failed`."""
        self._outcome = ("error", error, None, code)

    def reject(self, output: str, *, reason: str | None = None) -> None:
        """Record a soft rejection (e.g., supervisor declined). Emits
        `tool_returned` with `avp.tool.rejected=true`."""
        self._outcome = ("rejected", output, None, reason)


class SubagentScope:
    """Returned from `tracer.subagent(...)`. Inside the `with` block, calls
    to `scope.turn()` / `scope.tool()` emit nested events under the
    subagent's frame span. On exit, the tracer emits `subagent_returned`
    with the result text + usage rollup recorded via `scope.record_result()`,
    or `subagent_failed` if `scope.fail()` was called."""

    def __init__(
        self,
        tracer: AVPTracer,
        *,
        subagent: Subagent,
        invocation_id: str,
        frame_span_id: str,
        parent_frame_span_id: str,
        invocation_input: dict[str, Any],
        step: int,
    ) -> None:
        self._tracer = tracer
        self._subagent = subagent
        self._invocation_id = invocation_id
        self._frame_span_id = frame_span_id
        self._parent_frame_span_id = parent_frame_span_id
        self._invocation_input = invocation_input
        self._step = step
        self._t0 = time.monotonic()
        # Nested usage tally for this subagent only (so the rollup on
        # subagent_returned reflects the subagent's spend, not the parent's).
        self._sub_state = _RunState(
            started_at=now_iso(),
            started_monotonic_ms=_monotonic_ms(),
        )
        self._result_text: str | None = None
        self._result_structured: Any | None = None
        self._reason: StopReason = StopReason.converged
        self._error: str | None = None
        self._error_code: str | None = None

    @property
    def frame_span_id(self) -> str:
        return self._frame_span_id

    @contextmanager
    def turn(self) -> Iterator[TurnRecorder]:
        """Open a model turn nested under the subagent's frame."""
        with self._tracer._turn_under_scope(self) as turn:
            yield turn

    @contextmanager
    def tool(self, *, call_id: str, name: str, input: dict[str, Any]) -> Iterator[ToolCallRecorder]:
        """Open a tool call nested under the subagent's frame."""
        with self._tracer._tool_under_scope(self, call_id=call_id, name=name, input=input) as tool:
            yield tool

    def record_result(
        self,
        text: str,
        *,
        structured: Any | None = None,
        reason: StopReason | str = StopReason.converged,
    ) -> None:
        """Record the subagent's final output. The tracer emits
        `subagent_returned` on `__exit__`."""
        self._result_text = text
        self._result_structured = structured
        self._reason = StopReason(reason) if isinstance(reason, str) else reason

    def fail(self, error: str, *, code: str | None = None) -> None:
        """Record a subagent failure. The tracer emits `subagent_failed`
        on `__exit__` (instead of `subagent_returned`)."""
        self._error = error
        self._error_code = code


# ── The tracer ────────────────────────────────────────────────────────────────


class AVPTracer:
    """Owns the AVP wire for an agent loop the caller controls.

    Usage outline:

        with AVPTracer(config, on_event=publish) as tracer:
            while True:
                with tracer.turn() as turn:
                    resp = client.messages.create(...)
                    turn.record(tokens_input=..., tokens_output=..., cost_usd=..., text=...)
                if converged(resp):
                    tracer.converged()
                    break
                for tc in tool_calls(resp):
                    with tracer.tool(call_id=tc.id, name=tc.name, input=tc.input) as t:
                        out = run(tc)
                        t.record(out)

    The caller owns termination. v0.1 leaves bounded execution out of the
    spec — agents that need it wire it externally (subprocess timeouts,
    supervisor SIGKILL, model-driven convergence, etc.).
    """

    def __init__(
        self,
        config: Commission,
        on_event: Callable[[BaseModel], None],
        *,
        provider: str | None = None,
    ) -> None:
        self.config = config
        self._on_event = on_event
        self._provider = provider
        self._trace_id = new_trace_id()
        self._agent_span_id = new_span_id()
        self._scope_stack: list[SubagentScope] = []
        self._state = _RunState(
            started_at=now_iso(),
            started_monotonic_ms=_monotonic_ms(),
        )
        self._sa_seq = itertools.count(1)
        self._step = 0
        self._stop_reason: StopReason | None = None
        self._entered = False
        self._exited = False
        self._cv_token: Token[AVPTracer | None] | None = None
        # For subagents declared in Commission — we look these up by name when
        # the caller uses tracer.subagent(name=...).
        self._declared_subagents: dict[str, Subagent] = {
            sa.name: sa for sa in (config.subagents or [])
        }

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def __enter__(self) -> AVPTracer:
        if self._entered:
            raise RuntimeError("AVPTracer cannot be reused; create a new instance per run")
        self._entered = True
        # Push self onto the active-tracer ContextVar so wrap_anthropic-
        # style proxies and module-level helpers (avp.tracer.tool() etc.)
        # find this tracer without taking it as an explicit argument.
        self._cv_token = _ACTIVE_TRACER.set(self)
        self._emit_agent_started()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._exited:
            return
        self._exited = True
        try:
            if exc_type is not None and self._stop_reason is None:
                self._stop_reason = StopReason.error
            elif self._stop_reason is None:
                # The caller exited the loop without calling converged().
                # Default to converged.
                self._stop_reason = StopReason.converged
            self._emit_agent_stopped(self._stop_reason)
        finally:
            # Always pop, even if agent_stopped emission raised.
            if self._cv_token is not None:
                _ACTIVE_TRACER.reset(self._cv_token)
                self._cv_token = None

    # ── Control signals ─────────────────────────────────────────────────────

    def converged(self) -> None:
        """Mark the run as converged. The tracer emits `agent_stopped`
        with `reason=converged` on `__exit__`."""
        if self._stop_reason is None:
            self._stop_reason = StopReason.converged

    @property
    def state(self) -> RunStateSnapshot:
        """Current cumulative state. Read-only snapshot."""
        return self._state.snapshot()

    @property
    def trace_id(self) -> str:
        """The OTel trace ID for this run. Used by delegated emitters
        (e.g., avp_claude_agent's translator in active-tracer mode) to
        nest their events under this tracer's span tree."""
        return self._trace_id

    @property
    def agent_span_id(self) -> str:
        """The OTel span ID of the agent root span (parent of all
        turn / tool spans). Delegated emitters parent their top-level
        spans under this so the trajectory remains one tree."""
        return self._agent_span_id

    @property
    def on_event(self) -> Callable[[BaseModel], None]:
        """The callback this tracer emits events to. Exposed so
        delegated emitters route their events through the same sink."""
        return self._on_event

    # ── Span helpers ────────────────────────────────────────────────────────

    def _current_parent_span(self) -> str:
        """Where new turn / tool spans should attach. The agent span when no
        subagent is active, the innermost subagent's frame span otherwise."""
        if self._scope_stack:
            return self._scope_stack[-1]._frame_span_id
        return self._agent_span_id

    def _own_span(self, parent_span_id: str) -> dict[str, str]:
        return {
            "trace_id": self._trace_id,
            "span_id": new_span_id(),
            "parent_span_id": parent_span_id,
        }

    def _shared_span(self, span_id: str, parent_span_id: str) -> dict[str, str]:
        return {
            "trace_id": self._trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
        }

    # ── Emission ────────────────────────────────────────────────────────────

    def _emit(self, event: BaseModel) -> None:
        self._on_event(event)

    def _emit_agent_started(self) -> None:
        cfg = self.config
        # The tracer doesn't enumerate agent-built-in tools (it has no
        # agent_builtin_tools input). Tools surface only via MCP or via
        # whatever wrapper drives the loop. Honest-null when the wrapper
        # doesn't push them in.
        tools_meta = None
        subagents_meta = None
        if cfg.subagents:
            subagents_meta = [
                {
                    "name": sa.name,
                    "description": sa.description,
                    **({"inputSchema": sa.inputSchema} if sa.inputSchema is not None else {}),
                }
                for sa in cfg.subagents
            ]
        data_kwargs: dict[str, Any] = {
            "trace_id": self._trace_id,
            "span_id": self._agent_span_id,
            "parent_span_id": ZERO_SPAN_ID,
            "prompt": cfg.prompt,
            "system_prompt": cfg.system_prompt,
            "tools": tools_meta,
            "skills": [{"name": s.name, "avp.source": s.avp_source} for s in (cfg.skills or [])]
            or None,
            "subagents": subagents_meta,
        }
        if cfg.model:
            data_kwargs["gen_ai.request.model"] = cfg.model
        if self._provider:
            data_kwargs["gen_ai.provider.name"] = self._provider
        if cfg.thread_id:
            data_kwargs["avp.thread_id"] = cfg.thread_id
        if cfg.tags:
            data_kwargs["avp.tags"] = cfg.tags
        if cfg.meta:
            data_kwargs["avp.meta"] = cfg.meta
        self._emit(
            AgentStartedEvent(
                subject=cfg.run_id,
                data=AgentStartedData(**data_kwargs),
            )
        )

    def _emit_agent_stopped(self, reason: StopReason) -> AgentStoppedEvent:
        snap = self._state.snapshot()
        ev = AgentStoppedEvent(
            subject=self.config.run_id,
            data=AgentStoppedData(
                trace_id=self._trace_id,
                span_id=self._agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                **{
                    "avp.reason": reason,
                    "avp.state": snap,
                    "avp.total_tokens": snap.total_tokens,
                    "avp.total_cost_usd": snap.total_cost_usd,
                    "avp.total_turns": snap.total_turns,
                    "avp.duration_ms": snap.duration_ms,
                },
            ),
        )
        self._emit(ev)
        return ev

    # ── Turn ────────────────────────────────────────────────────────────────

    @contextmanager
    def turn(self) -> Iterator[TurnRecorder]:
        """Open a model turn at the top level (or under the active subagent
        scope, if one is open). Emits `model_turn_started` on enter and
        `model_turn_ended` + optional `text_emitted` + `cost_recorded` on
        exit."""
        parent_span = self._current_parent_span()
        with self._open_turn(parent_span) as turn:
            yield turn

    @contextmanager
    def _turn_under_scope(self, scope: SubagentScope) -> Iterator[TurnRecorder]:
        """Variant used inside a subagent scope."""
        with self._open_turn(scope._frame_span_id, scope=scope) as turn:
            yield turn

    @contextmanager
    def _open_turn(
        self, parent_span_id: str, *, scope: SubagentScope | None = None
    ) -> Iterator[TurnRecorder]:
        self._step += 1
        turn_span_id = new_span_id()
        self._emit(
            ModelTurnStartedEvent(
                subject=self.config.run_id,
                data=ModelTurnStartedData(
                    **self._shared_span(turn_span_id, parent_span_id),
                    step=self._step,
                ),
            )
        )
        recorder = TurnRecorder(self, turn_span_id, parent_span_id, self._step)
        try:
            yield recorder
        finally:
            self._close_turn(recorder, scope=scope)

    def _close_turn(self, recorder: TurnRecorder, *, scope: SubagentScope | None) -> None:
        cfg = self.config
        duration_ms = (
            recorder._duration_ms
            if recorder._duration_ms is not None
            else int((time.monotonic() - recorder._t0) * 1000)
        )
        ended_kwargs: dict[str, Any] = {
            "gen_ai.usage.input_tokens": recorder._tokens_input,
            "gen_ai.usage.output_tokens": recorder._tokens_output,
            "avp.cost_usd": recorder._cost_usd,
            "avp.cost.source": recorder._cost_source,
        }
        if recorder._cache_read is not None:
            ended_kwargs["gen_ai.usage.cache_read.input_tokens"] = recorder._cache_read
        if recorder._cache_write is not None:
            ended_kwargs["gen_ai.usage.cache_creation.input_tokens"] = recorder._cache_write
        if recorder._reasoning_output is not None:
            ended_kwargs["gen_ai.usage.reasoning.output_tokens"] = recorder._reasoning_output
        if recorder._response_model is not None:
            ended_kwargs["gen_ai.response.model"] = recorder._response_model
        if recorder._finish_reasons:
            ended_kwargs["gen_ai.response.finish_reasons"] = recorder._finish_reasons
        self._emit(
            ModelTurnEndedEvent(
                subject=cfg.run_id,
                data=ModelTurnEndedData(
                    **self._shared_span(recorder._span_id, recorder._parent_span_id),
                    step=recorder._step,
                    duration_ms=duration_ms,
                    **ended_kwargs,
                ),
            )
        )

        # Update accounting. Subagent scopes accumulate to the parent state
        # AND to the scope's own _sub_state (which surfaces on
        # subagent_returned.avp.subagent.usage).
        self._accumulate(
            tokens_input=recorder._tokens_input,
            tokens_output=recorder._tokens_output,
            cost_usd=recorder._cost_usd,
            cache_read=recorder._cache_read or 0,
            cache_write=recorder._cache_write or 0,
            scope=scope,
        )

        if recorder._text:
            self._emit(
                TextEmittedEvent(
                    subject=cfg.run_id,
                    data=TextEmittedData(
                        **self._own_span(recorder._span_id),
                        step=recorder._step,
                        **{"avp.text": recorder._text},
                    ),
                )
            )

        # cost_recorded fires per turn at the run level (not per subagent
        # scope) — same as AVPAgent.
        self._emit(
            CostRecordedEvent(
                subject=cfg.run_id,
                data=CostRecordedData(
                    **self._own_span(recorder._span_id),
                    **{"avp.state": self._state.snapshot()},
                ),
            )
        )

    def accumulate_external(
        self,
        *,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
        cache_read: int = 0,
        cache_write: int = 0,
    ) -> None:
        """Push per-turn spend from a delegated emitter into this tracer's
        cumulative state.

        Used when a traced client (e.g., avp_claude_agent's translator in
        delegated mode) is emitting events under this tracer's trace_id
        but tracking its own internal totals. Without this push, the
        parent's `agent_stopped.avp_state` shows zeros even though the
        wire shows real per-turn cost.

        Equivalent to `_accumulate(scope=None)` but exposed for
        cross-package use.
        """
        self._accumulate(
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
            cache_read=cache_read,
            cache_write=cache_write,
            scope=None,
        )

    def _accumulate(
        self,
        *,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
        cache_read: int,
        cache_write: int,
        scope: SubagentScope | None,
    ) -> None:
        st = self._state
        st.total_cost_usd += cost_usd
        st.total_tokens += tokens_input + tokens_output
        st.tokens_input_total += tokens_input
        st.tokens_output_total += tokens_output
        if cache_read:
            st.tokens_cache_read_total += cache_read
        if cache_write:
            st.tokens_cache_write_total += cache_write
        st.total_turns += 1
        if scope is not None:
            ss = scope._sub_state
            ss.total_cost_usd += cost_usd
            ss.total_tokens += tokens_input + tokens_output
            ss.tokens_input_total += tokens_input
            ss.tokens_output_total += tokens_output
            if cache_read:
                ss.tokens_cache_read_total += cache_read
            if cache_write:
                ss.tokens_cache_write_total += cache_write
            ss.total_turns += 1

    # ── Tool ────────────────────────────────────────────────────────────────

    @contextmanager
    def tool(self, *, call_id: str, name: str, input: dict[str, Any]) -> Iterator[ToolCallRecorder]:
        """Open a tool call. The caller dispatches the tool inside the block
        and calls `.record(output)` (or `.fail(error)`). Emits `tool_invoked`
        on enter and `tool_returned` / `tool_failed` on exit."""
        parent_span = self._current_parent_span()
        with self._open_tool(parent_span, call_id=call_id, name=name, input=input) as t:
            yield t

    @contextmanager
    def _tool_under_scope(
        self, scope: SubagentScope, *, call_id: str, name: str, input: dict[str, Any]
    ) -> Iterator[ToolCallRecorder]:
        with self._open_tool(scope._frame_span_id, call_id=call_id, name=name, input=input) as t:
            yield t

    @contextmanager
    def _open_tool(
        self, parent_span_id: str, *, call_id: str, name: str, input: dict[str, Any]
    ) -> Iterator[ToolCallRecorder]:
        cfg = self.config
        tool_span_id = new_span_id()
        self._state.tools_invoked[name] = self._state.tools_invoked.get(name, 0) + 1
        self._emit(
            ToolInvokedEvent(
                subject=cfg.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, parent_span_id),
                    step=self._step,
                    **{
                        "gen_ai.tool.call.id": call_id,
                        "gen_ai.tool.name": name,
                        "gen_ai.tool.call.arguments": dict(input),
                    },
                ),
            )
        )
        recorder = ToolCallRecorder(
            self, tool_span_id, parent_span_id, self._step, call_id=call_id, name=name
        )
        try:
            yield recorder
        finally:
            self._close_tool(recorder)

    def _close_tool(self, recorder: ToolCallRecorder) -> None:
        cfg = self.config
        outcome = recorder._outcome
        duration_ms = max(1, int((time.monotonic() - recorder._t0) * 1000))
        if outcome is None:
            # Block exited without recording — treat as failure with a generic message.
            outcome = ("error", "tool block exited without recording an outcome", None, None)

        kind, payload, structured, code_or_reason = outcome
        if kind == "error":
            failed_kwargs: dict[str, Any] = {
                "step": recorder._step,
                "gen_ai.tool.call.id": recorder._call_id,
                "gen_ai.tool.name": recorder._name,
                "avp.tool.error": payload,
            }
            if isinstance(code_or_reason, int):
                failed_kwargs["avp.tool.error.code"] = code_or_reason
            self._emit(
                ToolFailedEvent(
                    subject=cfg.run_id,
                    data=ToolFailedData(
                        **self._shared_span(recorder._span_id, recorder._parent_span_id),
                        **failed_kwargs,
                    ),
                )
            )
            return

        returned_kwargs: dict[str, Any] = {
            "step": recorder._step,
            "duration_ms": duration_ms,
            "gen_ai.tool.call.id": recorder._call_id,
            "gen_ai.tool.name": recorder._name,
            "avp.tool.result.text": payload,
        }
        if structured is not None:
            returned_kwargs["avp.tool.result.structured"] = structured
        if kind == "rejected":
            returned_kwargs["avp.tool.rejected"] = True
            if code_or_reason:
                returned_kwargs["avp.tool.rejection_reason"] = code_or_reason
        self._emit(
            ToolReturnedEvent(
                subject=cfg.run_id,
                data=ToolReturnedData(
                    **self._shared_span(recorder._span_id, recorder._parent_span_id),
                    **returned_kwargs,
                ),
            )
        )

    # ── Subagent ───────────────────────────────────────────────────────────

    @contextmanager
    def subagent(
        self, *, name: str, input: dict[str, Any] | None = None
    ) -> Iterator[SubagentScope]:
        """Open a subagent frame. The subagent's `name` MUST match a
        `Commission.subagents[].name`. Inside the block, use `scope.turn()` /
        `scope.tool()` for the subagent's nested events; call
        `scope.record_result(text)` before exit, or `scope.fail(error)` to
        emit `subagent_failed` instead.

        Emits `subagent_invoked` on enter, plus either `subagent_returned`
        or `subagent_failed` on exit. The frame span_id is shared across
        the pair so consumers can pair them."""
        if name not in self._declared_subagents:
            raise ValueError(
                f"subagent {name!r} is not declared in Commission.subagents; declare it before invoking"
            )
        sa = self._declared_subagents[name]
        invocation_id = f"sa-{next(self._sa_seq)}"
        frame_span_id = new_span_id()
        parent_frame = self._current_parent_span()
        invocation_input = dict(input or {})
        self._state.tools_invoked[name] = self._state.tools_invoked.get(name, 0) + 1

        invoked_data: dict[str, Any] = {
            "step": self._step,
            "gen_ai.agent.name": sa.name,
            "avp.subagent.invocation_id": invocation_id,
            "avp.subagent.input": invocation_input,
        }
        if sa.description:
            invoked_data["gen_ai.agent.description"] = sa.description
        self._emit(
            SubagentInvokedEvent(
                subject=self.config.run_id,
                data=SubagentInvokedData(
                    **self._shared_span(frame_span_id, parent_frame),
                    **invoked_data,
                ),
            )
        )

        scope = SubagentScope(
            self,
            subagent=sa,
            invocation_id=invocation_id,
            frame_span_id=frame_span_id,
            parent_frame_span_id=parent_frame,
            invocation_input=invocation_input,
            step=self._step,
        )
        self._scope_stack.append(scope)
        try:
            yield scope
        finally:
            self._scope_stack.pop()
            self._close_subagent(scope)

    def _close_subagent(self, scope: SubagentScope) -> None:
        cfg = self.config
        duration_ms = max(0, int((time.monotonic() - scope._t0) * 1000))
        if scope._error is not None:
            failed_data: dict[str, Any] = {
                "step": scope._step,
                "gen_ai.agent.name": scope._subagent.name,
                "avp.subagent.invocation_id": scope._invocation_id,
                "duration_ms": duration_ms,
                "avp.subagent.error": scope._error,
            }
            if scope._error_code is not None:
                failed_data["avp.subagent.error.code"] = scope._error_code
            self._emit(
                SubagentFailedEvent(
                    subject=cfg.run_id,
                    data=SubagentFailedData(
                        **self._shared_span(scope._frame_span_id, scope._parent_frame_span_id),
                        **failed_data,
                    ),
                )
            )
            return

        returned_data: dict[str, Any] = {
            "step": scope._step,
            "gen_ai.agent.name": scope._subagent.name,
            "avp.subagent.invocation_id": scope._invocation_id,
            "duration_ms": duration_ms,
            "avp.subagent.result.text": scope._result_text or "",
            "avp.subagent.reason": scope._reason,
            "avp.subagent.usage": scope._sub_state.snapshot(),
        }
        if scope._result_structured is not None:
            returned_data["avp.subagent.result.structured"] = scope._result_structured
        self._emit(
            SubagentReturnedEvent(
                subject=cfg.run_id,
                data=SubagentReturnedData(
                    **self._shared_span(scope._frame_span_id, scope._parent_frame_span_id),
                    **returned_data,
                ),
            )
        )

    # ── Error events (rare; called explicitly by callers) ──────────────────

    def emit_error(self, *, message: str, code: ErrorCode | str = ErrorCode.unknown) -> None:
        """Emit `error_occurred` for agent-level conditions the caller
        observed (rate limit, auth failure, etc.). Distinct from tool
        failures, which use `ToolCallRecorder.fail()`."""
        if isinstance(code, str):
            code = ErrorCode(code)
        self._emit(
            ErrorOccurredEvent(
                subject=self.config.run_id,
                data=ErrorOccurredData(
                    **self._own_span(self._current_parent_span()),
                    **{"avp.error.code": code, "avp.error.message": message},
                ),
            )
        )


# ── Module-level helpers (delegate to current_tracer()) ──────────────────────
#
# These are sugar over `current_tracer().tool(...)` / `.subagent(...)` /
# `.converged()`. They let user code outside the AVPTracer instance
# (e.g., a tool-dispatch helper called from inside a wrap_anthropic-
# traced loop) reach the active tracer without taking it as an argument.


@contextmanager
def tool(*, call_id: str, name: str, input: dict[str, Any]) -> Iterator[ToolCallRecorder]:
    """Open a tool call on the active AVPTracer. Mirrors
    `AVPTracer.tool()`; raises if no tracer is active."""
    with current_tracer().tool(call_id=call_id, name=name, input=input) as t:
        yield t


@contextmanager
def subagent(*, name: str, input: dict[str, Any] | None = None) -> Iterator[SubagentScope]:
    """Open a subagent frame on the active AVPTracer. Mirrors
    `AVPTracer.subagent()`."""
    with current_tracer().subagent(name=name, input=input) as sa:
        yield sa


def converged() -> None:
    """Mark the active run as converged."""
    current_tracer().converged()


# ── Pretty-print sink (use as `on_event=print_event`) ────────────────────────


def format_event(event: BaseModel) -> str:
    """Return a one-line human-readable representation of an AVP event.

    Useful when you want a default sink for examples and debugging
    without dispatching over event types yourself. Pair with
    `on_event=print_event` for live trajectory output, or filter through
    your own logger:

        with AnthropicTracedClient(client, config=config, on_event=print_event):
            ...

    For machine-readable output, dump the event directly:
    `event.model_dump(by_alias=True, exclude_none=True)`.
    """
    cls = type(event).__name__
    data = getattr(event, "data", None)
    if data is None:
        return f"  {cls}"

    if cls == "AgentStartedEvent":
        model = getattr(data, "gen_ai_request_model", None)
        provider = getattr(data, "gen_ai_provider_name", None)
        bits = [f"agent_started run={event.subject!r}"]
        if model:
            bits.append(f"model={model}")
        if provider:
            bits.append(f"provider={provider}")
        return "  " + " ".join(bits)

    if cls == "AgentStoppedEvent":
        snap = data.avp_state
        return (
            f"  STOPPED reason={data.avp_reason} "
            f"cost=${snap.total_cost_usd:.5f} "
            f"tokens={snap.total_tokens} turns={snap.total_turns}"
        )

    if cls == "ModelTurnStartedEvent":
        return None  # quiet — paired with model_turn_ended which is louder

    if cls == "ModelTurnEndedEvent":
        return (
            f"  [turn {data.step}] "
            f"in={data.gen_ai_usage_input_tokens} "
            f"out={data.gen_ai_usage_output_tokens} "
            f"cost=${data.avp_cost_usd:.5f}"
        )

    if cls == "TextEmittedEvent":
        head = data.avp_text.replace("\n", " ")[:80]
        return f"     text: {head!r}"

    if cls == "ToolInvokedEvent":
        return f"  -> {data.gen_ai_tool_name}({list(data.gen_ai_tool_call_arguments.keys())})"

    if cls == "ToolReturnedEvent":
        head = data.avp_tool_result_text.replace("\n", " ")[:60]
        return f"  <- {data.gen_ai_tool_name}: {head!r}"

    if cls == "ToolFailedEvent":
        return f"  ✗ {data.gen_ai_tool_name}: {data.avp_tool_error}"

    if cls == "SubagentInvokedEvent":
        return (
            f"  -> subagent {data.gen_ai_agent_name!r} "
            f"(invocation_id={data.avp_subagent_invocation_id})"
        )

    if cls == "SubagentReturnedEvent":
        head = data.avp_subagent_result_text.replace("\n", " ")[:60]
        usage = data.avp_subagent_usage
        return (
            f"  <- subagent {data.gen_ai_agent_name!r} "
            f"reason={data.avp_subagent_reason} "
            f"cost=${usage.total_cost_usd:.5f} turns={usage.total_turns}"
            f" :: {head!r}"
        )

    if cls == "SubagentFailedEvent":
        return f"  ✗ subagent {data.gen_ai_agent_name!r}: {data.avp_subagent_error}"

    if cls == "ErrorOccurredEvent":
        return f"  ! {data.avp_error_code}: {data.avp_error_message}"

    if cls == "CostRecordedEvent":
        return None  # too noisy; turn-ended already shows cost

    # Fall-through: every other event (skill_loaded / mcp_* / etc.) —
    # print the type so users see something landed.
    return f"  {cls}"


def print_event(event: BaseModel) -> None:
    """Pretty-print an AVP event to stdout. Use as `on_event=print_event`
    when you want a live trajectory view without writing your own
    dispatch over event types. Returns nothing; suppresses noisy
    intermediates (model_turn_started, cost_recorded) that pair with
    louder events."""
    line = format_event(event)
    if line is not None:
        print(line)


__all__ = [
    "AVPTracer",
    "SubagentScope",
    "ToolCallRecorder",
    "TurnRecorder",
    "converged",
    "current_tracer",
    "format_event",
    "get_current_tracer",
    "print_event",
    "subagent",
    "tool",
]
