"""Seam test for subagent dispatch through AEPRunner.

Crosses runner ↔ subagent_driver: the parent's scripted model emits a
tool_use whose name matches a declared Subagent; the runner's
`_handle_subagent_call` routes through the supplied SubagentDriver and
emits the documented three-event lifecycle. The frame span_id from
`subagent_invoked` MUST equal the span_id on the matching
`subagent_returned`, and any nested events the driver emits MUST chain
through that span.

This is the layer most likely to drift. Unit tests on parsing won't
catch a runner that emits the wrong span shape.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from aep import (
    Config,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    Subagent,
    SubagentFailedEvent,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    TextEmittedEvent,
)
from aep.enums import StopReason
from aep.runner import AEPRunner
from aep.runner.drivers import (
    ModelResponse,
    ScriptedToolCall,
    SubagentDriver,
    SubagentOutcome,
)
from aep.runner.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from aep.types import (
    ModelTurnEndedData,
    ModelTurnStartedData,
    RunStateSnapshot,
    TextEmittedData,
    new_span_id,
)
from aep.types import (
    Subagent as _Subagent,
)


class _StubSubagentDriver(SubagentDriver):
    """Records every invocation, emits two synthetic nested model_turn
    events under the parent_frame_span_id, and returns a fixed text."""

    def __init__(self, *, text: str = "subagent reply", reason: StopReason = StopReason.converged):
        self.text = text
        self.reason = reason
        self.invocations: list[dict[str, Any]] = []

    def invoke(
        self,
        subagent: _Subagent,
        invocation_input: dict[str, Any],
        *,
        parent_trace_id: str,
        parent_frame_span_id: str,
        parent_observer: Callable[[BaseModel], None],
    ) -> SubagentOutcome:
        self.invocations.append(
            {
                "name": subagent.name,
                "input": dict(invocation_input),
                "parent_trace_id": parent_trace_id,
                "parent_frame_span_id": parent_frame_span_id,
            }
        )

        # Emit one model_turn pair under the frame span. Real drivers loop;
        # this is enough to prove span linkage.
        turn_span_id = new_span_id()
        parent_observer(
            ModelTurnStartedEvent(
                subject=None,
                data=ModelTurnStartedData(
                    trace_id=parent_trace_id,
                    span_id=turn_span_id,
                    parent_span_id=parent_frame_span_id,
                    step=1,
                    **{"aep.context_messages": 1},
                ),
            )
        )
        parent_observer(
            TextEmittedEvent(
                subject=None,
                data=TextEmittedData(
                    trace_id=parent_trace_id,
                    span_id=new_span_id(),
                    parent_span_id=turn_span_id,
                    step=1,
                    **{"aep.text": self.text},
                ),
            )
        )
        parent_observer(
            ModelTurnEndedEvent(
                subject=None,
                data=ModelTurnEndedData(
                    trace_id=parent_trace_id,
                    span_id=turn_span_id,
                    parent_span_id=parent_frame_span_id,
                    step=1,
                    duration_ms=10,
                    **{
                        "gen_ai.usage.input_tokens": 50,
                        "gen_ai.usage.output_tokens": 25,
                        "aep.cost_usd": 0.0001,
                    },
                ),
            )
        )

        return SubagentOutcome(
            text=self.text,
            reason=self.reason,
            duration_ms=42,
            usage=RunStateSnapshot(
                total_cost_usd=0.0001,
                total_tokens=75,
                total_turns=1,
                tokens_input_total=50,
                tokens_output_total=25,
            ),
        )


def _run(config: Config, *, scripted_model: list[ModelResponse], driver: SubagentDriver):
    runner = AEPRunner(
        config=config,
        model=ScriptedModel(scripted_model),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
        subagent_driver=driver,
    )
    runner.run()
    return runner


def _by_type(traj, type_) -> list:
    return [e for e in traj if isinstance(e, type_)]


def test_subagent_call_emits_invoked_and_returned_with_paired_span_id() -> None:
    """The frame span_id on subagent_invoked MUST equal the span_id on
    subagent_returned. Consumers reconstruct nesting by following spans
    that descend from this one."""
    sa_driver = _StubSubagentDriver(text="all clear")
    cfg = Config(
        schema_version="0.1",
        run_id="r-1",
        prompt="kick it off",
        subagents=[Subagent(name="researcher", description="Looks things up.")],
    )
    scripted = [
        # Turn 1: parent calls subagent
        ModelResponse(
            tokens_input=10,
            tokens_output=5,
            cost_usd=0.0001,
            duration_ms=1,
            tool_calls=[ScriptedToolCall(call_id="c1", tool="researcher", input={"prompt": "go"})],
            converged=False,
        ),
        # Turn 2: parent converges after seeing subagent reply
        ModelResponse(
            tokens_input=20,
            tokens_output=5,
            cost_usd=0.0001,
            duration_ms=1,
            text="done",
            converged=True,
        ),
    ]
    runner = _run(cfg, scripted_model=scripted, driver=sa_driver)

    invoked = _by_type(runner.trajectory, SubagentInvokedEvent)
    returned = _by_type(runner.trajectory, SubagentReturnedEvent)
    assert len(invoked) == 1 and len(returned) == 1, "exactly one invoke/return pair"
    assert invoked[0].data.span_id == returned[0].data.span_id, "frame span_id MUST match"
    assert invoked[0].data.gen_ai_agent_name == "researcher"
    assert invoked[0].data.gen_ai_agent_description == "Looks things up."
    assert invoked[0].data.gen_ai_operation_name == "invoke_agent"
    assert invoked[0].data.aep_subagent_input == {"prompt": "go"}
    assert returned[0].data.aep_subagent_result_text == "all clear"
    assert returned[0].data.aep_subagent_reason == "converged"


def test_nested_events_chain_through_frame_span() -> None:
    """Events the driver emits via parent_observer MUST descend from the
    frame span (parent_span_id == frame_span_id, transitively). The
    trajectory is one tree."""
    sa_driver = _StubSubagentDriver()
    cfg = Config(
        schema_version="0.1",
        run_id="r-2",
        prompt="kick",
        subagents=[Subagent(name="r", description="r.")],
    )
    scripted = [
        ModelResponse(
            tokens_input=10,
            tokens_output=5,
            cost_usd=0.0001,
            duration_ms=1,
            tool_calls=[ScriptedToolCall(call_id="c1", tool="r", input={"prompt": "go"})],
            converged=False,
        ),
        ModelResponse(
            tokens_input=20,
            tokens_output=5,
            cost_usd=0.0001,
            duration_ms=1,
            text="done",
            converged=True,
        ),
    ]
    runner = _run(cfg, scripted_model=scripted, driver=sa_driver)

    invoked = _by_type(runner.trajectory, SubagentInvokedEvent)[0]
    frame_id = invoked.data.span_id

    # The driver emitted one ModelTurnStarted and ModelTurnEnded "inside"
    # the frame. Find them — they're the ones whose parent is the frame.
    nested_starts = [
        e
        for e in runner.trajectory
        if isinstance(e, ModelTurnStartedEvent) and e.data.parent_span_id == frame_id
    ]
    nested_ends = [
        e
        for e in runner.trajectory
        if isinstance(e, ModelTurnEndedEvent) and e.data.parent_span_id == frame_id
    ]
    assert len(nested_starts) == 1, "subagent's model_turn_started chains under frame"
    assert len(nested_ends) == 1, "subagent's model_turn_ended chains under frame"
    # The text emitted by the subagent chains through the turn span, which
    # chains through the frame.
    nested_text = [
        e
        for e in runner.trajectory
        if isinstance(e, TextEmittedEvent)
        and e.data.parent_span_id == nested_starts[0].data.span_id
    ]
    assert len(nested_text) == 1


def test_subagent_usage_rolls_up_into_parent_state() -> None:
    """The subagent's spend (cost, tokens) MUST be reflected in the
    parent's cumulative state. Otherwise the parent's boundary check
    can't see what the subagent consumed."""
    sa_driver = _StubSubagentDriver()
    cfg = Config(
        schema_version="0.1",
        run_id="r-3",
        prompt="kick",
        subagents=[Subagent(name="r", description="r.")],
    )
    scripted = [
        ModelResponse(
            tokens_input=10,
            tokens_output=5,
            cost_usd=0.001,
            duration_ms=1,
            tool_calls=[ScriptedToolCall(call_id="c1", tool="r", input={"prompt": "go"})],
            converged=False,
        ),
        ModelResponse(
            tokens_input=20,
            tokens_output=5,
            cost_usd=0.002,
            duration_ms=1,
            text="done",
            converged=True,
        ),
    ]
    runner = _run(cfg, scripted_model=scripted, driver=sa_driver)
    stopped = runner.trajectory[-1]
    snap = stopped.data.aep_state
    # Parent turns: 0.001 + 0.002 = 0.003. Subagent: 0.0001. Total: 0.0031.
    assert abs(snap.total_cost_usd - 0.0031) < 1e-9
    # Parent tokens: 10+5+20+5 = 40. Subagent: 50+25 = 75. Total: 115.
    assert snap.total_tokens == 115


def test_subagent_with_no_driver_emits_subagent_failed() -> None:
    """If subagents are declared but no SubagentDriver is wired in, a
    subagent invocation MUST surface as `subagent_failed` (not crash, not
    silently return). The model receives an `Error: ...` tool_result."""
    cfg = Config(
        schema_version="0.1",
        run_id="r-4",
        prompt="kick",
        subagents=[Subagent(name="r", description="r.")],
    )
    scripted = [
        ModelResponse(
            tokens_input=10,
            tokens_output=5,
            cost_usd=0.0001,
            duration_ms=1,
            tool_calls=[ScriptedToolCall(call_id="c1", tool="r", input={"prompt": "go"})],
            converged=False,
        ),
        ModelResponse(
            tokens_input=20,
            tokens_output=5,
            cost_usd=0.0001,
            duration_ms=1,
            text="proceeding without it",
            converged=True,
        ),
    ]
    runner = _run(cfg, scripted_model=scripted, driver=None)
    failures = _by_type(runner.trajectory, SubagentFailedEvent)
    assert len(failures) == 1
    assert "no SubagentDriver" in failures[0].data.aep_subagent_error
    assert failures[0].data.aep_subagent_error_code == "not_configured"
    # And no subagent_returned was emitted.
    assert not _by_type(runner.trajectory, SubagentReturnedEvent)


def test_subagent_collision_with_tool_name_aborts_run() -> None:
    """The model sees a single name → one resource. A subagent named the
    same as a Config tool would create ambiguity; the runner refuses to
    start with `error_occurred` + `agent_stopped(reason=error)`."""
    from aep import AgentStoppedEvent, ErrorOccurredEvent, Tool

    cfg = Config(
        schema_version="0.1",
        run_id="r-5",
        tools=[Tool(name="lookup", inputSchema={"type": "object", "properties": {}})],
        subagents=[Subagent(name="lookup", description="collides with tool name")],
        prompt="kick",
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel([]),  # never reached
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
        subagent_driver=_StubSubagentDriver(),
    )
    runner.run()
    errors = _by_type(runner.trajectory, ErrorOccurredEvent)
    stops = _by_type(runner.trajectory, AgentStoppedEvent)
    assert len(errors) == 1 and "collide" in errors[0].data.aep_error_message
    assert len(stops) == 1 and stops[0].data.aep_reason == "error"


def test_subagent_appears_in_agent_started_subagents_field() -> None:
    """The model's subagent surface is observable on the wire via
    `agent_started.data.subagents`. Consumers don't need to parse Config
    a second time to see what was offered."""
    from aep import AgentStartedEvent

    cfg = Config(
        schema_version="0.1",
        run_id="r-6",
        prompt="kick",
        subagents=[
            Subagent(
                name="planner",
                description="Decomposes work.",
                inputSchema={"type": "object", "properties": {"prompt": {"type": "string"}}},
            )
        ],
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0,
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        ),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
        subagent_driver=_StubSubagentDriver(),
    )
    runner.run()
    started = _by_type(runner.trajectory, AgentStartedEvent)[0]
    assert started.data.subagents and len(started.data.subagents) == 1
    assert started.data.subagents[0].name == "planner"
    assert started.data.subagents[0].description == "Decomposes work."


def test_allowed_tools_filters_subagent_names() -> None:
    """The model-facing allowlist applies to subagent names too — a
    subagent declared but not in allowed_tools is rejected at run start
    just like an unlisted tool would be."""
    from aep import ErrorOccurredEvent

    cfg = Config(
        schema_version="0.1",
        run_id="r-7",
        prompt="kick",
        subagents=[Subagent(name="excluded", description="should not be reachable")],
        allowed_tools=["bash"],  # no `excluded`
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel([]),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
        subagent_driver=_StubSubagentDriver(),
    )
    runner.run()
    errors = _by_type(runner.trajectory, ErrorOccurredEvent)
    assert len(errors) == 1
    assert "excluded" in errors[0].data.aep_error_message
