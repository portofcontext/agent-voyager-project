"""Real-LLM smoke tests for avp-openai-agent.

Drive OpenAIAgentTranslator against the actual OpenAI Agents SDK, which
hits OpenAI's Responses API. These cost real money and are skipped
unless:

  - OPENAI_API_KEY is set
  - the `openai-agents` package (import `agents`) is installed

Behind the `real_llm` pytest marker; default `make test` runs skip them.

Run explicitly:
    OPENAI_API_KEY=sk-... uv run pytest python/agents/avp-openai-agent -m real_llm

Tests use the cheapest GPT-5-tier model (gpt-5-nano) and tight prompts
to keep cost per run small (well under $0.01).
"""

from __future__ import annotations

import importlib.util
import os

import pytest
from avp_openai_agent import OpenAIAgentTranslator, descriptor

from avp import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Commission,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    StopReason,
)

_HAS_SDK = importlib.util.find_spec("agents") is not None
_HAS_KEY = bool(os.environ.get("OPENAI_API_KEY"))

pytestmark = [
    pytest.mark.real_llm,
    pytest.mark.skipif(not _HAS_SDK, reason="`openai-agents` (import `agents`) not installed"),
    pytest.mark.skipif(not _HAS_KEY, reason="OPENAI_API_KEY not set"),
]


SMOKE_MODEL = "gpt-5-nano"


def _new_translator(*, prompt: str, run_id: str):
    config = Commission(
        schema_version="0.1",
        run_id=run_id,
        model=SMOKE_MODEL,
        prompt=prompt,
    )
    captured: list = []
    translator = OpenAIAgentTranslator(
        config,
        on_event=captured.append,
        descriptor=descriptor(),
    )
    return translator, captured


def test_simple_text_response_completes_successfully() -> None:
    """End-to-end: ask GPT-5-nano one trivial question. The translator MUST
    emit the full AVP-compliant lifecycle and an agent_stopped that
    mirrors what the avp-anthropic / avp-claude-agent smokes produce."""
    translator, captured = _new_translator(
        prompt="Reply with exactly the single word 'pong' and nothing else.",
        run_id="openai-agent-smoke-text",
    )
    stop = translator.run()
    types = [type(ev).__name__ for ev in captured]

    assert isinstance(stop, AgentStoppedEvent)
    assert stop.data.avp_reason == StopReason.converged, (
        f"unexpected stop reason {stop.data.avp_reason}: trajectory types={types}"
    )

    # Lifecycle invariants — same shape every AVP agent produces.
    assert "AgentStartedEvent" in types
    assert types[-1] == "AgentStoppedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert "CostRecordedEvent" in types

    started = next(ev for ev in captured if isinstance(ev, AgentStartedEvent))
    assert started.subject == "openai-agent-smoke-text"
    assert started.source == "avp://agent"

    snap = stop.data.avp_state
    # gpt-5-nano is priced in the bundled table; cost MUST be > 0.
    assert snap.total_cost_usd > 0
    assert snap.total_tokens > 0
    assert snap.total_turns >= 1


def test_cost_accounting_matches_per_turn_usage() -> None:
    """Each model_turn_ended carries the per-turn delta, and the final
    state.total_* matches the sum across all turns. The OpenAI Agents
    SDK reports per-call usage on `on_llm_end`, so deltas are direct —
    no cumulative-to-delta conversion (compare avp-claude-agent)."""
    translator, captured = _new_translator(
        prompt="Reply with 'ok'.",
        run_id="openai-agent-smoke-accounting",
    )
    stop = translator.run()
    assert isinstance(stop, AgentStoppedEvent)

    turn_events = [ev for ev in captured if isinstance(ev, ModelTurnEndedEvent)]
    assert turn_events, "translator must emit at least one model_turn_ended"

    sum_input = sum(ev.data.gen_ai_usage_input_tokens for ev in turn_events)
    sum_output = sum(ev.data.gen_ai_usage_output_tokens for ev in turn_events)
    snap = stop.data.avp_state
    assert snap.tokens_input_total == sum_input
    assert snap.tokens_output_total == sum_output
    # total_tokens covers input + output (excludes the cache slices which
    # are double-counted under tokens_input_total in AVP convention).
    assert snap.total_tokens == sum_input + sum_output


def test_cost_recorded_events_monotonic() -> None:
    """Per-turn cost_recorded snapshots MUST be monotonic across the run
    (spec/v0.1/trajectory.md §3.3). With per-call usage from the SDK,
    each turn strictly adds to the running total."""
    translator, captured = _new_translator(
        prompt="Reply with 'ok'.",
        run_id="openai-agent-smoke-monotonic",
    )
    translator.run()

    cost_events = [ev for ev in captured if isinstance(ev, CostRecordedEvent)]
    assert cost_events

    last_cost = -1.0
    last_tokens = -1
    for ce in cost_events:
        snap = ce.data.avp_state
        assert snap.total_cost_usd >= last_cost
        assert snap.total_tokens >= last_tokens
        last_cost = snap.total_cost_usd
        last_tokens = snap.total_tokens
