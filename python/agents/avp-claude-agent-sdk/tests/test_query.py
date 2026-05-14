"""Tests for `avp_claude_agent_sdk.query`.

The upstream `claude_agent_sdk.query` is monkeypatched to yield canned
`AssistantMessage` instances so these tests run offline (no CLI, no API key).
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from typing import Any

import pytest
from claude_agent_sdk.types import AssistantMessage, ClaudeAgentOptions, TextBlock

import avp_claude_agent_sdk.query  # noqa: F401 — ensure the submodule is in sys.modules
from avp_claude_agent_sdk import query as avp_query

# `avp_claude_agent_sdk.__init__` does `from .query import query`, which
# shadows the submodule attribute on the package — `getattr` style access
# would return the function. Go through `sys.modules` to reach the module.
_WRAPPER_MODULE = sys.modules["avp_claude_agent_sdk.query"]


def _patch_sdk_query(monkeypatch: pytest.MonkeyPatch, messages: list[Any]) -> None:
    """Replace the wrapper's upstream `_sdk_query` with a fake async generator."""

    async def fake_sdk_query(**_: Any) -> AsyncIterator[Any]:
        for m in messages:
            yield m

    monkeypatch.setattr(_WRAPPER_MODULE, "_sdk_query", fake_sdk_query)


def test_query_default_stdio_sink_writes_ndjson_trajectory(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no `sink` kwarg, query() defaults to `stdio_sink` → one NDJSON
    event per line on stdout. A single AssistantMessage in the SDK stream
    triggers one `model_turn_started` after the run prelude."""
    _patch_sdk_query(
        monkeypatch,
        [
            AssistantMessage(
                content=[TextBlock(text="pong")],
                model="claude-haiku-4-5-20251001",
            ),
        ],
    )

    async def _run() -> list[Any]:
        opts = ClaudeAgentOptions(model="claude-haiku-4-5-20251001")
        received: list[Any] = []
        async for msg in avp_query(prompt="ping", options=opts):
            received.append(msg)
        return received

    received = asyncio.run(_run())

    # Drop-in contract: the wrapper yields the SDK messages untouched.
    assert len(received) == 1
    assert isinstance(received[0], AssistantMessage)

    # Parse the NDJSON the default sink wrote to stdout.
    out_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    events = [json.loads(line) for line in out_lines]
    types = [ev["type"] for ev in events]

    # Spec §2.1 prelude order.
    assert types[0] == "avp.run_requested"
    assert types[1] == "avp.agent_described"
    assert types[2] == "avp.agent_started"
    assert "avp.model_turn_started" in types[3:]

    # Single trace and single run subject across the trajectory.
    assert len({ev["data"]["trace_id"] for ev in events}) == 1
    assert len({ev["subject"] for ev in events}) == 1

    # CloudEvents invariants. Spec §8 conformance #1: the agent is the sole
    # producer on the wire, so every event carries `avp://agent`.
    for ev in events:
        assert ev["specversion"] == "1.0"
        assert ev["source"] == "avp://agent"

    # Prelude events parent on ZERO; the turn parents on agent_started's span.
    agent_started = events[2]
    agent_span_id = agent_started["data"]["span_id"]
    ZERO = "0" * 16
    for prelude in events[:3]:
        assert prelude["data"]["parent_span_id"] == ZERO

    turn = next(ev for ev in events if ev["type"] == "avp.model_turn_started")
    assert turn["data"]["parent_span_id"] == agent_span_id
    assert turn["data"]["step"] == 1
    assert turn["data"]["gen_ai.request.stream"] is True

    # agent_started surfaces the descriptor's model + the user prompt.
    assert agent_started["data"]["gen_ai.request.model"] == "claude-haiku-4-5-20251001"
    assert agent_started["data"]["prompt"] == "ping"


def test_query_increments_step_per_assistant_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each AssistantMessage opens a new turn; step is 1-indexed and monotonic."""
    _patch_sdk_query(
        monkeypatch,
        [
            AssistantMessage(content=[TextBlock(text="one")], model="claude-haiku-4-5-20251001"),
            AssistantMessage(content=[TextBlock(text="two")], model="claude-haiku-4-5-20251001"),
            AssistantMessage(content=[TextBlock(text="three")], model="claude-haiku-4-5-20251001"),
        ],
    )

    async def _run() -> None:
        async for _ in avp_query(prompt="go"):
            pass

    asyncio.run(_run())

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    turn_steps = [ev["data"]["step"] for ev in events if ev["type"] == "avp.model_turn_started"]
    assert turn_steps == [1, 2, 3]
