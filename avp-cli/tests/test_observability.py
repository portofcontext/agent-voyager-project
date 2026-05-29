"""Trajectory → Summary reduction (the per-turn assistant_message delta fold).

The eval engine (setups, scoring, board) is covered in test_eval_engine.py; the
supervisor↔agent subprocess seam is covered there too (run_eval driving a
scripted agent).
"""

from __future__ import annotations

import pytest

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
from avp_cli import Summary, render, summarize

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
