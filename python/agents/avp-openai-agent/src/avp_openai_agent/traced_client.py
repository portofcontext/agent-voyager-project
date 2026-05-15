"""TracedOpenAIRunner — drop-in instrumentation for `agents.Runner`.

Wraps the OpenAI Agents SDK's one-shot `Runner.run` / `Runner.run_sync`
calls so an existing user flow:

    from agents import Agent, Runner
    agent = Agent(name="x", instructions="...")
    result = Runner.run_sync(agent, "hello")

becomes:

    from avp_openai_agent import TracedOpenAIRunner
    with TracedOpenAIRunner(commission=commission, on_event=publish) as t:
        result = t.run_sync(agent, "hello")

with AVP events on the wire — `run_requested`, `agent_described`,
`agent_started`, `model_turn_*`, `tool_invoked` / `tool_returned`,
`subagent_invoked` / `subagent_returned`, `agent_stopped` — emitted as
the SDK hits its lifecycle hooks.

OpenAI's SDK ownership shape differs from Claude's: `Runner.run` is a
one-shot call, not a long-lived client object. So this wrapper sits at
the Runner-call level rather than wrapping a persistent client, and the
context manager mainly exists to bracket the run with the `run_requested`
/ `agent_described` prelude (on enter) and `agent_stopped` (on exit).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from avp import AVPTracer, Commission, StopReason, get_current_tracer
from avp_openai_agent.descriptor import descriptor as build_descriptor
from avp_openai_agent.translator import OpenAIAgentTranslator, _AVPRunHooks


class TracedOpenAIRunner:
    """Sync context manager that runs `agents.Runner` with AVP wire events.

    Construct with the AVP `Commission` and an `on_event` callback. On
    enter we emit `run_requested` + `agent_described` (the run prelude).
    Inside the block, call `.run_sync(agent, input)` to execute the
    underlying `agents.Runner.run` with our `RunHooks` adapter wired in.
    On exit we emit `agent_stopped` with the accumulated state.

    `runner` injects a fake runner (object with async `run(agent, input,
    *, hooks, **kwargs)`) for tests that don't have `openai-agents`
    installed.
    """

    def __init__(
        self,
        *,
        commission: Commission,
        on_event: Callable[[BaseModel], None],
        runner: Any | None = None,
        parent_tracer: AVPTracer | None = None,
        emit_descriptor: bool = True,
    ) -> None:
        """Standalone mode (default): pass `commission` and `on_event`; the
        translator emits its own agent_started / agent_stopped bookends.

        Delegated mode: pass `parent_tracer` (typically via the
        `traced_openai_runner()` factory inside `with AVPTracer(...)`).
        The translator borrows the parent's trace_id / agent_span_id,
        emits via the parent's on_event sink, and suppresses its own
        lifecycle bookends so the wire stays one coherent tree.
        """
        self.commission = commission
        self._on_event = on_event
        self._parent_tracer = parent_tracer
        self._translator = OpenAIAgentTranslator(
            commission,
            on_event,
            descriptor=build_descriptor() if emit_descriptor else None,
            runner=runner,
            parent_trace_id=parent_tracer.trace_id if parent_tracer else None,
            parent_agent_span_id=parent_tracer.agent_span_id if parent_tracer else None,
            suppress_lifecycle=parent_tracer is not None,
            parent_tracer=parent_tracer,
        )
        self._stop_reason: StopReason | None = None
        self._entered = False

    def __enter__(self) -> TracedOpenAIRunner:
        if self._entered:
            raise RuntimeError("TracedOpenAIRunner cannot be reused; create a new instance per run")
        self._entered = True
        self._translator._emit_run_prelude()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        reason = self._stop_reason
        if reason is None and exc_type is not None:
            reason = StopReason.error
        if reason is None:
            reason = StopReason.converged
        self._translator._emit_agent_stopped(reason)

    # ── Forwarded SDK surface ──────────────────────────────────────────────

    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any:
        """Synchronous wrapper around `Runner.run`.

        Mirrors `agents.Runner.run_sync(agent, input, **kwargs)`. Any
        kwargs (e.g. `max_turns`, `run_config`) pass through to the
        underlying call.
        """
        return asyncio.run(self.run(agent, input, **kwargs))

    async def run(self, agent: Any, input: str, **kwargs: Any) -> Any:
        """Async wrapper around `Runner.run`. Returns the SDK's RunResult."""
        if not self._entered:
            raise RuntimeError(
                "TracedOpenAIRunner must be used as a `with` block before "
                "calling run() / run_sync()"
            )
        runner = self._translator._runner
        if runner is None:
            from agents import Runner  # type: ignore[import-not-found]

            runner = Runner
            self._translator._runner = runner
        self._translator._root_agent_name = getattr(agent, "name", None) or "agent"
        hooks = _AVPRunHooks(self._translator)
        try:
            result = await runner.run(agent, input, hooks=hooks, **kwargs)
            self.converged()
            return result
        except Exception:
            self._stop_reason = StopReason.error
            raise

    def converged(self) -> None:
        """Mark this run as converged. Honored on `__exit__` when no
        other terminal condition (exception) has fired."""
        if self._stop_reason is None:
            self._stop_reason = StopReason.converged


def traced_openai_runner(
    *,
    runner: Any | None = None,
) -> TracedOpenAIRunner:
    """Factory for the "wrap inside an active tracer" pattern.

    Requires an enclosing `with AVPTracer(commission, on_event=...)`
    block; the factory pulls Commission + on_event from that tracer and
    constructs a `TracedOpenAIRunner` in delegated mode.

    Usage:

        with AVPTracer(commission, on_event=publish):
            with traced_openai_runner() as t:
                result = t.run_sync(agent, "hello")

    Compare to the self-contained form:

        with TracedOpenAIRunner(commission=commission, on_event=publish) as t:
            result = t.run_sync(agent, "hello")

    Both produce the same wire shape. Use this factory when you have
    other AVP-instrumented work flowing through the same tracer.
    """
    tracer = get_current_tracer()
    if tracer is None:
        raise RuntimeError(
            "traced_openai_runner() requires an active AVPTracer. Wrap your "
            "code in `with AVPTracer(commission, on_event=...):` before "
            "calling, OR use TracedOpenAIRunner(commission=..., "
            "on_event=...) directly for the self-contained form."
        )
    return TracedOpenAIRunner(
        commission=tracer.commission,
        on_event=tracer.on_event,
        runner=runner,
        parent_tracer=tracer,
    )


__all__ = ["TracedOpenAIRunner", "traced_openai_runner"]
