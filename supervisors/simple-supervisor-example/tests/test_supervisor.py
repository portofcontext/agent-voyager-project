"""Tests for simple-supervisor-example.

Covers the wire-level supervisor logic that doesn't need a live agent:
  - Profile → Commission compilation
  - Trajectory → Summary classification (reducing per-turn assistant_message deltas)
  - Subprocess wrapper drives the reference agent with a scripted driver
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from simple_supervisor import (
    DEV_LOOSE,
    READ_ONLY,
    Summary,
    build_commission,
    render,
    summarize,
)

from avp.content import TextBlock, ToolResultBlock
from avp.envelope import ZERO_SPAN_ID, new_span_id, new_trace_id
from avp.trajectory import (
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    AssistantMessageData,
    AssistantMessageEvent,
    StopReason,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    Usage,
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


# ── Trajectory summarization (reduces per-turn assistant_message deltas) ───────


def test_summarize_reduces_facts_from_the_stream() -> None:
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
                **span(agent_span, ZERO_SPAN_ID), request_model="m", provider_name="anthropic"
            ),
        ),
        AssistantMessageEvent(
            subject="r-summary",
            data=AssistantMessageData(
                **span(turn_span, agent_span),
                step=1,
                duration_ms=10,
                content=[TextBlock(text="running bash")],
                usage=Usage(input_tokens=10, output_tokens=5),
                cost_usd=0.001,
            ),
        ),
        ToolInvokedEvent(
            subject="r-summary",
            data=ToolInvokedData(
                **span(tool_span, turn_span),
                step=1,
                tool_call_id="c1",
                tool_name="bash",
                tool_input={"x": 1},
                tool_dispatch_target="local",
            ),
        ),
        ToolReturnedEvent(
            subject="r-summary",
            data=ToolReturnedData(
                **span(new_span_id(), tool_span),
                step=1,
                tool_call_id="c1",
                tool_name="bash",
                duration_ms=1,
                tool_result=ToolResultBlock(tool_use_id="c1", content="ok"),
            ),
        ),
        AgentStoppedEvent(
            subject="r-summary",
            data=AgentStoppedData(**span(new_span_id(), agent_span), reason=StopReason.converged),
        ),
    ]
    s = summarize(events)
    assert isinstance(s, Summary)
    assert s.run_id == "r-summary"
    assert s.stop_reason == "converged"
    assert s.total_turns == 1
    assert s.tools["bash"].invocations == 1
    # Reduced from the single assistant_message delta.
    assert pytest.approx(s.total_cost_usd, abs=1e-9) == 0.001
    assert s.total_tokens == 15

    rendered = render(s)
    assert "bash: 1 call" in rendered


def test_summarize_counts_tool_failures() -> None:
    trace = new_trace_id()

    def span(parent: str = ZERO_SPAN_ID) -> dict:
        return {"trace_id": trace, "span_id": new_span_id(), "parent_span_id": parent}

    events = [
        ToolInvokedEvent(
            subject="r",
            data=ToolInvokedData(
                **span(), step=1, tool_call_id="c1", tool_name="bash", tool_input={}
            ),
        ),
        ToolReturnedEvent(
            subject="r",
            data=ToolReturnedData(
                **span(),
                step=1,
                tool_call_id="c1",
                tool_name="bash",
                duration_ms=1,
                tool_result=ToolResultBlock(tool_use_id="c1", content="boom", is_error=True),
            ),
        ),
    ]
    s = summarize(events)
    assert s.tools["bash"].failures == 1


# ── Subprocess wrapper end-to-end (no LLM — a scripted driver feeds run_agent) ──

_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"

_INLINE_SCRIPTED_AGENT = f"""\
import json, sys
sys.path.insert(0, {str(_EXAMPLES_DIR)!r})

from _anthropic_reference_agent import run_agent, stdout_sink
from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp_anthropic import ModelResponse, ToolOutcome
from avp_anthropic.translate import ScriptedToolCall


class ScriptedDriver:
    model = "scripted-model"

    def __init__(self, responses):
        self._responses = list(responses)

    def step(self, history):
        return self._responses.pop(0)


class DictTools:
    def is_local(self, tool):
        return True

    def invoke(self, tool, input):
        return ToolOutcome(output="hi", duration_ms=1)


commission = Commission.model_validate(json.loads(sys.stdin.readline()))
driver = ScriptedDriver([
    ModelResponse(
        tokens_input=50, tokens_output=10, cost_usd=0.001, duration_ms=1,
        text="running bash",
        tool_calls=[ScriptedToolCall(call_id="c1", tool="bash", input={{"cmd": "echo hi"}})],
        converged=False,
    ),
    ModelResponse(
        tokens_input=10, tokens_output=5, cost_usd=0.0005, duration_ms=1,
        text="all done", converged=True,
    ),
])
desc = AgentDescriptor(agent_name="scripted", agent_version="0.1", spec_version="0.1")
run_agent(commission, driver=driver, tools=DictTools(), desc=desc, started_tools=[], sink=stdout_sink)
"""


def test_run_subprocess_drives_a_real_agent_end_to_end(tmp_path) -> None:
    """Spawn a tiny inline agent that feeds the reference `run_agent` loop a
    scripted driver, pipe a Commission in, parse events out. Pins the
    supervisor↔agent subprocess seam end-to-end without an LLM."""
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
        timeout_s=20.0,
    )

    types = [getattr(ev, "type", None) for ev in events if hasattr(ev, "type")]
    assert "avp.agent_started" in types
    assert "avp.assistant_message" in types
    assert "avp.tool_invoked" in types
    assert "avp.tool_returned" in types
    assert "avp.agent_stopped" in types

    s = summarize(events)
    assert s.stop_reason == "converged"
    assert s.tools["bash"].invocations == 1
    assert s.total_turns == 2
