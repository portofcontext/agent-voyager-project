"""Real-LLM smoke tests for aep-anthropic.

These tests hit the live Anthropic API and cost real money. They are skipped
unless ANTHROPIC_API_KEY is set in the environment, and they're behind the
'real_llm' pytest marker so they don't run on every test invocation.

Run explicitly:
    ANTHROPIC_API_KEY=sk-... pytest -v -m real_llm

Skip in normal runs (default behavior in CI for forked PRs):
    pytest -m "not real_llm"

Each test uses claude-haiku-4-5-20251001 (the cheapest current Claude model)
and tight boundaries to keep cost per run under ~$0.001.
"""

from __future__ import annotations

import os

import pytest

from aep import (
    AgentStoppedEvent,
    Config,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    StopReason,
)
from aep.runner import AEPRunner
from aep.runner.mock import ScriptedSupervisor, ScriptedTools
from aep_anthropic import AnthropicModelDriver

pytestmark = [
    pytest.mark.real_llm,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set; skipping real-LLM smoke tests",
    ),
]


SMOKE_MODEL = "claude-haiku-4-5-20251001"  # cheapest current Claude
TIGHT_BOUNDARY = {"max_steps": 3, "max_cost_usd": 0.10, "max_tokens": 4000}


def _new_runner(*, prompt: str, run_id: str) -> AEPRunner:
    config = Config(
        schema_version="0.1",
        run_id=run_id,
        model=SMOKE_MODEL,
        prompt=prompt,
        boundary=TIGHT_BOUNDARY,
    )
    return AEPRunner(
        config=config,
        model=AnthropicModelDriver(model=SMOKE_MODEL, max_tokens=200),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor([]),
    )


def _types(traj) -> list[str]:
    return [type(ev).__name__ for ev in traj]


def test_simple_text_response_completes_successfully() -> None:
    """End-to-end: ask Claude one trivial question. Trajectory must contain the full
    AEP-compliant lifecycle and agent_stopped reason='converged'."""
    runner = _new_runner(
        prompt="Reply with exactly the single word 'pong' and nothing else.",
        run_id="smoke-simple-text",
    )
    stop = runner.run()
    types = _types(runner.trajectory)

    assert isinstance(stop, AgentStoppedEvent)
    assert stop.data.aep_reason == StopReason.converged, (
        f"expected converged, got {stop.data.aep_reason}: trajectory types={types}"
    )

    # Lifecycle invariants
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert "CostRecordedEvent" in types
    assert "TextEmittedEvent" in types  # Claude will produce text on a converged run

    # Real call → non-zero cost and tokens
    snap = stop.data.aep_state
    assert snap.total_cost_usd > 0
    assert snap.total_tokens > 0
    assert snap.total_turns >= 1


def test_token_and_cost_accounting_monotonic_across_turns() -> None:
    """RunStateSnapshot accounting MUST be monotonic; consecutive cost_recorded
    events MUST never report decreasing totals."""
    runner = _new_runner(
        prompt="Reply with 'one'. Then if asked again, reply with 'two'. Just answer naturally.",
        run_id="smoke-monotonic",
    )
    runner.run()

    cost_events = [ev for ev in runner.trajectory if isinstance(ev, CostRecordedEvent)]
    assert len(cost_events) >= 1

    last_cost = -1.0
    last_tokens = -1
    for ce in cost_events:
        snap = ce.data.aep_state
        assert snap.total_cost_usd >= last_cost
        assert snap.total_tokens >= last_tokens
        last_cost = snap.total_cost_usd
        last_tokens = snap.total_tokens


def test_boundary_max_steps_enforced_against_real_model() -> None:
    """Set max_steps=1; Claude should respond once and the runner should stop with reason='turn_limit'.
    Proves the strict-greater step check works against a real model that doesn't naturally converge."""
    config = Config(
        schema_version="0.1",
        run_id="smoke-max-steps",
        model=SMOKE_MODEL,
        prompt="Pick three numbers between 1 and 10 then call out which is largest. Then ask me to pick another set.",
        boundary={"max_steps": 1, "max_cost_usd": 0.10},
    )
    runner = AEPRunner(
        config=config,
        model=AnthropicModelDriver(model=SMOKE_MODEL, max_tokens=200),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor([]),
    )
    stop = runner.run()

    # Either Claude converged in 1 turn (reason=converged with total_turns=1)
    # or hit the max_steps boundary (reason=turn_limit with total_turns=1).
    # Both prove the runner respected the boundary; total_turns MUST equal exactly 1.
    snap = stop.data.aep_state
    assert snap.total_turns == 1, f"max_steps=1 must yield exactly 1 turn, got {snap.total_turns}"
    assert stop.data.aep_reason in (StopReason.converged, StopReason.turn_limit)


def test_token_input_includes_cache_reads_when_present() -> None:
    """If the API reports cache_read_input_tokens, the AEP wire's
    gen_ai.usage.input_tokens MUST include them (per SPEC.md §9.4). On a
    single short call we likely get 0 cache reads; this test just asserts
    the math: input_tokens >= cache_read.input_tokens when present."""
    runner = _new_runner(
        prompt="Reply with 'ok'.",
        run_id="smoke-cache-tokens",
    )
    runner.run()

    turn_ends = [ev for ev in runner.trajectory if isinstance(ev, ModelTurnEndedEvent)]
    assert turn_ends
    for te in turn_ends:
        cache_read = te.data.gen_ai_usage_cache_read_input_tokens
        if cache_read is not None:
            input_total = te.data.gen_ai_usage_input_tokens
            assert input_total >= cache_read, (
                f"AEP §9.4: gen_ai.usage.input_tokens ({input_total}) MUST include "
                f"cache reads ({cache_read}); driver may be subtracting them"
            )
