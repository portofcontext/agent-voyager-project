"""Server-side tool calls (e.g. Anthropic's MCP connector running tools
inline during the request) MUST surface as per-call tool_invoked /
tool_returned events on the AVP wire — not get rolled up into the
model_turn_ended cost.

The driver populates `ModelResponse.server_tool_calls` with a
`ServerToolCall` per inline call; the agent emits synthetic
tool_invoked + tool_returned (or tool_failed) events parented to the
turn span. This pins the wire shape so the trajectory has the same
per-call detail for server-side and agent-dispatched tools.
"""

from __future__ import annotations

from avp import Commission
from avp.agent.agent import AVPAgent
from avp.agent.drivers import ModelResponse, ServerToolCall
from avp.agent.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from avp.types import (
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    ToolFailedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)


def _by_type(traj, type_):
    return [e for e in traj if isinstance(e, type_)]


def _converged_with_server_calls(server_tool_calls: list[ServerToolCall]) -> ModelResponse:
    return ModelResponse(
        tokens_input=10,
        tokens_output=5,
        cost_usd=0.0001,
        duration_ms=1,
        text="done",
        converged=True,
        server_tool_calls=server_tool_calls,
    )


def _agent(model: ScriptedModel) -> AVPAgent:
    commission = Commission(schema_version="0.1", run_id="server-tool", model="test/mock")
    return AVPAgent(
        commission=commission,
        model=model,
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )


# ── Synthesis: per-call events emitted ─────────────────────────────────────


def test_server_tool_call_emits_invoked_and_returned() -> None:
    agent = _agent(
        ScriptedModel(
            [
                _converged_with_server_calls(
                    [
                        ServerToolCall(
                            call_id="srvtu_01",
                            tool="get_forecast",
                            input={"city": "NYC"},
                            output_text="sunny, 72F",
                            duration_ms=42,
                            dispatch_target="mcp_server",
                            server_id="weather",
                        )
                    ]
                )
            ]
        )
    )
    agent.run()

    invoked = _by_type(agent.trajectory, ToolInvokedEvent)
    returned = _by_type(agent.trajectory, ToolReturnedEvent)
    assert len(invoked) == 1
    assert len(returned) == 1

    inv = invoked[0]
    assert inv.data.gen_ai_tool_call_id == "srvtu_01"
    assert inv.data.gen_ai_tool_name == "get_forecast"
    assert inv.data.gen_ai_tool_call_arguments == {"city": "NYC"}
    assert inv.data.avp_tool_dispatch_target == "mcp_server"

    # mcp_server_id surfaces under its dotted alias (extras=allow on _SpanData).
    wire = inv.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert wire["data"]["avp.mcp_server_id"] == "weather"

    ret = returned[0]
    assert ret.data.gen_ai_tool_call_id == "srvtu_01"
    assert ret.data.avp_tool_result_text == "sunny, 72F"
    assert ret.data.duration_ms == 42


def test_server_tool_call_pairs_invoked_and_returned_on_same_span() -> None:
    """Per AVP wire convention, paired events for the same tool call MUST
    share a span_id (so consumers can correlate them) and trace_id (one
    run = one tree)."""
    agent = _agent(
        ScriptedModel(
            [
                _converged_with_server_calls(
                    [
                        ServerToolCall(
                            call_id="srvtu_02",
                            tool="search",
                            input={"q": "x"},
                            output_text="ok",
                        )
                    ]
                )
            ]
        )
    )
    agent.run()

    invoked = _by_type(agent.trajectory, ToolInvokedEvent)[0]
    returned = _by_type(agent.trajectory, ToolReturnedEvent)[0]
    assert invoked.data.span_id == returned.data.span_id
    assert invoked.data.trace_id == returned.data.trace_id


def test_server_tool_call_parented_to_turn_span() -> None:
    """The inline call happened during the model's turn — parent_span_id
    MUST point to the model_turn_started span, not the agent root, so
    the trajectory tree reconstructs as turn → tool, not agent → tool."""
    agent = _agent(
        ScriptedModel(
            [
                _converged_with_server_calls(
                    [
                        ServerToolCall(
                            call_id="srvtu_03",
                            tool="x",
                            input={},
                            output_text="ok",
                        )
                    ]
                )
            ]
        )
    )
    agent.run()

    turn_started = _by_type(agent.trajectory, ModelTurnStartedEvent)[0]
    invoked = _by_type(agent.trajectory, ToolInvokedEvent)[0]
    assert invoked.data.parent_span_id == turn_started.data.span_id


def test_error_server_tool_call_emits_tool_failed_not_returned() -> None:
    agent = _agent(
        ScriptedModel(
            [
                _converged_with_server_calls(
                    [
                        ServerToolCall(
                            call_id="srvtu_err",
                            tool="broken",
                            input={},
                            output_text="connection refused",
                            is_error=True,
                            server_id="weather",
                        )
                    ]
                )
            ]
        )
    )
    agent.run()

    assert _by_type(agent.trajectory, ToolInvokedEvent)
    assert not _by_type(agent.trajectory, ToolReturnedEvent)
    failed = _by_type(agent.trajectory, ToolFailedEvent)
    assert len(failed) == 1
    assert failed[0].data.avp_tool_error == "connection refused"


def test_no_server_tool_calls_emits_no_synthetic_events() -> None:
    """Backwards-compat: without server_tool_calls, agent behaviour
    is unchanged — no synthetic tool events for turns where the API
    didn't run any inline tools."""
    agent = _agent(
        ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="hi",
                    converged=True,
                )
            ]
        )
    )
    agent.run()
    assert not _by_type(agent.trajectory, ToolInvokedEvent)
    assert not _by_type(agent.trajectory, ToolReturnedEvent)


def test_server_tool_calls_emitted_after_turn_ended() -> None:
    """Ordering: server-tool synthetic events MUST come AFTER the turn's
    model_turn_ended event so consumers reading the wire can trust the
    "turn closes before its inline tools are described" invariant."""
    agent = _agent(
        ScriptedModel(
            [
                _converged_with_server_calls(
                    [
                        ServerToolCall(
                            call_id="srvtu_order",
                            tool="t",
                            input={},
                            output_text="ok",
                        )
                    ]
                )
            ]
        )
    )
    agent.run()
    types = [type(e).__name__ for e in agent.trajectory]
    turn_ended_idx = types.index("ModelTurnEndedEvent")
    invoked_idx = types.index("ToolInvokedEvent")
    returned_idx = types.index("ToolReturnedEvent")
    assert turn_ended_idx < invoked_idx < returned_idx
    # Sanity: model_turn_ended is reachable.
    assert _by_type(agent.trajectory, ModelTurnEndedEvent)


def test_multiple_server_tool_calls_in_one_turn_each_get_paired_events() -> None:
    agent = _agent(
        ScriptedModel(
            [
                _converged_with_server_calls(
                    [
                        ServerToolCall(
                            call_id="a", tool="t1", input={}, output_text="r1", server_id="s1"
                        ),
                        ServerToolCall(
                            call_id="b", tool="t2", input={}, output_text="r2", server_id="s2"
                        ),
                    ]
                )
            ]
        )
    )
    agent.run()
    invoked = _by_type(agent.trajectory, ToolInvokedEvent)
    returned = _by_type(agent.trajectory, ToolReturnedEvent)
    assert [e.data.gen_ai_tool_call_id for e in invoked] == ["a", "b"]
    assert [e.data.gen_ai_tool_call_id for e in returned] == ["a", "b"]
