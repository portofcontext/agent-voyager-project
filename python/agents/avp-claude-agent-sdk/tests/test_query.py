"""Tests for the AVP-emitting query wrapper (monkeypatch path).

`_wrap_query` is driven directly with a fake async generator so tests
run offline (no CLI, no API key).
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk.types import AssistantMessage, ClaudeAgentOptions, TextBlock

from avp._envelope import new_trace_id
from avp.trajectory import Event

from avp_claude_agent_sdk._patches import _wrap_query
from avp_claude_agent_sdk._runstate import RunState, reset_run, set_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# Minimal stand-ins whose class names match the SDK's dispatch strings.
@dataclasses.dataclass
class ToolResultBlock:
    tool_use_id: str = "toolu_01"
    content: str = "ok"
    is_error: bool = False


@dataclasses.dataclass
class UserMessage:
    content: list[Any] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ResultMessage:
    result: str = "done"
    is_error: bool = False
    stop_reason: str = "end_turn"


def _assistant(text: str = "hi") -> AssistantMessage:
    return AssistantMessage(
        content=[TextBlock(text=text)], model="claude-haiku-4-5-20251001"
    )


def _user_tool_result() -> UserMessage:
    return UserMessage(content=[ToolResultBlock()])


# ---------------------------------------------------------------------------
# Prelude + passthrough
# ---------------------------------------------------------------------------

def test_prelude_order_and_passthrough() -> None:
    msg = _assistant("pong")
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
    assert turn.data.avp_step == 1
    assert turn.data.gen_ai_request_stream is True
    assert agent_started.data.gen_ai_request_model == "claude-haiku-4-5-20251001"
    assert agent_started.data.avp_prompt == "ping"


# ---------------------------------------------------------------------------
# Merge gate
# ---------------------------------------------------------------------------

def test_consecutive_assistant_messages_merge_into_one_turn() -> None:
    """Thinking block + text block (no UserMessage between) = one turn."""
    events, _ = asyncio.run(_run([_assistant("thinking..."), _assistant("answer")]))
    steps = [ev.data.avp_step for ev in events if ev.type == "avp.model_turn_started"]
    assert steps == [1]


def test_tool_result_boundary_opens_new_turn() -> None:
    """AssistantMessage → UserMessage(ToolResult) → AssistantMessage = two turns."""
    messages = [_assistant("calling tool"), _user_tool_result(), _assistant("done")]
    events, _ = asyncio.run(_run(messages))
    steps = [ev.data.avp_step for ev in events if ev.type == "avp.model_turn_started"]
    assert steps == [1, 2]


# ---------------------------------------------------------------------------
# ResultMessage → agent_stopped
# ---------------------------------------------------------------------------

def test_result_message_emits_agent_stopped() -> None:
    events, _ = asyncio.run(_run([_assistant("hi"), ResultMessage(result="done")]))
    types = [ev.type for ev in events]
    assert "avp.agent_stopped" in types
    stopped = next(ev for ev in events if ev.type == "avp.agent_stopped")
    assert stopped.data.avp_reason == "converged"
    assert stopped.data.avp_output == "done"


def test_result_message_is_error_emits_error_reason() -> None:
    events, _ = asyncio.run(
        _run([ResultMessage(result=None, is_error=True, stop_reason="error")])
    )
    stopped = next(ev for ev in events if ev.type == "avp.agent_stopped")
    assert stopped.data.avp_reason == "error"
