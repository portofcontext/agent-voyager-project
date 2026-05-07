"""Tests for `Verifier.on_success` — declarative convergence.

A verifier with `on_success: halt` halts the run with `reason=converged`
when its check passes (the agent achieved the declared goal). Mirror of
`on_failure: halt` which halts with `reason=verifier_failed` (the agent
broke an invariant). Both polarities use the same trigger / source /
shell-execution machinery.

The motivating use case: "stop when the output file exists" or "stop
when all tests pass". Today these are expressible as inverse-polarity
verifiers — without on_success, you'd write a verifier that fails when
the file exists, which is awkward and reads badly.
"""

from __future__ import annotations

import os
import tempfile

from aep import (
    Config,
    StopReason,
    Verifier,
    VerifierEvaluatedEvent,
    VerifierSourceShell,
)
from aep.runner import AEPRunner
from aep.runner.drivers import ModelResponse
from aep.runner.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools


def _resp(text: str = "ok", *, converged: bool = False) -> ModelResponse:
    return ModelResponse(
        tokens_input=10,
        tokens_output=5,
        cost_usd=0.0001,
        duration_ms=1,
        text=text,
        converged=converged,
    )


def _by_type(traj, type_):
    return [e for e in traj if isinstance(e, type_)]


def test_on_success_halt_stops_with_reason_converged() -> None:
    """A verifier whose check passes AND has on_success=halt terminates
    the run. Stop reason is `converged` — the agent achieved the goal —
    not `verifier_failed`."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        marker = f.name
    try:
        cfg = Config(
            schema_version="0.1",
            run_id="convergence",
            verifiers=[
                # Always passes: shell `true`. With on_success=halt, the
                # first turn after which this fires terminates the run.
                Verifier(
                    name="goal-met",
                    trigger="after_each_turn",
                    source=VerifierSourceShell(shell=f"test -f {marker}"),
                    on_success=OnFailure_halt(),
                    on_failure="continue",
                ),
            ],
            model="test/mock",
        )
        runner = AEPRunner(
            config=cfg,
            model=ScriptedModel(
                [
                    _resp(text="t1"),
                    _resp(text="t2"),
                    _resp(text="t3"),
                ]
            ),
            tools=ScriptedTools(),
            supervisor=ScriptedSupervisor(),
        )
        # File doesn't exist yet → verifier fails → continue. Run all turns.
        # ... actually for this test, easier to make the file exist from the
        # start and assert the FIRST turn already triggers the halt.
        open(marker, "w").close()
        stopped = runner.run()
        assert stopped.data.aep_reason == StopReason.converged, (
            f"expected converged, got {stopped.data.aep_reason}"
        )
        # Exactly one turn — verifier fired after turn 1 and halted.
        assert stopped.data.aep_state.total_turns == 1
        # And the verifier_evaluated event shows it passed.
        verifiers = _by_type(runner.trajectory, VerifierEvaluatedEvent)
        assert len(verifiers) == 1 and verifiers[0].data.aep_verifier_passed
    finally:
        for p in (marker,):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass


def OnFailure_halt():
    """Test helper: returns the OnFailure.halt enum value as a string
    (Pydantic accepts either)."""
    return "halt"


def test_on_failure_halt_unchanged_still_yields_verifier_failed() -> None:
    """Backwards-compat: on_failure=halt still terminates with
    verifier_failed. The polarity differentiator is which side fired."""
    cfg = Config(
        schema_version="0.1",
        run_id="invariant-broken",
        verifiers=[
            Verifier(
                name="bad-rule",
                trigger="after_each_turn",
                source=VerifierSourceShell(shell="false"),  # always fails
                on_failure="halt",
            )
        ],
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel([_resp(), _resp()]),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )
    stopped = runner.run()
    assert stopped.data.aep_reason == StopReason.verifier_failed


def test_on_success_continue_is_default_so_no_halt_when_passing() -> None:
    """A verifier with no on_success specified defaults to `continue` —
    passing is just observed, not a stop signal. Existing behavior."""
    cfg = Config(
        schema_version="0.1",
        run_id="passing-verifier",
        verifiers=[
            Verifier(
                name="always-passes",
                trigger="after_each_turn",
                source=VerifierSourceShell(shell="true"),
                # on_success defaults to continue
                on_failure="halt",
            )
        ],
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel(
            [
                _resp(text="t1"),
                _resp(text="t2", converged=True),
            ]
        ),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )
    stopped = runner.run()
    # Verifier passed both times; run converged naturally.
    assert stopped.data.aep_reason == StopReason.converged
    assert stopped.data.aep_state.total_turns == 2


def test_on_success_inject_correction_requires_correction_message() -> None:
    """Validation: setting on_success: inject_correction without
    correction_message raises (same rule as on_failure)."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="correction_message"):
        Verifier(
            name="bad",
            trigger="after_each_turn",
            source=VerifierSourceShell(shell="true"),
            on_success="inject_correction",
            # No correction_message — should fail
        )
