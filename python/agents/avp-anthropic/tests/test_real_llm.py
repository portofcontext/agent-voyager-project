"""Real-LLM smoke tests for avp-anthropic.

These tests hit the live Anthropic API and cost real money. They are skipped
unless ANTHROPIC_API_KEY is set in the environment, and they're behind the
'real_llm' pytest marker so they don't run on every test invocation.

Run explicitly:
    ANTHROPIC_API_KEY=sk-... pytest -v -m real_llm

Skip in normal runs (default behavior in CI for forked PRs):
    pytest -m "not real_llm"

Each test uses claude-haiku-4-5-20251001 (the cheapest current Claude model)
and tight prompts to keep cost per run under ~$0.001. v0.1 has no spec
mechanism for caps (boundaries were dropped); these tests rely on the
model converging on its own from short prompts.
"""

from __future__ import annotations

import os

import pytest

from avp import (
    AgentStoppedEvent,
    Commission,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    StopReason,
    Subagent,
    SubagentFailedEvent,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
)
from avp.agent import AVPAgent
from avp.agent.mock import ScriptedSupervisor, ScriptedTools
from avp_anthropic import AnthropicModelDriver, build_anthropic_tools
from avp_anthropic.subagent import AnthropicSubagentDriver

pytestmark = [
    pytest.mark.real_llm,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set; skipping real-LLM smoke tests",
    ),
]


SMOKE_MODEL = "claude-haiku-4-5-20251001"  # cheapest current Claude


def _new_runner(*, prompt: str, run_id: str) -> AVPAgent:
    config = Commission(
        schema_version="0.1",
        run_id=run_id,
        model=SMOKE_MODEL,
        prompt=prompt,
    )
    return AVPAgent(
        config=config,
        model=AnthropicModelDriver(model=SMOKE_MODEL, max_tokens=200),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor([]),
    )


def _types(traj) -> list[str]:
    return [type(ev).__name__ for ev in traj]


def test_simple_text_response_completes_successfully() -> None:
    """End-to-end: ask Claude one trivial question. Trajectory must contain the full
    AVP-compliant lifecycle and agent_stopped reason='converged'."""
    agent = _new_runner(
        prompt="Reply with exactly the single word 'pong' and nothing else.",
        run_id="smoke-simple-text",
    )
    stop = agent.run()
    types = _types(agent.trajectory)

    assert isinstance(stop, AgentStoppedEvent)
    assert stop.data.avp_reason == StopReason.converged, (
        f"expected converged, got {stop.data.avp_reason}: trajectory types={types}"
    )

    # Lifecycle invariants
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert "CostRecordedEvent" in types
    assert "TextEmittedEvent" in types  # Claude will produce text on a converged run

    # Real call → non-zero cost and tokens
    snap = stop.data.avp_state
    assert snap.total_cost_usd > 0
    assert snap.total_tokens > 0
    assert snap.total_turns >= 1


def test_token_and_cost_accounting_monotonic_across_turns() -> None:
    """RunStateSnapshot accounting MUST be monotonic; consecutive cost_recorded
    events MUST never report decreasing totals."""
    agent = _new_runner(
        prompt="Reply with 'one'. Then if asked again, reply with 'two'. Just answer naturally.",
        run_id="smoke-monotonic",
    )
    agent.run()

    cost_events = [ev for ev in agent.trajectory if isinstance(ev, CostRecordedEvent)]
    assert len(cost_events) >= 1

    last_cost = -1.0
    last_tokens = -1
    for ce in cost_events:
        snap = ce.data.avp_state
        assert snap.total_cost_usd >= last_cost
        assert snap.total_tokens >= last_tokens
        last_cost = snap.total_cost_usd
        last_tokens = snap.total_tokens


def test_subagent_delegation_round_trip_against_real_model() -> None:
    """End-to-end: parent agent calls a declared subagent, the subagent runs
    its own sub-loop on the real Anthropic API, and the wire shape assembles
    correctly: subagent_invoked / subagent_returned pair share a frame
    span_id, nested model_turn events chain through that frame, and the
    parent run converges.

    Two real model calls: one for the parent's tool-use turn, one for the
    subagent's reply. Parent's converging turn may add a third. Short
    prompts keep cost per run under ~$0.002 on Haiku.
    """
    config = Commission(
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
            "argument: 'AVP is a wire format between supervisor and agent.'"
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
            )
        ],
        allowed_tools=["summarizer"],
    )
    # When wiring AVPAgent directly (no CLI), the caller is responsible for
    # exposing Commission.tools and Commission.subagents on the model's surface —
    # `build_anthropic_tools(config)` does the translation, including the
    # MCP `inputSchema` → Anthropic `input_schema` rename and the
    # allowed_tools filter.
    agent = AVPAgent(
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
    stop = agent.run()
    traj = agent.trajectory

    # No driver-level failures (e.g. unsupported_in_v0_1 from the prototype's
    # not-yet-dispatched fields). If this fails, the model invoked the
    # subagent with input the driver couldn't handle, not an API issue.
    failures = [ev for ev in traj if isinstance(ev, SubagentFailedEvent)]
    assert not failures, f"subagent_failed: {[f.data.avp_subagent_error for f in failures]}"

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
    sa_usage = ret.data.avp_subagent_usage
    assert sa_usage.total_cost_usd > 0, "subagent didn't accrue cost — driver swallowed it"
    assert sa_usage.total_tokens > 0
    assert sa_usage.total_turns >= 1
    assert ret.data.avp_subagent_reason == StopReason.converged

    # Parent's cumulative state includes the subagent's spend.
    parent_snap = stop.data.avp_state
    assert parent_snap.total_cost_usd >= sa_usage.total_cost_usd, (
        "subagent usage MUST roll up into parent's RunStateSnapshot so "
        "the parent's aep.state reflects the true total"
    )
    assert stop.data.avp_reason == StopReason.converged


def test_traced_client_drop_in_round_trip_against_real_model() -> None:
    """End-to-end: an existing-shape Anthropic SDK loop that uses
    AnthropicTracedClient instead of AVPAgent. The wire events MUST
    match what AVPAgent would have emitted for the same response —
    same lifecycle, real cost, real tokens.

    This is the test that proves the drop-in story works against the
    actual API: the loop body is a vanilla Anthropic loop with no
    separate tracer; AVP events appear on the wire."""
    import anthropic

    from avp_anthropic import AnthropicTracedClient

    config = Commission(
        schema_version="0.1",
        run_id="smoke-traced-client",
        model=SMOKE_MODEL,
        prompt="Reply with exactly the single word 'pong' and nothing else.",
    )

    out: list = []
    real_client = anthropic.Anthropic()

    with AnthropicTracedClient(real_client, config=config, on_event=out.append) as client:
        msgs = [{"role": "user", "content": config.prompt}]
        while True:
            resp = client.messages.create(model=SMOKE_MODEL, messages=msgs, max_tokens=20)
            if resp.stop_reason == "end_turn":
                client.converged()
                break
            # No tools in this test — tool dispatch path is exercised by
            # the subagent test above and the existing AVPAgent tests.
            break  # safety net

    types = [type(ev).__name__ for ev in out]
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert "TextEmittedEvent" in types
    assert "CostRecordedEvent" in types

    stopped = next(ev for ev in out if isinstance(ev, AgentStoppedEvent))
    assert stopped.data.avp_reason == StopReason.converged
    snap = stopped.data.avp_state
    assert snap.total_cost_usd > 0, "real call should accrue cost"
    assert snap.total_tokens > 0
    assert snap.total_turns >= 1


def test_token_input_includes_cache_reads_when_present() -> None:
    """If the API reports cache_read_input_tokens, the AVP wire's
    gen_ai.usage.input_tokens MUST include them (per SPEC.md §9.4). On a
    single short call we likely get 0 cache reads; this test just asserts
    the math: input_tokens >= cache_read.input_tokens when present."""
    agent = _new_runner(
        prompt="Reply with 'ok'.",
        run_id="smoke-cache-tokens",
    )
    agent.run()

    turn_ends = [ev for ev in agent.trajectory if isinstance(ev, ModelTurnEndedEvent)]
    assert turn_ends
    for te in turn_ends:
        cache_read = te.data.gen_ai_usage_cache_read_input_tokens
        if cache_read is not None:
            input_total = te.data.gen_ai_usage_input_tokens
            assert input_total >= cache_read, (
                f"AVP §9.4: gen_ai.usage.input_tokens ({input_total}) MUST include "
                f"cache reads ({cache_read}); driver may be subtracting them"
            )
