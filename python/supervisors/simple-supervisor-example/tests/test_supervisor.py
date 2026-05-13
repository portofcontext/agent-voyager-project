"""Tests for simple-supervisor-example.

Covers the wire-level supervisor logic that doesn't need a live agent:
  - Profile → Commission compilation
  - Trajectory → Summary classification
  - Subprocess wrapper drives the reference avp agent with ScriptedModel
"""

from __future__ import annotations

import sys

import pytest
from simple_supervisor import (
    DEV_LOOSE,
    READ_ONLY,
    Summary,
    build_commission,
    render,
    summarize,
)

from avp.commission import Commission
from avp.enums import StopReason
from avp.trajectory import (
    AgentStartedEvent,
    AgentStoppedEvent,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)

# ── Profile / Commission compilation ──────────────────────────────────────────────


def test_build_commission_inherits_dev_loose_profile() -> None:
    commission = build_commission(run_id="r1", prompt="x", profile="dev-loose")
    # dev-loose enables every built-in (None = no allowlist).
    assert commission.enabled_builtin_tools is None


def test_build_commission_inherits_read_only_profile() -> None:
    commission = build_commission(run_id="r1", prompt="x", profile="read-only")
    assert commission.enabled_builtin_tools == ["read_file"]


def test_profiles_are_distinct() -> None:
    assert DEV_LOOSE.enabled_builtin_tools != READ_ONLY.enabled_builtin_tools


# ── Trajectory summarization ──────────────────────────────────────────────────


def _make_state(*, cost: float, tokens: int, turns: int) -> dict:
    return {
        "total_cost_usd": cost,
        "total_tokens": tokens,
        "total_turns": turns,
        "started_at": "2026-05-04T18:00:00Z",
        "duration_ms": 1234,
    }


def test_summarize_classifies_fact_classes() -> None:
    from avp.trajectory import (
        ZERO_SPAN_ID,
        AgentStartedData,
        AgentStoppedData,
        CostRecordedData,
        ModelTurnEndedData,
        ToolInvokedData,
        ToolReturnedData,
        new_span_id,
        new_trace_id,
    )

    Commission(schema_version="0.1", run_id="r-summary", model="m")
    trace = new_trace_id()
    agent_span = new_span_id()
    turn_span = new_span_id()
    tool_span = new_span_id()

    def span(span_id: str, parent: str) -> dict:
        return {"trace_id": trace, "span_id": span_id, "parent_span_id": parent}

    events = [
        AgentStartedEvent(
            subject="r-summary",
            data=AgentStartedData(
                **span(agent_span, ZERO_SPAN_ID),
                **{"gen_ai.request.model": "m"},
            ),
        ),
        ModelTurnEndedEvent(
            subject="r-summary",
            data=ModelTurnEndedData(
                **span(turn_span, agent_span),
                step=1,
                duration_ms=10,
                **{
                    "gen_ai.usage.input_tokens": 10,
                    "gen_ai.usage.output_tokens": 5,
                    "avp.cost_usd": 0.001,
                },
            ),
        ),
        ToolInvokedEvent(
            subject="r-summary",
            data=ToolInvokedData(
                **span(tool_span, turn_span),
                step=1,
                **{
                    "gen_ai.tool.call.id": "c1",
                    "gen_ai.tool.name": "bash",
                    "gen_ai.tool.call.arguments": {"x": 1},
                },
            ),
        ),
        ToolReturnedEvent(
            subject="r-summary",
            data=ToolReturnedData(
                **span(tool_span, turn_span),
                step=1,
                duration_ms=1,
                **{
                    "gen_ai.tool.call.id": "c1",
                    "gen_ai.tool.name": "bash",
                    "avp.tool.result.text": "ok",
                },
            ),
        ),
        CostRecordedEvent(
            subject="r-summary",
            data=CostRecordedData(
                **span(new_span_id(), turn_span),
                **{"avp.state": _make_state(cost=0.001, tokens=15, turns=1)},
            ),
        ),
        AgentStoppedEvent(
            subject="r-summary",
            data=AgentStoppedData(
                **span(agent_span, ZERO_SPAN_ID),
                **{
                    "avp.reason": StopReason.converged,
                    "avp.state": _make_state(cost=0.001, tokens=15, turns=1),
                    "avp.total_tokens": 15,
                    "avp.total_cost_usd": 0.001,
                    "avp.total_turns": 1,
                    "avp.duration_ms": 1234,
                },
            ),
        ),
    ]
    s = summarize(events)
    assert isinstance(s, Summary)
    assert s.run_id == "r-summary"
    assert s.stop_reason == "converged"
    assert s.total_turns == 1
    assert s.tools["bash"].invocations == 1
    assert pytest.approx(s.total_cost_usd, abs=1e-9) == 0.001

    rendered = render(s)
    assert "bash: 1 call" in rendered


# ── Subprocess wrapper end-to-end (uses no LLM — pipes to a tiny scripted agent) ──


_INLINE_SCRIPTED_AGENT = """\
import json, sys
from avp.commission import Commission
from avp.io import write_event
from avp.agent import AVPAgent
from avp.agent.mock import ScriptedTools, ScriptedSupervisor, parse_scripted_model

cfg_line = sys.stdin.readline()
commission = Commission.model_validate(json.loads(cfg_line))

# Two-turn scripted run: turn 1 calls 'bash', turn 2 converges.
model = parse_scripted_model([
    {
        "tokens_input": 50, "tokens_output": 10, "cost_usd": 0.001, "duration_ms": 1,
        "text": "running bash",
        "tool_calls": [{"call_id": "c1", "tool": "bash", "input": {"cmd": "echo hi"}}],
        "converged": False,
    },
    {
        "tokens_input": 10, "tokens_output": 5, "cost_usd": 0.0005, "duration_ms": 1,
        "text": "all done", "converged": True,
    },
])
tools = ScriptedTools({"bash": {"output": "hi", "duration_ms": 1}})

# Streaming supervisor: every observed event gets written to stdout as NDJSON.
class _StreamingSupervisor(ScriptedSupervisor):
    def observe(self, event):
        super().observe(event)
        write_event(event, file=sys.stdout)

agent = AVPAgent(commission=commission,
    model=model,
    tools=tools,
    supervisor=_StreamingSupervisor([]),
    agent_builtin_tools=[
        {"name": "bash"},
        {"name": "read_file"},
        {"name": "write_file"},
    ],
)
agent.run()
"""


def test_run_subprocess_drives_a_real_agent_end_to_end(tmp_path) -> None:
    """Spawn a tiny inline agent that uses ScriptedModel + ScriptedTools, pipe a
    Commission in, parse events out. Pins the wire-level supervisor flow."""
    from simple_supervisor import run_subprocess

    agent_script = tmp_path / "tiny_agent.py"
    agent_script.write_text(_INLINE_SCRIPTED_AGENT)

    commission = build_commission(
        run_id="subprocess-smoke",
        prompt="anything",
        profile="dev-loose",
    )

    events = run_subprocess(
        [sys.executable, str(agent_script)],
        commission,
        timeout_s=10.0,
    )

    types = [getattr(ev, "type", None) for ev in events if hasattr(ev, "type")]
    assert "avp.agent_started" in types
    assert "avp.model_turn_started" in types
    assert "avp.tool_invoked" in types
    assert "avp.tool_returned" in types
    assert "avp.agent_stopped" in types

    s = summarize(events)
    assert s.stop_reason == "converged"
    assert s.tools["bash"].invocations == 1
    assert s.total_turns == 2
