"""Tests for the `pre_tool:<name>` verifier trigger.

`pre_tool:<name>` fires BEFORE the named tool dispatches and gates
whether the tool runs. Use cases:
  - "Run smoke tests before any deploy."
  - "Confirm the workspace is clean before any write_file."
  - (with the approval source — phase 3b) "Ask a human before this tool."

These tests cover the shell-source path. Approval-source tests live in
`test_approval_source.py` once the approval RPC is in place.
"""

from __future__ import annotations

from aep import (
    Config,
    StopReason,
    Tool,
    ToolFailedEvent,
    ToolReturnedEvent,
    Verifier,
    VerifierEvaluatedEvent,
    VerifierSourceShell,
)
from aep.runner import AEPRunner
from aep.runner.drivers import ModelResponse, ScriptedToolCall
from aep.runner.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools


def _resp_calling(tool: str, *, call_id: str = "c1", input: dict | None = None) -> ModelResponse:
    return ModelResponse(
        tokens_input=10,
        tokens_output=5,
        cost_usd=0.0001,
        duration_ms=1,
        tool_calls=[ScriptedToolCall(call_id=call_id, tool=tool, input=input or {})],
        converged=False,
    )


def _resp_text(text: str = "ok", *, converged: bool = True) -> ModelResponse:
    return ModelResponse(
        tokens_input=5,
        tokens_output=3,
        cost_usd=0.0001,
        duration_ms=1,
        text=text,
        converged=converged,
    )


def _by_type(traj, type_):
    return [e for e in traj if isinstance(e, type_)]


def test_pre_tool_verifier_passes_then_tool_dispatches() -> None:
    """When the pre_tool verifier passes, the tool runs normally — same
    trajectory as if no pre_tool gate existed."""
    cfg = Config(
        schema_version="0.1",
        run_id="pre-tool-pass",
        verifiers=[
            Verifier(
                name="always-passes",
                trigger="pre_tool:bash",
                source=VerifierSourceShell(shell="true"),
                on_failure="halt",
            )
        ],
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel([_resp_calling("bash"), _resp_text()]),
        tools=ScriptedTools({"bash": {"output": "ran"}}),
        supervisor=ScriptedSupervisor(),
    )
    runner.run()
    # Verifier ran (passed=True), tool ran successfully.
    verifiers = _by_type(runner.trajectory, VerifierEvaluatedEvent)
    assert len(verifiers) == 1 and verifiers[0].data.aep_verifier_passed
    assert _by_type(runner.trajectory, ToolReturnedEvent), "tool should have dispatched"
    assert not _by_type(runner.trajectory, ToolFailedEvent)


def test_pre_tool_verifier_fails_with_halt_terminates_run() -> None:
    """When the pre_tool verifier fails with on_failure=halt, the tool
    does NOT run and the run terminates with reason=verifier_failed.
    The trajectory still records `tool_invoked` (the agent attempted
    the call) so consumers see the rejection chain."""
    cfg = Config(
        schema_version="0.1",
        run_id="pre-tool-halt",
        verifiers=[
            Verifier(
                name="block-deploy",
                trigger="pre_tool:deploy",
                source=VerifierSourceShell(shell="false"),  # always fails
                on_failure="halt",
            )
        ],
        tools=[Tool(name="deploy", inputSchema={"type": "object", "properties": {}})],
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel([_resp_calling("deploy")]),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )
    stopped = runner.run()
    assert stopped.data.aep_reason == StopReason.verifier_failed
    # No tool_returned (tool never ran), no tool_invoked either (we
    # halted before the dispatch path).
    assert not _by_type(runner.trajectory, ToolReturnedEvent)


def test_pre_tool_verifier_fails_with_continue_emits_tool_failed() -> None:
    """on_failure=continue means: the tool doesn't run, but the run
    continues. The model receives `tool_failed` with the verifier's
    reason so its next turn knows what happened."""
    cfg = Config(
        schema_version="0.1",
        run_id="pre-tool-continue",
        verifiers=[
            Verifier(
                name="advisory-block",
                trigger="pre_tool:bash",
                source=VerifierSourceShell(shell="false"),
                on_failure="continue",
            )
        ],
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel([_resp_calling("bash"), _resp_text()]),
        tools=ScriptedTools({"bash": {"output": "should not run"}}),
        supervisor=ScriptedSupervisor(),
    )
    stopped = runner.run()
    # tool_failed emitted, tool_returned NOT emitted, run converges naturally.
    assert _by_type(runner.trajectory, ToolFailedEvent)
    assert not _by_type(runner.trajectory, ToolReturnedEvent)
    assert stopped.data.aep_reason == StopReason.converged
    failed = _by_type(runner.trajectory, ToolFailedEvent)[0]
    assert "pre_tool verifier" in failed.data.aep_tool_error


def test_pre_tool_verifier_fails_with_inject_correction_skips_tool_and_corrects() -> None:
    """on_failure=inject_correction: the tool is rejected (model sees
    tool_failed) AND the correction message is appended to history so
    the model's NEXT turn sees the correction. This is the "your last
    move was wrong, here's what to do instead" pattern."""
    cfg = Config(
        schema_version="0.1",
        run_id="pre-tool-correct",
        verifiers=[
            Verifier(
                name="redirect",
                trigger="pre_tool:write_file",
                source=VerifierSourceShell(shell="false"),
                on_failure="inject_correction",
                correction_message="Don't write to that path; use the build/ directory instead.",
            )
        ],
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel(
            [
                _resp_calling("write_file"),
                _resp_text(text="ok will use build/", converged=True),
            ]
        ),
        tools=ScriptedTools({"write_file": {"output": "should not run"}}),
        supervisor=ScriptedSupervisor(),
    )
    runner.run()
    assert _by_type(runner.trajectory, ToolFailedEvent)
    # The correction landed in history before the second turn.
    user_messages = [m for m in runner._history if m.get("role") == "user"]
    correction = next((m for m in user_messages if m.get("kind") == "correction"), None)
    assert correction is not None
    assert "build/" in correction["content"]


def test_pre_tool_verifier_only_runs_for_matching_tool() -> None:
    """`pre_tool:bash` does NOT fire for `write_file` — the trigger is
    name-scoped."""
    cfg = Config(
        schema_version="0.1",
        run_id="pre-tool-scoped",
        verifiers=[
            Verifier(
                name="bash-gate",
                trigger="pre_tool:bash",
                source=VerifierSourceShell(shell="false"),
                on_failure="halt",
            )
        ],
        model="test/mock",
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel([_resp_calling("write_file"), _resp_text()]),
        tools=ScriptedTools({"write_file": {"output": "ok"}}),
        supervisor=ScriptedSupervisor(),
    )
    runner.run()
    # No verifier fired — write_file isn't covered.
    assert not _by_type(runner.trajectory, VerifierEvaluatedEvent)
    assert _by_type(runner.trajectory, ToolReturnedEvent)


def test_pre_tool_trigger_validates_at_config_construction() -> None:
    """`pre_tool:<name>` must be syntactically valid at Pydantic
    validation time, like `on_tool:<name>` is."""
    import pytest
    from pydantic import ValidationError

    # Valid: passes
    Verifier(
        name="ok",
        trigger="pre_tool:deploy",
        source=VerifierSourceShell(shell="true"),
    )
    # Invalid: empty tool name
    with pytest.raises(ValidationError):
        Verifier(
            name="bad",
            trigger="pre_tool:",
            source=VerifierSourceShell(shell="true"),
        )
    # Invalid: nonsense trigger
    with pytest.raises(ValidationError):
        Verifier(
            name="bad",
            trigger="random",
            source=VerifierSourceShell(shell="true"),
        )
