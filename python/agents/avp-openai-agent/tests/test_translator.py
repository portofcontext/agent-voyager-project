"""Unit tests for OpenAIAgentTranslator.

These tests drive the translator's `RunHooks` callbacks directly so we
can verify event mapping without depending on `openai-agents`'s actual
loop. They cover:

  - Cost / token math (no cum-to-delta — usage on `on_llm_end` is per-turn)
  - Tool start/end → tool_invoked/tool_returned
  - Handoff → subagent_invoked, target's on_agent_end → subagent_returned
  - Reasoning items → reasoning_emitted (text + redacted variants)
  - Final RunResult-classified stop reason
  - Error classification on SDK exception
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from avp_openai_agent import OpenAIAgentTranslator, descriptor

from avp import (
    AgentStoppedEvent,
    Commission,
    ErrorOccurredEvent,
    ModelTurnEndedEvent,
    ReasoningEmittedEvent,
    StopReason,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)

# ── Fakes ──────────────────────────────────────────────────────────────────


@dataclass
class _InputTokensDetails:
    cached_tokens: int = 0


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int
    input_tokens_details: _InputTokensDetails = None  # type: ignore[assignment]


@dataclass
class _MessageBlock:
    text: str
    type: str = "output_text"


@dataclass
class ResponseOutputMessage:
    content: list[_MessageBlock]


@dataclass
class _SummaryBlock:
    text: str


@dataclass
class ReasoningItem:
    summary: list[_SummaryBlock]


@dataclass
class _ModelResponse:
    usage: _Usage
    output: list[Any]
    model: str = "gpt-5-nano"
    status: str = "completed"


class _FakeAgent:
    """Stands in for `agents.Agent` — only attributes the translator reads."""

    def __init__(self, name: str = "avp-agent", tools: list[Any] | None = None) -> None:
        self.name = name
        self.tools = tools or []
        self.model = "gpt-5-nano"


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


def _commission(**overrides: Any) -> Commission:
    base: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "test-run",
        "model": "gpt-5-nano",
        "prompt": "say hi",
    }
    base.update(overrides)
    return Commission.model_validate(base)


def _new_translator(
    commission: Commission | None = None,
) -> tuple[OpenAIAgentTranslator, list[Any]]:
    captured: list[Any] = []
    translator = OpenAIAgentTranslator(
        commission or _commission(),
        on_event=captured.append,
        descriptor=descriptor(),
    )
    # Pre-emit the run prelude so the trajectory order matches a real run.
    translator._emit_run_prelude()
    translator._root_agent_name = "avp-agent"
    return translator, captured


# ── Tests ──────────────────────────────────────────────────────────────────


def test_basic_llm_turn_emits_lifecycle_events() -> None:
    t, captured = _new_translator()
    agent = _FakeAgent()
    response = _ModelResponse(
        usage=_Usage(
            input_tokens=20,
            output_tokens=10,
            input_tokens_details=_InputTokensDetails(cached_tokens=0),
        ),
        output=[ResponseOutputMessage(content=[_MessageBlock(text="hi back")])],
    )

    asyncio.run(t.on_agent_start(None, agent))
    asyncio.run(t.on_llm_start(None, agent, None, []))
    asyncio.run(t.on_llm_end(None, agent, response))
    asyncio.run(t.on_agent_end(None, agent, "hi back"))
    final = t._emit_agent_stopped(StopReason.converged)
    assert final is not None

    types = [type(ev).__name__ for ev in captured]
    # run_prelude + agent_started + (turn_start, text, turn_end, cost) +
    # agent_stopped
    assert "AgentStartedEvent" in types
    assert "ModelTurnStartedEvent" in types
    assert "TextEmittedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert "CostRecordedEvent" in types
    assert "AgentStoppedEvent" in types

    # Find the model_turn_ended event and verify the usage breakdown.
    turn_ended = next(ev for ev in captured if isinstance(ev, ModelTurnEndedEvent))
    assert turn_ended.data.gen_ai_usage_input_tokens == 20
    assert turn_ended.data.gen_ai_usage_output_tokens == 10
    # gpt-5-nano: input $0.05/M, output $0.40/M. 20*0.05/1M + 10*0.40/1M
    expected_cost = (20 * 0.05 + 10 * 0.40) / 1_000_000
    assert abs(turn_ended.data.avp_cost_usd - expected_cost) < 1e-9
    assert turn_ended.data.avp_cost_source == "computed"

    # Final snapshot rolls up cumulative state.
    stopped = next(ev for ev in captured if isinstance(ev, AgentStoppedEvent))
    snap = stopped.data.avp_state
    assert snap.total_turns == 1
    assert snap.total_tokens == 30
    assert snap.total_cost_usd > 0


def test_cache_read_tokens_picked_up_and_priced() -> None:
    t, captured = _new_translator()
    agent = _FakeAgent()
    response = _ModelResponse(
        usage=_Usage(
            input_tokens=100,
            output_tokens=10,
            input_tokens_details=_InputTokensDetails(cached_tokens=30),
        ),
        output=[],
    )
    asyncio.run(t.on_agent_start(None, agent))
    asyncio.run(t.on_llm_start(None, agent, None, []))
    asyncio.run(t.on_llm_end(None, agent, response))

    turn_ended = next(ev for ev in captured if isinstance(ev, ModelTurnEndedEvent))
    # gpt-5-nano: input $0.05/M, output $0.40/M, cache_read $0.005/M.
    # 70 fresh + 30 cache_read + 10 output.
    expected = (70 * 0.05 + 30 * 0.005 + 10 * 0.40) / 1_000_000
    assert abs(turn_ended.data.avp_cost_usd - expected) < 1e-9


def test_unknown_model_warns_and_reports_zero_cost() -> None:
    c = _commission(model="future-model-not-priced")
    t, captured = _new_translator(c)
    agent = _FakeAgent()
    agent.model = "future-model-not-priced"
    response = _ModelResponse(
        usage=_Usage(input_tokens=5, output_tokens=5),
        output=[],
        model="future-model-not-priced",
    )
    asyncio.run(t.on_agent_start(None, agent))
    asyncio.run(t.on_llm_start(None, agent, None, []))
    with pytest.warns(UserWarning, match="no price for model"):
        asyncio.run(t.on_llm_end(None, agent, response))

    turn_ended = next(ev for ev in captured if isinstance(ev, ModelTurnEndedEvent))
    assert turn_ended.data.avp_cost_usd == 0.0
    assert turn_ended.data.avp_cost_source == "unknown"


def test_tool_invoked_and_returned_paired() -> None:
    t, captured = _new_translator()
    agent = _FakeAgent()
    tool = _FakeTool("web_search")

    asyncio.run(t.on_agent_start(None, agent))
    asyncio.run(t.on_tool_start(None, agent, tool))
    asyncio.run(t.on_tool_end(None, agent, tool, "search results"))

    invoked = next(ev for ev in captured if isinstance(ev, ToolInvokedEvent))
    returned = next(ev for ev in captured if isinstance(ev, ToolReturnedEvent))
    assert invoked.data.gen_ai_tool_name == "web_search"
    assert returned.data.gen_ai_tool_name == "web_search"
    # Call id is preserved across the pair.
    assert invoked.data.gen_ai_tool_call_id == returned.data.gen_ai_tool_call_id
    # Hosted tool name maps to local-dispatch per AVP v0.1 vocab.
    assert invoked.data.avp_tool_dispatch_target == "local"
    assert returned.data.avp_tool_result_text == "search results"


def test_handoff_emits_subagent_invoked_and_returned() -> None:
    c = _commission(subagents=[{"id": "researcher", "ref": "x://researcher"}])
    # The Commission stores subagents as SubagentRef objects; model_validate
    # accepts the dict above. Sanity:
    assert c.subagents and c.subagents[0].id == "researcher"

    t, captured = _new_translator(c)
    root = _FakeAgent(name="avp-agent")
    target = _FakeAgent(name="researcher")

    asyncio.run(t.on_agent_start(None, root))
    asyncio.run(t.on_handoff(None, root, target))
    asyncio.run(t.on_agent_start(None, target))  # target spins up
    asyncio.run(t.on_agent_end(None, target, "research done"))

    invoked = next(ev for ev in captured if isinstance(ev, SubagentInvokedEvent))
    returned = next(ev for ev in captured if isinstance(ev, SubagentReturnedEvent))
    assert invoked.data.gen_ai_agent_name == "researcher"
    assert returned.data.gen_ai_agent_name == "researcher"
    assert invoked.data.avp_subagent_invocation_id == returned.data.avp_subagent_invocation_id
    assert returned.data.avp_subagent_result_text == "research done"


def test_reasoning_item_emits_reasoning_emitted() -> None:
    t, captured = _new_translator()
    agent = _FakeAgent()
    response = _ModelResponse(
        usage=_Usage(input_tokens=10, output_tokens=5),
        output=[
            ReasoningItem(
                summary=[_SummaryBlock(text="Plan: do X then Y")],
            ),
            ResponseOutputMessage(content=[_MessageBlock(text="result")]),
        ],
    )
    asyncio.run(t.on_agent_start(None, agent))
    asyncio.run(t.on_llm_start(None, agent, None, []))
    asyncio.run(t.on_llm_end(None, agent, response))

    reasoning = [ev for ev in captured if isinstance(ev, ReasoningEmittedEvent)]
    assert len(reasoning) == 1
    assert reasoning[0].data.avp_reasoning_text == "Plan: do X then Y"
    assert reasoning[0].data.avp_reasoning_redacted is False


def test_redacted_reasoning_when_summary_empty() -> None:
    t, captured = _new_translator()
    agent = _FakeAgent()
    response = _ModelResponse(
        usage=_Usage(input_tokens=10, output_tokens=5),
        output=[ReasoningItem(summary=[])],
    )
    asyncio.run(t.on_agent_start(None, agent))
    asyncio.run(t.on_llm_start(None, agent, None, []))
    asyncio.run(t.on_llm_end(None, agent, response))

    reasoning = [ev for ev in captured if isinstance(ev, ReasoningEmittedEvent)]
    assert len(reasoning) == 1
    assert reasoning[0].data.avp_reasoning_redacted is True
    assert reasoning[0].data.avp_reasoning_text == ""


def test_run_exception_path_emits_error_and_stops_with_error_reason() -> None:
    """Drives `.run()` through a fake Runner that raises, and verifies the
    error_occurred + agent_stopped(reason=error) shape on the wire."""

    class _BoomRunner:
        @staticmethod
        async def run(agent: Any, input_text: str, **kwargs: Any) -> Any:
            raise RuntimeError("simulated SDK failure")

    captured: list[Any] = []
    commission = _commission()
    translator = OpenAIAgentTranslator(
        commission,
        on_event=captured.append,
        descriptor=descriptor(),
        runner=_BoomRunner,
        agent_factory=lambda: _FakeAgent(),
    )
    final = translator.run()
    assert final is not None
    assert final.data.avp_reason == StopReason.error
    # error_occurred fires before agent_stopped.
    types = [type(ev).__name__ for ev in captured]
    assert types.index("ErrorOccurredEvent") < types.index("AgentStoppedEvent")
    err = next(ev for ev in captured if isinstance(ev, ErrorOccurredEvent))
    assert "simulated" in err.data.avp_error_message


def test_run_clean_path_with_fake_runner() -> None:
    """End-to-end shape of `.run()` against a Runner that calls our hooks
    in the canonical order and returns. Asserts the full event sequence."""

    captured: list[Any] = []
    commission = _commission()

    fake_agent = _FakeAgent()

    class _FakeRunResult:
        final_output = "pong"

    class _OkRunner:
        @staticmethod
        async def run(agent: Any, input_text: str, *, hooks: Any, **kwargs: Any) -> Any:
            await hooks.on_agent_start(None, agent)
            await hooks.on_llm_start(None, agent, None, [])
            response = _ModelResponse(
                usage=_Usage(
                    input_tokens=12,
                    output_tokens=3,
                    input_tokens_details=_InputTokensDetails(cached_tokens=0),
                ),
                output=[ResponseOutputMessage(content=[_MessageBlock(text="pong")])],
            )
            await hooks.on_llm_end(None, agent, response)
            await hooks.on_agent_end(None, agent, "pong")
            return _FakeRunResult()

    translator = OpenAIAgentTranslator(
        commission,
        on_event=captured.append,
        descriptor=descriptor(),
        runner=_OkRunner,
        agent_factory=lambda: fake_agent,
    )
    final = translator.run()
    assert final is not None
    assert final.data.avp_reason == StopReason.converged

    types = [type(ev).__name__ for ev in captured]
    # Run prelude → agent_started → turn pair → cost → agent_stopped.
    assert types[0] == "RunRequestedEvent"
    assert types[1] == "AgentDescribedEvent"
    assert "AgentStartedEvent" in types
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert "TextEmittedEvent" in types
    assert types[-1] == "AgentStoppedEvent"

    # Cost rolled up.
    stopped = next(ev for ev in captured if isinstance(ev, AgentStoppedEvent))
    assert stopped.data.avp_state.total_turns == 1
    assert stopped.data.avp_state.total_tokens == 15
