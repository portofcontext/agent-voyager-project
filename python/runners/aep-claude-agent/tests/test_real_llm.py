"""Real-LLM smoke tests for aep-claude-agent.

These tests drive ClaudeAgentTranslator against the actual Claude Agent SDK,
which spawns the Claude CLI and hits Anthropic's API. They cost real money
and are skipped unless:

  - ANTHROPIC_API_KEY is set
  - the Claude CLI (`claude`) is installed and on PATH
  - the `claude_agent_sdk` Python package imports cleanly

They sit behind the `real_llm` pytest marker so default test runs skip them.

Run explicitly:
    ANTHROPIC_API_KEY=sk-... uv run pytest python/runners/aep-claude-agent -m real_llm

Each test uses a tight boundary to keep cost per run small. The tests assert
the SAME wire shape as `aep-anthropic`'s real-LLM smoke — that's the point of
parity: a downstream supervisor MUST be able to consume both runners' output
identically.
"""

from __future__ import annotations

import importlib.util
import os
import shutil

import pytest

from aep import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Config,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    StopReason,
    TextEmittedEvent,
)
from aep_claude_agent.translator import ClaudeAgentTranslator

_HAS_SDK = importlib.util.find_spec("claude_agent_sdk") is not None
_HAS_CLI = shutil.which("claude") is not None
_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))

pytestmark = [
    pytest.mark.real_llm,
    pytest.mark.skipif(not _HAS_SDK, reason="claude_agent_sdk not installed"),
    pytest.mark.skipif(not _HAS_CLI, reason="`claude` CLI not on PATH"),
    pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set"),
]


SMOKE_MODEL = "claude-haiku-4-5-20251001"
TIGHT_BOUNDARY = {"max_steps": 2, "max_cost_usd": 0.10, "max_tokens": 4000}


def _new_translator(*, prompt: str, run_id: str):
    config = Config(
        schema_version="0.1",
        run_id=run_id,
        model=SMOKE_MODEL,
        prompt=prompt,
        boundary=TIGHT_BOUNDARY,
    )
    captured: list = []
    translator = ClaudeAgentTranslator(config, on_event=captured.append)
    return translator, captured


def test_simple_text_response_completes_successfully() -> None:
    """End-to-end: ask Claude one trivial question via the Agent SDK. The
    translator MUST emit the full AEP-compliant lifecycle and an
    agent_stopped that mirrors what the driver-pattern runner produces."""
    translator, captured = _new_translator(
        prompt="Reply with exactly the single word 'pong' and nothing else.",
        run_id="claude-agent-smoke-text",
    )
    stop = translator.run()
    types = [type(ev).__name__ for ev in captured]

    assert isinstance(stop, AgentStoppedEvent)
    assert stop.data.aep_reason in (StopReason.converged, StopReason.turn_limit), (
        f"unexpected stop reason {stop.data.aep_reason}: trajectory types={types}"
    )

    # Lifecycle invariants — same shape the driver-pattern runner produces.
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert "CostRecordedEvent" in types

    # Sanity on what's in the started + stopped envelopes.
    started = next(ev for ev in captured if isinstance(ev, AgentStartedEvent))
    assert started.subject == "claude-agent-smoke-text"
    assert started.source == "aep://runner"

    snap = stop.data.aep_state
    assert snap.total_cost_usd > 0
    assert snap.total_tokens > 0
    assert snap.total_turns >= 1


def test_token_and_cost_accounting_monotonic_across_turns() -> None:
    """Translators over cumulative-usage SDKs MUST derive per-turn deltas
    correctly so consecutive cost_recorded events report monotonic totals
    (SPEC.md §9.4)."""
    translator, captured = _new_translator(
        prompt="Reply with 'ok'.",
        run_id="claude-agent-smoke-monotonic",
    )
    translator.run()

    cost_events = [ev for ev in captured if isinstance(ev, CostRecordedEvent)]
    assert cost_events, "translator must emit at least one cost_recorded"

    last_cost = -1.0
    last_tokens = -1
    for ce in cost_events:
        snap = ce.data.aep_state
        assert snap.total_cost_usd >= last_cost
        assert snap.total_tokens >= last_tokens
        last_cost = snap.total_cost_usd
        last_tokens = snap.total_tokens


def test_text_emitted_carries_assistant_content() -> None:
    """When Claude produces text, the translator MUST emit text_emitted
    with the verbatim content under data["aep.text"] (SPEC §11)."""
    translator, captured = _new_translator(
        prompt="Reply with exactly the word 'hello' and nothing else.",
        run_id="claude-agent-smoke-text-content",
    )
    translator.run()

    text_events = [ev for ev in captured if isinstance(ev, TextEmittedEvent)]
    # Claude SHOULD produce at least one text block on a converged trivial run.
    if text_events:
        joined = " ".join(ev.data.aep_text for ev in text_events).lower()
        assert "hello" in joined, f"expected 'hello' in emitted text, got {joined!r}"


def test_model_turn_ended_carries_otel_genai_usage() -> None:
    """Per the OTel GenAI conventions, model_turn_ended.data MUST surface
    `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`. If the SDK
    reports cache reads, those MUST be additive to input_tokens (§9.4)."""
    translator, captured = _new_translator(
        prompt="Reply with 'ok'.",
        run_id="claude-agent-smoke-usage",
    )
    translator.run()

    turn_ends = [ev for ev in captured if isinstance(ev, ModelTurnEndedEvent)]
    assert turn_ends, "expected at least one model_turn_ended"
    for te in turn_ends:
        assert te.data.gen_ai_usage_input_tokens >= 0
        assert te.data.gen_ai_usage_output_tokens >= 0
        cache_read = te.data.gen_ai_usage_cache_read_input_tokens
        if cache_read is not None:
            assert te.data.gen_ai_usage_input_tokens >= cache_read, (
                f"AEP §9.4: gen_ai.usage.input_tokens ({te.data.gen_ai_usage_input_tokens}) "
                f"MUST include cache reads ({cache_read})"
            )
