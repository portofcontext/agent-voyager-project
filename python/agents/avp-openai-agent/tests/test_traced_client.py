"""TracedOpenAIRunner / traced_openai_runner shape tests."""

from __future__ import annotations

from typing import Any

import pytest
from avp_openai_agent import TracedOpenAIRunner, traced_openai_runner

from avp import AVPTracer, Commission


def _commission() -> Commission:
    return Commission.model_validate(
        {
            "schema_version": "0.1",
            "run_id": "test-run",
            "model": "gpt-5-nano",
            "prompt": "hi",
        }
    )


class _OkRunner:
    """Calls every hook once so the wire shape is exercised end-to-end."""

    @staticmethod
    async def run(agent: Any, input_text: str, *, hooks: Any, **kwargs: Any) -> str:
        await hooks.on_agent_start(None, agent)
        await hooks.on_agent_end(None, agent, "result")
        return "result"


class _FakeAgent:
    def __init__(self) -> None:
        self.name = "avp-agent"
        self.tools: list[Any] = []
        self.model = "gpt-5-nano"


def test_standalone_emits_prelude_then_lifecycle_then_stop() -> None:
    captured: list[Any] = []
    with TracedOpenAIRunner(
        commission=_commission(),
        on_event=captured.append,
        runner=_OkRunner,
    ) as t:
        t.run_sync(_FakeAgent(), "hi")

    types = [type(ev).__name__ for ev in captured]
    # Prelude bracketed by the with-block; agent_started fires from
    # on_agent_start.
    assert types[0] == "RunRequestedEvent"
    assert types[1] == "AgentDescribedEvent"
    assert "AgentStartedEvent" in types
    assert types[-1] == "AgentStoppedEvent"


def test_reuse_raises() -> None:
    t = TracedOpenAIRunner(
        commission=_commission(),
        on_event=lambda _e: None,
        runner=_OkRunner,
    )
    with t:
        pass
    with pytest.raises(RuntimeError, match="cannot be reused"):
        with t:
            pass


def test_factory_requires_active_tracer() -> None:
    with pytest.raises(RuntimeError, match="requires an active AVPTracer"):
        traced_openai_runner(runner=_OkRunner)


def test_factory_delegated_mode_inherits_trace_id() -> None:
    captured: list[Any] = []
    commission = _commission()
    with AVPTracer(commission, on_event=captured.append) as outer:
        with traced_openai_runner(runner=_OkRunner) as t:
            # In delegated mode the translator borrows the parent's trace_id.
            assert t._translator._trace_id == outer.trace_id
            assert t._translator._agent_span_id == outer.agent_span_id
            assert t._translator._suppress_lifecycle is True
            t.run_sync(_FakeAgent(), "hi")
    # Outer tracer owns the lifecycle bookends. The inner runner suppresses
    # its own agent_started / agent_stopped to avoid duplicates.
    types = [type(ev).__name__ for ev in captured]
    assert types.count("AgentStartedEvent") == 1
    assert types.count("AgentStoppedEvent") == 1
