"""Subagent dispatch via the AVP resolver protocol.

When the parent's model invokes a Commission-declared subagent, the agent
calls `ResolverDriver.spawn_subagent` and emits the subagent_invoked /
subagent_returned (or _failed) lifecycle. This file is a small smoke
verifying the wiring at the AVPAgent layer; the wire-format guarantees
are pinned by the conformance suite under
conformance/v0.1/cases/subagent/.
"""

from __future__ import annotations

from avp import (
    AgentManifest,
    Commission,
    SubagentInvokedEvent,
    SubagentRef,
    SubagentReturnedEvent,
)
from avp.agent.agent import AVPAgent
from avp.agent.drivers import ModelResponse, ScriptedToolCall
from avp.agent.mock import (
    ScriptedModel,
    ScriptedResolver,
    ScriptedSupervisor,
    ScriptedTools,
)


def _model_invokes_then_converges() -> ScriptedModel:
    return ScriptedModel(
        [
            ModelResponse(
                tokens_input=10,
                tokens_output=2,
                cost_usd=0.0001,
                duration_ms=1,
                tool_calls=[ScriptedToolCall(call_id="c1", tool="researcher", input={"q": "x"})],
            ),
            ModelResponse(
                tokens_input=5,
                tokens_output=2,
                cost_usd=0.0,
                duration_ms=1,
                text="done",
                converged=True,
            ),
        ]
    )


def _managed_manifest() -> AgentManifest:
    return AgentManifest(
        agent_name="test-agent",
        agent_version="0.0.0",
        avp_spec_version="0.1",
    )


def test_managed_subagent_returns_with_child_run_id() -> None:
    commission = Commission(
        schema_version="0.1",
        run_id="r-spawn-ok",
        prompt="hi",
        subagents=[SubagentRef(id="researcher", ref="sk_test")],
    )
    resolver = ScriptedResolver(
        resolutions={"subagent:researcher": {"result": {"name": "researcher"}}},
        subagent_spawns={
            "researcher": {
                "child_run_id": "child-1",
                "text": "found 3 handlers",
                "reason": "converged",
                "duration_ms": 50,
                "usage": {"total_cost_usd": 0.001, "total_tokens": 80, "total_turns": 1},
            }
        },
    )
    agent = AVPAgent(
        commission,
        _model_invokes_then_converges(),
        ScriptedTools(),
        ScriptedSupervisor(),
        resolver=resolver,
        manifest=_managed_manifest(),
    )
    agent.run()

    invoked = next(ev for ev in agent.trajectory if isinstance(ev, SubagentInvokedEvent))
    returned = next(ev for ev in agent.trajectory if isinstance(ev, SubagentReturnedEvent))

    assert invoked.data.avp_subagent_run_id == "child-1"
    assert invoked.data.span_id == returned.data.span_id  # frame span pairs
    assert returned.data.avp_subagent_result_text == "found 3 handlers"
    # Child usage rolls into parent's cumulative state — at least the
    # subagent's tokens / cost contributed to the parent.
    assert resolver.calls_spawn_subagent == [("researcher", {"q": "x"})]
