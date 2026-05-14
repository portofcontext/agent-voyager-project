"""Tests for the AVP-emitting query wrapper (monkeypatch path).

`_wrap_query` is driven directly with a fake async generator so tests
run offline (no CLI, no API key).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk.types import AssistantMessage, ClaudeAgentOptions, TextBlock

from avp._envelope import new_trace_id
from avp.trajectory import Event

from avp_claude_agent_sdk._patches import _wrap_query
from avp_claude_agent_sdk._runstate import RunState, reset_run, set_run


def _make_state(events: list[Event]) -> RunState:
    async def sink(event: Event) -> None:
        events.append(event)

    return RunState(trace_id=new_trace_id(), run_id="test-run", sink=sink)


async def _run(
    messages: list[Any],
    prompt: str = "ping",
    model: str = "claude-haiku-4-5-20251001",
) -> tuple[list[Event], list[Any]]:
    """Drive _wrap_query with fake messages; return (events, yielded_messages)."""
    events: list[Event] = []

    async def fake_original(**kwargs: Any) -> AsyncIterator[Any]:
        for msg in messages:
            yield msg

    state = _make_state(events)
    token = set_run(state)
    received: list[Any] = []
    try:
        opts = ClaudeAgentOptions(model=model)
        async for msg in _wrap_query(fake_original)(prompt=prompt, options=opts):
            received.append(msg)
    finally:
        reset_run(token)

    return events, received


def test_prelude_order_and_passthrough() -> None:
    msg = AssistantMessage(content=[TextBlock(text="pong")], model="claude-haiku-4-5-20251001")
    events, received = asyncio.run(_run([msg]))

    assert received == [msg]

    types = [ev.type for ev in events]
    assert types[0] == "avp.run_requested"
    assert types[1] == "avp.agent_described"
    assert types[2] == "avp.agent_started"
    assert "avp.model_turn_started" in types[3:]

    assert len({ev.data.trace_id for ev in events}) == 1
    assert len({ev.subject for ev in events}) == 1

    ZERO = "0" * 16
    for ev in events[:3]:
        assert ev.data.parent_span_id == ZERO

    agent_started = events[2]
    agent_span_id = agent_started.data.span_id
    turn = next(ev for ev in events if ev.type == "avp.model_turn_started")
    assert turn.data.parent_span_id == agent_span_id
    assert turn.data.step == 1
    assert turn.data.gen_ai_request_stream is True

    assert agent_started.data.gen_ai_request_model == "claude-haiku-4-5-20251001"
    assert agent_started.data.prompt == "ping"


def test_step_increments_per_assistant_message() -> None:
    messages = [
        AssistantMessage(content=[TextBlock(text="one")], model="claude-haiku-4-5-20251001"),
        AssistantMessage(content=[TextBlock(text="two")], model="claude-haiku-4-5-20251001"),
        AssistantMessage(content=[TextBlock(text="three")], model="claude-haiku-4-5-20251001"),
    ]
    events, _ = asyncio.run(_run(messages))
    steps = [ev.data.step for ev in events if ev.type == "avp.model_turn_started"]
    assert steps == [1, 2, 3]
