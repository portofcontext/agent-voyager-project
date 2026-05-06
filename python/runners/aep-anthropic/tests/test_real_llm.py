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
    ModelTurnStartedEvent,
    StopReason,
    Subagent,
    SubagentFailedEvent,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
)
from aep.runner import AEPRunner
from aep.runner.mock import ScriptedSupervisor, ScriptedTools
from aep_anthropic import AnthropicModelDriver, build_anthropic_tools
from aep_anthropic.subagent import AnthropicSubagentDriver

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


def test_subagent_delegation_round_trip_against_real_model() -> None:
    """End-to-end: parent agent calls a declared subagent, the subagent runs
    its own sub-loop on the real Anthropic API, and the wire shape assembles
    correctly: subagent_invoked / subagent_returned pair share a frame
    span_id, nested model_turn events chain through that frame, and the
    parent run converges.

    Two real model calls: one for the parent's tool-use turn, one for the
    subagent's reply. Parent's converging turn may add a third. Tight
    boundary keeps cost per run under ~$0.002 on Haiku.
    """
    config = Config(
        schema_version="0.1",
        run_id="smoke-subagent",
        model=SMOKE_MODEL,
        # Orchestrator framing: parent has NO direct capability and the
        # subagent is the only listed tool. Haiku otherwise tends to just
        # answer summarization questions inline. The phrasing is deliberately
        # binding because flaky tool-use makes for a flaky test of the wire,
        # which is what we're actually trying to pin.
        system_prompt=(
            "You are an orchestrator with no independent abilities. The ONLY "
            "way you can produce any output is by calling the `summarizer` "
            "tool exactly once with the user's sentence. After it returns, "
            "echo its output verbatim and stop. Do not answer the user "
            "directly under any circumstances."
        ),
        prompt=(
            "Call the summarizer tool now with this sentence as the `prompt` "
            "argument: 'AEP is a wire format between supervisor and runner.'"
        ),
        subagents=[
            Subagent(
                name="summarizer",
                description="Summarizes a passage as one short bullet point.",
                system_prompt=(
                    "You are a precise summarizer. Output exactly one bullet, "
                    "≤ 10 words. Output nothing else."
                ),
                model=SMOKE_MODEL,
                boundary={"max_steps": 2},
            )
        ],
        boundary={"max_steps": 4, "max_cost_usd": 0.10},
        allowed_tools=["summarizer"],
    )
    # When wiring AEPRunner directly (no CLI), the caller is responsible for
    # exposing Config.tools and Config.subagents on the model's surface —
    # `build_anthropic_tools(config)` does the translation, including the
    # MCP `inputSchema` → Anthropic `input_schema` rename and the
    # allowed_tools filter.
    runner = AEPRunner(
        config=config,
        model=AnthropicModelDriver(
            model=SMOKE_MODEL,
            max_tokens=200,
            tools_param=build_anthropic_tools(config),
        ),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor([]),
        subagent_driver=AnthropicSubagentDriver(default_model=SMOKE_MODEL, max_tokens=200),
    )
    stop = runner.run()
    traj = runner.trajectory

    # No driver-level failures (e.g. unsupported_in_v0_1 from the prototype's
    # not-yet-dispatched fields). If this fails, the model invoked the
    # subagent with input the driver couldn't handle, not an API issue.
    failures = [ev for ev in traj if isinstance(ev, SubagentFailedEvent)]
    assert not failures, f"subagent_failed: {[f.data.aep_subagent_error for f in failures]}"

    invoked = [ev for ev in traj if isinstance(ev, SubagentInvokedEvent)]
    returned = [ev for ev in traj if isinstance(ev, SubagentReturnedEvent)]
    assert invoked, (
        "parent never called the subagent — model declined to delegate. "
        f"trajectory types: {_types(traj)}"
    )
    assert len(invoked) == len(returned), "every subagent_invoked needs a returned"

    # Frame span MUST pair across invoked/returned — this is how consumers
    # reconstruct the subagent's nested span tree.
    inv = invoked[0]
    ret = returned[0]
    assert inv.data.span_id == ret.data.span_id, "frame span_id MUST match across pair"
    assert inv.data.gen_ai_agent_name == "summarizer"
    assert inv.data.gen_ai_operation_name == "invoke_agent"

    # The subagent's internal turns chain through its frame span. If
    # AnthropicSubagentDriver doesn't pass parent_frame_span_id correctly,
    # the model_turn events parent under the wrong span and this fails.
    frame_id = inv.data.span_id
    nested_starts = [
        ev
        for ev in traj
        if isinstance(ev, ModelTurnStartedEvent) and ev.data.parent_span_id == frame_id
    ]
    assert nested_starts, "no model_turn descended from the subagent's frame — span linkage broken"

    # The subagent reported real spend.
    sa_usage = ret.data.aep_subagent_usage
    assert sa_usage.total_cost_usd > 0, "subagent didn't accrue cost — driver swallowed it"
    assert sa_usage.total_tokens > 0
    assert sa_usage.total_turns >= 1
    assert ret.data.aep_subagent_reason in (
        StopReason.converged,
        StopReason.turn_limit,
        StopReason.budget_exhausted,
    )

    # Parent's cumulative state includes the subagent's spend.
    parent_snap = stop.data.aep_state
    assert parent_snap.total_cost_usd >= sa_usage.total_cost_usd, (
        "subagent usage MUST roll up into parent's RunStateSnapshot — "
        "parent's boundary check would otherwise be blind to subagent cost"
    )
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
