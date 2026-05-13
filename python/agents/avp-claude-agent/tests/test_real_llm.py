"""Real-LLM smoke tests for avp-claude-agent.

These tests drive ClaudeAgentTranslator against the actual Claude Agent SDK,
which spawns the Claude CLI and hits Anthropic's API. They cost real money
and are skipped unless:

  - ANTHROPIC_API_KEY is set
  - the Claude CLI (`claude`) is installed and on PATH
  - the `claude_agent_sdk` Python package imports cleanly

They sit behind the `real_llm` pytest marker so default test runs skip them.

Run explicitly:
    ANTHROPIC_API_KEY=sk-... uv run pytest python/agents/avp-claude-agent -m real_llm

Each test uses a tight, short prompt to keep cost per run small. The tests
assert the SAME wire shape as `avp-anthropic`'s real-LLM smoke (which
runs `AVPAgent` + the driver in-process): that's the point of parity, a
downstream supervisor MUST be able to consume both agents' output
identically.
"""

from __future__ import annotations

import importlib.util
import os
import shutil

import pytest

from avp import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Commission,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    StopReason,
    TextEmittedEvent,
)
from avp_claude_agent.translator import ClaudeAgentTranslator

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


def _new_translator(*, prompt: str, run_id: str):
    config = Commission(
        schema_version="0.1",
        run_id=run_id,
        model=SMOKE_MODEL,
        prompt=prompt,
    )
    captured: list = []
    translator = ClaudeAgentTranslator(config, on_event=captured.append)
    return translator, captured


def test_simple_text_response_completes_successfully() -> None:
    """End-to-end: ask Claude one trivial question via the Agent SDK. The
    translator MUST emit the full AVP-compliant lifecycle and an
    agent_stopped that mirrors what the driver-pattern agent produces."""
    translator, captured = _new_translator(
        prompt="Reply with exactly the single word 'pong' and nothing else.",
        run_id="claude-agent-smoke-text",
    )
    stop = translator.run()
    types = [type(ev).__name__ for ev in captured]

    assert isinstance(stop, AgentStoppedEvent)
    assert stop.data.avp_reason == StopReason.converged, (
        f"unexpected stop reason {stop.data.avp_reason}: trajectory types={types}"
    )

    # Lifecycle invariants — same shape the driver-pattern agent produces.
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert "CostRecordedEvent" in types

    # Sanity on what's in the started + stopped envelopes.
    started = next(ev for ev in captured if isinstance(ev, AgentStartedEvent))
    assert started.subject == "claude-agent-smoke-text"
    assert started.source == "avp://agent"

    snap = stop.data.avp_state
    assert snap.total_cost_usd > 0
    assert snap.total_tokens > 0
    assert snap.total_turns >= 1


def test_token_and_cost_accounting_monotonic_across_turns() -> None:
    """Translators over cumulative-usage SDKs MUST derive per-turn deltas
    correctly so consecutive cost_recorded events report monotonic totals
    (`spec/trajectory/v0.1/trajectory.md` §3.3)."""
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
        snap = ce.data.avp_state
        assert snap.total_cost_usd >= last_cost
        assert snap.total_tokens >= last_tokens
        last_cost = snap.total_cost_usd
        last_tokens = snap.total_tokens


def test_text_emitted_carries_assistant_content() -> None:
    """When Claude produces text, the translator MUST emit text_emitted
    with the verbatim content under data["avp.text"] (spec/trajectory/v0.1/trajectory.md §7)."""
    translator, captured = _new_translator(
        prompt="Reply with exactly the word 'hello' and nothing else.",
        run_id="claude-agent-smoke-text-content",
    )
    translator.run()

    text_events = [ev for ev in captured if isinstance(ev, TextEmittedEvent)]
    # Claude SHOULD produce at least one text block on a converged trivial run.
    if text_events:
        joined = " ".join(ev.data.avp_text for ev in text_events).lower()
        assert "hello" in joined, f"expected 'hello' in emitted text, got {joined!r}"


def test_traced_client_drop_in_round_trip_against_real_sdk() -> None:
    """End-to-end: an existing-shape Claude Agent SDK loop using
    `TracedClaudeSDKClient` instead of `ClaudeSDKClient` directly. The
    user keeps their `async for message in client.receive_response()`
    pattern; AVP events flow on the wire automatically.

    Proves the drop-in story works against the actual SDK:
      - agent_started / agent_stopped emitted on context manager open/close
      - At least one ModelTurnEnded with non-zero usage (real model call)
      - The user's iterator received SDK Message instances unmodified
      - Run accrues real cost and converges
    """
    import asyncio

    from avp_claude_agent import TracedClaudeSDKClient

    config = Commission(
        schema_version="0.1",
        run_id="traced-client-smoke",
        model=SMOKE_MODEL,
        prompt="Reply with exactly the single word 'pong'.",
    )
    captured: list = []
    received_messages: list = []

    async def _run() -> None:
        async with TracedClaudeSDKClient(commission=config, on_event=captured.append) as client:
            await client.connect(config.prompt)
            async for message in client.receive_response():
                received_messages.append(message)
            client.converged()

    asyncio.run(_run())

    types = [type(ev).__name__ for ev in captured]
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types

    # Real call → at least one turn with non-zero usage.
    turn_ends = [ev for ev in captured if isinstance(ev, ModelTurnEndedEvent)]
    assert turn_ends
    total_in = sum(ev.data.gen_ai_usage_input_tokens for ev in turn_ends)
    total_out = sum(ev.data.gen_ai_usage_output_tokens for ev in turn_ends)
    assert total_in > 0 and total_out > 0, "real SDK call must report token usage"

    # The user's iterator saw SDK Message instances unmodified.
    assert received_messages, "user's async-for body MUST receive at least one message"
    # The SDK class names that end up in `received_messages` are SDK-defined
    # (AssistantMessage, ResultMessage, SystemMessage, etc.). We don't pin
    # the exact set — just assert SOMETHING came through with content.
    has_content = any(getattr(m, "content", None) for m in received_messages)
    assert has_content, "expected at least one message with .content"

    stopped = next(ev for ev in captured if isinstance(ev, AgentStoppedEvent))
    assert stopped.data.avp_reason == StopReason.converged
    assert stopped.data.avp_state.total_cost_usd > 0


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
                f"AVP §9.4: gen_ai.usage.input_tokens ({te.data.gen_ai_usage_input_tokens}) "
                f"MUST include cache reads ({cache_read})"
            )
