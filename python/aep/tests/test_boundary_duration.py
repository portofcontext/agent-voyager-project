"""Unit tests for `Boundary.max_duration_seconds`.

Lives outside the conformance harness because the harness's scripted
models report their own `duration_ms` (a per-call number) but the
boundary check reads `state.duration_ms` from the run's monotonic
clock — wall-clock spend, not summed scripted time. So the only way
to exercise the boundary deterministically is with real time.

The tests here use a tiny budget (50 ms) plus a model driver that
sleeps long enough to cross it, so the check fires after at most
one turn. Slow vs in-memory tests but still well under a second.
"""

from __future__ import annotations

import time

from aep import Config, StopReason
from aep.runner import AEPRunner
from aep.runner.drivers import ModelDriver, ModelResponse
from aep.runner.mock import ScriptedSupervisor, ScriptedTools


class _SleepyModel(ModelDriver):
    """Model driver that sleeps before each turn so the run's wall-clock
    duration crosses the boundary. Returns scripted responses."""

    def __init__(self, sleep_s: float, responses: list[ModelResponse]) -> None:
        self._sleep_s = sleep_s
        self._responses = list(responses)
        self._idx = 0

    def step(self, history: list[dict]) -> ModelResponse:
        time.sleep(self._sleep_s)
        if self._idx >= len(self._responses):
            raise RuntimeError("scripted model exhausted")
        r = self._responses[self._idx]
        self._idx += 1
        return r


def _resp(text: str = "ok", *, converged: bool = False) -> ModelResponse:
    return ModelResponse(
        tokens_input=1,
        tokens_output=1,
        cost_usd=0.0001,
        duration_ms=1,
        text=text,
        converged=converged,
    )


def test_max_duration_seconds_halts_after_threshold() -> None:
    """Boundary fires when wall-clock exceeds the cap. Strict-greater per
    SPEC §9.2 — same algorithm as cost / tokens, just measured in seconds."""
    cfg = Config(
        schema_version="0.1",
        run_id="duration-cap",
        boundary={"max_duration_seconds": 0.05},  # 50 ms
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        # Each turn sleeps ~80 ms; the first turn alone crosses the 50ms cap.
        model=_SleepyModel(0.08, [_resp(), _resp(), _resp()]),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )
    stopped = runner.run()
    assert stopped.data.aep_reason == StopReason.duration_limit
    # Strict-greater: the run was allowed to complete the turn that crossed
    # the cap (one final overshoot) before halting — same rule as cost/tokens.
    assert stopped.data.aep_state.total_turns == 1


def test_max_duration_seconds_does_not_fire_when_run_finishes_in_time() -> None:
    """Sanity check: a run that converges within the budget terminates
    naturally (reason=converged), not from the duration boundary."""
    cfg = Config(
        schema_version="0.1",
        run_id="duration-cap-not-hit",
        boundary={"max_duration_seconds": 5.0},  # 5 seconds — well above test runtime
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        model=_SleepyModel(0.001, [_resp(text="done", converged=True)]),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )
    stopped = runner.run()
    assert stopped.data.aep_reason == StopReason.converged


def test_max_duration_seconds_independent_of_other_boundaries() -> None:
    """Duration is its own boundary — it fires even if cost / tokens / steps
    are well under their caps."""
    cfg = Config(
        schema_version="0.1",
        run_id="duration-only",
        boundary={
            "max_cost_usd": 100.0,  # huge — won't fire
            "max_tokens": 1_000_000,  # huge — won't fire
            "max_steps": 100,  # huge — won't fire
            "max_duration_seconds": 0.05,  # tight
        },
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        model=_SleepyModel(0.08, [_resp(), _resp(), _resp()]),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )
    stopped = runner.run()
    assert stopped.data.aep_reason == StopReason.duration_limit
