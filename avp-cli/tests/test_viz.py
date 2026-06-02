"""Viewer-link payload shaping: single-agent stays flat, multi-agent folds into one.

Plus the trajectory -> RunEvent projection seam: the viz events MUST carry the
real AVP wire `type` and wire field names, not a re-vocabulary.
"""

from __future__ import annotations

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
from avp_cli import viz


def _payload(agent: str) -> dict:
    return {
        "eval_version": "v1",
        "snapshot_at": "2026-05-28T00:00:00Z",
        "agent": agent,
        "by_commission": {"baseline": []},
        "commissions": {"baseline": {}},
    }


def test_run_events_carry_the_real_wire_vocabulary() -> None:
    """The projection mirrors the wire: real `avp.*` types, wire field names.

    Guards against re-growing a bespoke display vocabulary (the removed
    `model_turn_ended` event, the `tokens_in`/`tokens_out` aliases).
    """
    trace, agent_span, turn_span, tool_span = (
        new_trace_id(),
        new_span_id(),
        new_span_id(),
        new_span_id(),
    )

    def span(span_id: str, parent: str) -> dict:
        return {"trace_id": trace, "span_id": span_id, "parent_span_id": parent}

    events = [
        AgentStartedEvent(subject="r", data=AgentStartedData(**span(agent_span, ZERO_SPAN_ID))),
        AssistantMessageEvent(
            subject="r",
            data=AssistantMessageData(
                **span(turn_span, agent_span),
                step=1,
                duration_ms=10,
                content=[TextBlock(text="hi")],
                usage=Usage(input_tokens=10, output_tokens=5),
                cost_usd=0.001,
                response_model="claude",
            ),
        ),
        ToolInvokedEvent(
            subject="r",
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
            subject="r",
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
            subject="r",
            data=AgentStoppedData(**span(new_span_id(), agent_span), reason=StopReason.converged),
        ),
    ]
    run = viz.trajectory_to_run(events, run_id="r")
    by_type = {e["type"]: e for e in run["events"]}

    # Real wire types, verbatim, in order.
    assert [e["type"] for e in run["events"]] == [
        "avp.agent_started",
        "avp.assistant_message",
        "avp.tool_invoked",
        "avp.tool_returned",
        "avp.agent_stopped",
    ]
    # No re-vocabulary survives anywhere in the projection.
    blob = str(run["events"])
    for banned in ("model_turn_ended", "tokens_in", "tokens_out"):
        assert banned not in blob

    # Wire field names, not aliases.
    am = by_type["avp.assistant_message"]
    assert am["input_tokens"] == 10 and am["output_tokens"] == 5
    assert am["response_model"] == "claude"
    assert by_type["avp.tool_invoked"]["tool_name"] == "bash"
    assert by_type["avp.tool_invoked"]["tool_dispatch_target"] == "local"
    assert by_type["avp.agent_stopped"]["reason"] == "converged"


def test_combine_single_agent_stays_flat() -> None:
    p = _payload("goose")
    assert viz.combine_payloads([p]) is p  # no wrapper for the common case


def test_combine_multi_agent_wraps_into_agents() -> None:
    combined = viz.combine_payloads([_payload("goose"), _payload("claude-code")])
    assert set(combined) == {"eval_version", "snapshot_at", "agents"}
    assert [a["agent"] for a in combined["agents"]] == ["goose", "claude-code"]
    # each agent keeps its own by_commission slice
    assert all("by_commission" in a for a in combined["agents"])


def test_combined_link_roundtrips_through_the_site_decode() -> None:
    import base64
    import gzip
    import json

    combined = viz.combine_payloads([_payload("goose"), _payload("claude-code")])
    url = viz.view_url(combined, site="http://localhost:3000")
    z = url.split("#z=", 1)[1]
    # mirror payload.ts: base64url -> base64 -> gunzip -> json
    decoded = json.loads(gzip.decompress(base64.b64decode(z.replace("-", "+").replace("_", "/"))))
    assert decoded == combined
