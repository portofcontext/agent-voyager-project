"""Tests for the Subagent Commission primitive and the subagent event lifecycle.

Subagent is the AVP analogue of Claude Agent SDK `AgentDefinition`, Google
ADK `LlmAgent.sub_agents`, and `deepagents.SubAgent` — a declared resource
the parent agent can delegate to. The wire surface is its own three-event
lifecycle (`subagent_invoked` / `subagent_returned` / `subagent_failed`)
so nested turns observe as a span tree rather than flatten into a single
tool_use → tool_result pair.

These tests pin:
  - Commission accepts a list of Subagent objects with the documented shape
  - The three event types parse to their Pydantic models and round-trip
    to the dotted-alias wire form (OTel GenAI conventions)
  - The frame span_id on subagent_invoked matches subagent_returned —
    consumers pair them by span_id
"""

from __future__ import annotations

from avp import (
    Commission,
    Skill,
    Subagent,
    SubagentFailedEvent,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    event_to_wire,
    parse_event,
)
from avp.types import (
    SOURCE_AGENT,
    ZERO_SPAN_ID,
    new_event_id,
    new_span_id,
    new_trace_id,
)


def _envelope(type_: str, run_id: str, data: dict) -> dict:
    return {
        "specversion": "1.0",
        "id": new_event_id(),
        "source": SOURCE_AGENT,
        "type": type_,
        "subject": run_id,
        "time": "2026-05-06T18:00:00Z",
        "datacontenttype": "application/json",
        "data": data,
    }


def _span(parent: str = ZERO_SPAN_ID, span_id: str | None = None) -> dict:
    return {
        "trace_id": new_trace_id(),
        "span_id": span_id or new_span_id(),
        "parent_span_id": parent,
    }


def test_config_accepts_subagents_with_full_environment_slice() -> None:
    """A Subagent carries an environment slice mirroring Commission — its own
    system_prompt, model, tools, skills."""
    commission = Commission(
        schema_version="0.1",
        run_id="r-1",
        subagents=[
            Subagent(
                name="code-explorer",
                description="Explores the codebase and reports findings.",
                system_prompt="You are a careful code reader.",
                model="claude-haiku-4-5-20251001",
                inputSchema={
                    "type": "object",
                    "properties": {"prompt": {"type": "string"}},
                    "required": ["prompt"],
                },
                skills=[Skill(name="search-tips", **{"avp.source": "./skills/search-tips"})],
                exposed=["*"],
            )
        ],
        exposed=["*"],
    )
    assert commission.subagents is not None
    sa = commission.subagents[0]
    assert sa.name == "code-explorer"
    assert sa.inherit_tools is False  # default — matches Google ADK / safer than CASDK
    assert sa.skills and sa.skills[0].name == "search-tips"


def test_subagent_name_pattern_enforced() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Subagent(name="Bad Name", description="x", exposed=["*"])
    with pytest.raises(ValidationError):
        Subagent(name="UPPERCASE", description="x", exposed=["*"])


def test_subagent_recursion_declared_in_type() -> None:
    """Subagents may declare their own subagents. Whether an agent enables
    recursive dispatch is its own concern; the wire type allows it."""
    sa = Subagent(
        name="parent",
        description="delegates",
        subagents=[Subagent(name="child", description="leaf")],
        exposed=["*"],
    )
    assert sa.subagents and sa.subagents[0].name == "child"


def test_subagent_invoked_event_parses_and_round_trips() -> None:
    frame_span = new_span_id()
    parent_turn_span = new_span_id()
    payload = _envelope(
        "avp.subagent_invoked",
        "r-1",
        {
            **_span(parent=parent_turn_span, span_id=frame_span),
            "step": 2,
            "gen_ai.agent.name": "code-explorer",
            "gen_ai.agent.description": "Explores the codebase",
            "gen_ai.operation.name": "invoke_agent",
            "avp.subagent.invocation_id": "sa-1",
            "avp.subagent.input": {"prompt": "find auth handlers"},
        },
    )
    ev = parse_event(payload)
    assert isinstance(ev, SubagentInvokedEvent)
    assert ev.data.gen_ai_agent_name == "code-explorer"
    assert ev.data.avp_subagent_invocation_id == "sa-1"
    assert ev.data.gen_ai_operation_name == "invoke_agent"
    # The span_id of subagent_invoked roots the subagent's frame.
    assert ev.data.span_id == frame_span
    assert ev.data.parent_span_id == parent_turn_span

    wire = event_to_wire(ev)
    # Dotted aliases on the wire — Python attr names MUST NOT leak.
    assert "gen_ai.agent.name" in wire["data"]
    assert "avp.subagent.invocation_id" in wire["data"]
    assert "gen_ai_agent_name" not in wire["data"]


def test_subagent_returned_event_carries_usage_rollup_and_pairs_with_invoked() -> None:
    """subagent_returned MUST share the frame span_id with the matching
    subagent_invoked. Consumers pair the two events by span_id and
    reconstruct the subagent's nested span tree from descendants of that
    span_id."""
    frame_span = new_span_id()
    parent_turn_span = new_span_id()
    payload = _envelope(
        "avp.subagent_returned",
        "r-1",
        {
            **_span(parent=parent_turn_span, span_id=frame_span),
            "step": 2,
            "gen_ai.agent.name": "code-explorer",
            "avp.subagent.invocation_id": "sa-1",
            "duration_ms": 4321,
            "avp.subagent.result.text": "Found 3 handlers in src/auth/.",
            "avp.subagent.reason": "converged",
            "avp.subagent.usage": {
                "total_cost_usd": 0.012,
                "total_tokens": 850,
                "total_turns": 3,
                "tokens_input_total": 600,
                "tokens_output_total": 250,
            },
        },
    )
    ev = parse_event(payload)
    assert isinstance(ev, SubagentReturnedEvent)
    assert ev.data.span_id == frame_span
    assert ev.data.avp_subagent_reason == "converged"
    assert ev.data.avp_subagent_usage.total_turns == 3
    assert ev.data.avp_subagent_usage.total_cost_usd == 0.012

    wire = event_to_wire(ev)
    assert "avp.subagent.result.text" in wire["data"]
    assert "avp.subagent.usage" in wire["data"]
    assert wire["data"]["avp.subagent.reason"] == "converged"


def test_subagent_failed_event_parses() -> None:
    payload = _envelope(
        "avp.subagent_failed",
        "r-1",
        {
            **_span(),
            "step": 1,
            "gen_ai.agent.name": "code-explorer",
            "avp.subagent.invocation_id": "sa-1",
            "duration_ms": 12,
            "avp.subagent.error": "subagent driver not configured",
            "avp.subagent.error.code": "not_configured",
        },
    )
    ev = parse_event(payload)
    assert isinstance(ev, SubagentFailedEvent)
    assert ev.data.avp_subagent_error == "subagent driver not configured"
    assert ev.data.avp_subagent_error_code == "not_configured"
