"""Translator tests for ClaudeAgentTranslator.

The SDK is fully decoupled via injection (sdk_query / sdk_options_cls /
sdk_hook_matcher_cls), so these tests run without claude_agent_sdk installed
and without an API key. They exercise:

  - Config → ClaudeAgentOptions translation (_build_sdk_options)
  - AssistantMessage / ResultMessage handling (the message-stream path)
  - PreToolUse / PostToolUse hook callbacks (the hook path)
  - Full run() lifecycle with a fake query() that yields canned messages
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from aep import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Config,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    StopReason,
    TextEmittedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
from aep_claude_agent import ClaudeAgentTranslator

# ── Lightweight fakes for the SDK surface ─────────────────────────────────────


@dataclass
class _FakeOptions:
    kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@dataclass
class _FakeHookMatcher:
    matcher: str | None
    hooks: list


class AssistantMessage:
    def __init__(
        self, content: list, usage: dict[str, Any] | None = None, model: str = "claude-sonnet-4-6"
    ):
        self.content = content
        self.usage = usage
        self.model = model


class ResultMessage:
    def __init__(self, total_cost_usd: float | None = None) -> None:
        self.total_cost_usd = total_cost_usd


class TextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


# ── Helpers ───────────────────────────────────────────────────────────────────


def _new_translator(
    cfg: Config | None = None,
    *,
    sdk_query: Any = None,
) -> tuple[ClaudeAgentTranslator, list]:
    cfg = cfg or Config(
        schema_version="0.1",
        run_id="t1",
        model="claude-sonnet-4-6",
        prompt="hello",
        allowed_tools=["bash"],
        boundary={"max_steps": 5, "max_cost_usd": 0.50},
    )
    out: list = []
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        sdk_query=sdk_query,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    return t, out


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_agent_started_emitted_with_config_metadata() -> None:
    t, out = _new_translator()
    t._emit_agent_started()
    ev = out[0]
    assert isinstance(ev, AgentStartedEvent)
    assert ev.run_id == "t1"
    assert ev.model == "claude-sonnet-4-6"
    assert ev.prompt == "hello"


def test_build_sdk_options_maps_config_fields() -> None:
    t, _ = _new_translator()
    opts = t._build_sdk_options()
    kw = opts.kwargs
    assert kw["allowed_tools"] == ["bash"]
    assert kw["max_turns"] == 5
    assert kw["max_budget_usd"] == 0.50
    assert kw["model"] == "claude-sonnet-4-6"
    assert "PreToolUse" in kw["hooks"]
    assert "PostToolUse" in kw["hooks"]


def test_assistant_message_emits_turn_started_text_ended_cost() -> None:
    t, out = _new_translator()
    msg = AssistantMessage(
        content=[TextBlock("hi there")],
        usage={"input_tokens": 100, "output_tokens": 25, "cache_read_input_tokens": 0},
        model="claude-sonnet-4-6",
    )
    t._handle_assistant_message(msg)
    types = [type(ev).__name__ for ev in out]
    assert types == [
        "ModelTurnStartedEvent",
        "TextEmittedEvent",
        "ModelTurnEndedEvent",
        "CostRecordedEvent",
    ]
    assert isinstance(out[0], ModelTurnStartedEvent)
    assert isinstance(out[1], TextEmittedEvent) and out[1].text == "hi there"
    assert isinstance(out[2], ModelTurnEndedEvent)
    assert out[2].tokens_input == 100
    assert out[2].tokens_output == 25
    assert out[2].cost_usd > 0
    assert isinstance(out[3], CostRecordedEvent)
    assert out[3].state.total_turns == 1


def test_cumulative_usage_yields_per_turn_deltas() -> None:
    """The Claude Agent SDK reports usage as cumulative-per-message — every
    AssistantMessage carries the running session total so far, NOT the delta
    for that turn alone. The translator MUST subtract the previous cumulative
    to populate AEP's per-turn ModelTurnEnded.

    Pre-fix this test would have failed: turn 2 would show the same
    cumulative cost / tokens as turn 1, double-counting.
    """
    t, out = _new_translator()

    # Turn 1: cumulative 100 input / 20 output
    t._handle_assistant_message(
        AssistantMessage(
            content=[TextBlock("first")],
            usage={"input_tokens": 100, "output_tokens": 20},
            model="claude-sonnet-4-6",
        )
    )
    # Turn 2: cumulative 250 input / 50 output  (delta is 150 / 30)
    t._handle_assistant_message(
        AssistantMessage(
            content=[TextBlock("second")],
            usage={"input_tokens": 250, "output_tokens": 50},
            model="claude-sonnet-4-6",
        )
    )

    turn_ended = [ev for ev in out if isinstance(ev, ModelTurnEndedEvent)]
    assert len(turn_ended) == 2

    # Turn 1 = its own cumulative (no prior context)
    assert turn_ended[0].tokens_input == 100
    assert turn_ended[0].tokens_output == 20

    # Turn 2 = delta, NOT cumulative. This is the load-bearing assertion.
    assert turn_ended[1].tokens_input == 150, (
        f"expected delta 150 (cumulative 250 - prior 100), got {turn_ended[1].tokens_input} — "
        f"translator likely treating cumulative usage as per-turn"
    )
    assert turn_ended[1].tokens_output == 30, (
        f"expected delta 30, got {turn_ended[1].tokens_output} — "
        f"output token cumulative-vs-delta bug"
    )

    # Cost deltas: turn 1 cost should be smaller than turn 2 cost (more tokens).
    assert turn_ended[0].cost_usd > 0
    assert turn_ended[1].cost_usd > turn_ended[0].cost_usd

    # State after both turns: cumulative totals should reconcile with the SDK.
    cost_recorded = [ev for ev in out if type(ev).__name__ == "CostRecordedEvent"]
    final_state = cost_recorded[-1].state
    assert final_state.total_turns == 2
    assert final_state.total_tokens == 300  # 100 + 20 + 150 + 30 = 300


def test_pre_and_post_tool_use_hooks_emit_invoked_and_returned() -> None:
    t, out = _new_translator()

    pre_input = {
        "tool_use_id": "c1",
        "tool_name": "bash",
        "tool_input": {"command": "ls"},
    }
    post_input = {
        "tool_use_id": "c1",
        "tool_name": "bash",
        "tool_response": "file1\nfile2",
    }
    asyncio.run(t._on_pre_tool_use_hook(pre_input, "c1", None))
    asyncio.run(t._on_post_tool_use_hook(post_input, "c1", None))

    assert isinstance(out[0], ToolInvokedEvent)
    assert out[0].call_id == "c1"
    assert out[0].tool == "bash"
    assert out[0].input == {"command": "ls"}
    assert isinstance(out[1], ToolReturnedEvent)
    assert out[1].output == "file1\nfile2"


def test_run_with_fake_query_emits_full_lifecycle() -> None:
    """End-to-end happy path: agent_started → assistant turn → result → agent_stopped."""

    async def fake_query(*, prompt: str, options: Any):
        # Mimics async generator over Message instances.
        yield AssistantMessage(
            content=[TextBlock("done")],
            usage={"input_tokens": 50, "output_tokens": 12},
        )
        yield ResultMessage(total_cost_usd=0.0042)

    t, out = _new_translator(sdk_query=fake_query)
    stop = t.run()

    assert isinstance(stop, AgentStoppedEvent)
    assert stop.reason == StopReason.converged
    # Start, turn, ResultMessage cost reconciliation, agent_stopped
    types = [type(ev).__name__ for ev in out]
    assert types[0] == "AgentStartedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert types.count("CostRecordedEvent") >= 1
    assert types[-1] == "AgentStoppedEvent"
    # SDK-reported cost wins
    assert abs(stop.total_cost_usd - 0.0042) < 1e-9


def test_run_propagates_sdk_error_to_agent_stopped_error() -> None:
    """A query() that raises is wrapped: error_occurred + agent_stopped reason='error'."""

    async def bad_query(*, prompt: str, options: Any):
        if False:
            yield None  # make this an async generator
        raise RuntimeError("boom")

    t, out = _new_translator(sdk_query=bad_query)
    stop = t.run()
    assert stop.reason == StopReason.error
    types = [type(ev).__name__ for ev in out]
    assert "ErrorOccurredEvent" in types
    assert types[-1] == "AgentStoppedEvent"
