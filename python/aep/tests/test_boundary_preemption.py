"""Boundary preemption observability.

When the model emits multiple tool_use blocks in one assistant turn AND
the boundary trips after one of those tools completes, the remaining
tools were previously silently skipped — the trajectory showed the tool
that pushed us over budget and then `agent_stopped`, with no record that
the agent had also wanted to call tools N+1, N+2, ...

This file pins the fix: every pre-empted tool emits a `tool_failed` event
with `aep.tool.error="boundary preempted: <reason>"` BEFORE the
`agent_stopped` event. Now the wire is the source of truth for "what did
the agent want to do but couldn't" — no need to diff assistant-history
against the events list.

Why it matters for the supervisor: cross-run analytics ("show me runs
where the agent was prevented from calling deploy") need the prevented
calls in the events table. Without these tool_failed events, that query
returns wrong answers.

Test mechanics: in the v0.1 runner, the per-tool consumption check only
trips via `max_duration_seconds` (token / cost increments happen at
turn granularity, not per-tool). Rather than wiring up duration
manipulation, we monkey-patch `check_consumption` to return stop=True
after the first per-tool invocation. That exercises the preemption path
without relying on wall-clock timing in the test.
"""

from __future__ import annotations

from aep import Config, StopReason
from aep.runner.drivers import ModelResponse, ScriptedToolCall
from aep.runner.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from aep.runner.runner import AEPRunner
from aep.types import (
    AgentStoppedEvent,
    ToolFailedEvent,
    ToolReturnedEvent,
)


def _by_type(traj, type_):
    return [e for e in traj if isinstance(e, type_)]


def _multi_tool_response() -> ModelResponse:
    """Single assistant turn that calls FOUR tools. With a patched
    consumption check that trips on the second per-tool call, tools 3
    and 4 are pre-empted."""
    return ModelResponse(
        tokens_input=10,
        tokens_output=5,
        cost_usd=0.0001,  # well under any budget — turn-level check passes
        duration_ms=1,
        tool_calls=[
            ScriptedToolCall(call_id="c1", tool="step1", input={}),
            ScriptedToolCall(call_id="c2", tool="step2", input={}),
            ScriptedToolCall(call_id="c3", tool="step3", input={}),
            ScriptedToolCall(call_id="c4", tool="step4", input={}),
        ],
        converged=False,
    )


def _runner() -> AEPRunner:
    cfg = Config(
        schema_version="0.1",
        run_id="boundary-preempt",
        model="test/mock",
    )
    return AEPRunner(
        config=cfg,
        model=ScriptedModel([_multi_tool_response()]),
        tools=ScriptedTools(
            {
                "step1": {"output": "ok1"},
                "step2": {"output": "ok2"},
                "step3": {"output": "ok3"},
                "step4": {"output": "ok4"},
            }
        ),
        supervisor=ScriptedSupervisor(),
    )


def _patch_consumption_to_trip_after_n_per_tool_checks(monkeypatch, n: int):
    """Patch `check_consumption` so the first `n` calls return stop=False
    (turn-level + first n-1 per-tool checks) and subsequent calls return
    stop=True with budget_exhausted. Lets us pin the preemption path
    without depending on real wall-clock duration."""
    import aep.runner.runner as runner_mod

    real = runner_mod.check_consumption
    counter = {"calls": 0}

    from aep.runner.boundary import BoundaryDecision

    def patched(state, boundary):
        counter["calls"] += 1
        if counter["calls"] <= n:
            return real(state, boundary)
        return BoundaryDecision(stop=True, reason=StopReason.budget_exhausted)

    monkeypatch.setattr(runner_mod, "check_consumption", patched)


def test_remaining_tools_emit_tool_failed_with_boundary_reason(monkeypatch) -> None:
    """The fix: tools 3 and 4 are surfaced on the wire as tool_failed
    events with `aep.tool.error` naming the boundary reason. Without this,
    those calls were invisible to consumers reading the events table.
    Patched consumption: first call (turn-level) and first per-tool
    (after c1) pass; the check after c2 trips."""
    _patch_consumption_to_trip_after_n_per_tool_checks(monkeypatch, n=2)
    runner = _runner()
    runner.run()

    failed = _by_type(runner.trajectory, ToolFailedEvent)
    failed_call_ids = {f.data.gen_ai_tool_call_id for f in failed}
    assert "c3" in failed_call_ids
    assert "c4" in failed_call_ids
    for f in failed:
        if f.data.gen_ai_tool_call_id in {"c3", "c4"}:
            assert "boundary preempted" in f.data.aep_tool_error
            assert "budget_exhausted" in f.data.aep_tool_error


def test_preemption_events_fire_before_agent_stopped(monkeypatch) -> None:
    """Wire ordering: boundary-preempted tool_failed events MUST come
    before agent_stopped, so a consumer streaming events sees the full
    picture before the run terminator."""
    _patch_consumption_to_trip_after_n_per_tool_checks(monkeypatch, n=2)
    runner = _runner()
    runner.run()
    types = [type(e).__name__ for e in runner.trajectory]
    last_failed_idx = max(
        (i for i, t in enumerate(types) if t == "ToolFailedEvent"),
        default=-1,
    )
    stopped_idx = types.index("AgentStoppedEvent")
    assert last_failed_idx >= 0
    assert last_failed_idx < stopped_idx


def test_run_terminates_with_budget_reason_not_tool_failure(monkeypatch) -> None:
    """The fix MUST NOT change the termination reason — the run still
    stops with the boundary's reason, not a tool-failure-cascade reason."""
    _patch_consumption_to_trip_after_n_per_tool_checks(monkeypatch, n=2)
    runner = _runner()
    runner.run()
    stopped = _by_type(runner.trajectory, AgentStoppedEvent)[-1]
    assert stopped.data.aep_reason == StopReason.budget_exhausted


def test_tools_that_completed_before_preemption_still_visible(monkeypatch) -> None:
    """Backwards-compat: tools 1 and 2 (the ones that ran before the
    boundary tripped) MUST still emit tool_returned. We didn't accidentally
    swap them into the failed bucket."""
    _patch_consumption_to_trip_after_n_per_tool_checks(monkeypatch, n=2)
    runner = _runner()
    runner.run()
    returned = _by_type(runner.trajectory, ToolReturnedEvent)
    returned_call_ids = {r.data.gen_ai_tool_call_id for r in returned}
    assert "c1" in returned_call_ids
    assert "c2" in returned_call_ids
    # And NOT c3/c4 (those were pre-empted and emit tool_failed instead).
    assert "c3" not in returned_call_ids
    assert "c4" not in returned_call_ids


def test_no_preemption_when_no_boundary_trips() -> None:
    """Regression: when the boundary doesn't trip, no preemption events
    fire — only the normal tool_returned for each call. Pins that the
    fix doesn't accidentally emit phantom tool_failed events on
    happy-path runs."""
    cfg = Config(schema_version="0.1", run_id="happy", model="test/mock")
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel(
            [
                _multi_tool_response(),
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="done",
                    converged=True,
                ),
            ]
        ),
        tools=ScriptedTools(
            {
                "step1": {"output": "ok1"},
                "step2": {"output": "ok2"},
                "step3": {"output": "ok3"},
                "step4": {"output": "ok4"},
            }
        ),
        supervisor=ScriptedSupervisor(),
    )
    runner.run()
    returned = _by_type(runner.trajectory, ToolReturnedEvent)
    assert {r.data.gen_ai_tool_call_id for r in returned} == {"c1", "c2", "c3", "c4"}
    failed = _by_type(runner.trajectory, ToolFailedEvent)
    assert failed == []


def test_first_tool_preempted_emits_failures_for_all_remaining(monkeypatch) -> None:
    """Edge case: boundary trips immediately after tool 1 completes.
    Tools 2, 3, 4 should ALL appear as boundary-preempted tool_failed."""
    _patch_consumption_to_trip_after_n_per_tool_checks(monkeypatch, n=1)
    runner = _runner()
    runner.run()
    failed = _by_type(runner.trajectory, ToolFailedEvent)
    failed_call_ids = {f.data.gen_ai_tool_call_id for f in failed}
    assert failed_call_ids == {"c2", "c3", "c4"}
