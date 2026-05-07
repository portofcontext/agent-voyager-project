"""Tests for approval-source verifiers — the human-in-the-loop gate.

An approval-source verifier defers the pass/fail decision to the
supervisor via an `aep.approval_requested` / `aep.approval_resolved`
RPC pair. Used at `pre_tool:<name>` triggers for "ask before deploy"
patterns.

Coverage:
  - Approved → tool dispatches as if no gate were present
  - Denied → tool does NOT dispatch; on_failure action applies
  - Timeout → treated as a denial; aep.verifier.error = source_timed_out
  - Wire shape: approval_requested carries the verifier name + tool
    context; approval_resolved is recorded into the trajectory verbatim
  - Span tree: the runner re-stamps the supervisor's reply so the run
    has one consistent trace
"""

from __future__ import annotations

from typing import Any

from aep import (
    ApprovalRequestedEvent,
    ApprovalResolvedEvent,
    Config,
    StopReason,
    ToolFailedEvent,
    ToolReturnedEvent,
    Verifier,
    VerifierEvaluatedEvent,
)
from aep.runner import AEPRunner
from aep.runner.drivers import ModelResponse, ScriptedToolCall
from aep.runner.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools


def _resp_calling(tool: str, *, call_id: str = "c1") -> ModelResponse:
    return ModelResponse(
        tokens_input=10,
        tokens_output=5,
        cost_usd=0.0001,
        duration_ms=1,
        tool_calls=[ScriptedToolCall(call_id=call_id, tool=tool, input={"target": "prod"})],
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


def _approval_step(*, run_id: str, approved: bool, reason: str | None = None) -> dict[str, Any]:
    """Build a ScriptedSupervisor step that responds to any approval_requested
    event with the given decision. The supervisor matches on the request,
    extracts the approval_id via the substitute placeholder, and replies."""
    send_data: dict[str, Any] = {
        "trace_id": "0" * 32,  # runner re-stamps with its own trace_id
        "span_id": "0" * 16,
        "parent_span_id": "0" * 16,
        "aep.approval.id": "{{event.data.aep.approval.id}}",
        "aep.approval.approved": approved,
    }
    if reason:
        send_data["aep.approval.reason"] = reason
    return {
        "on": {"match": {"type": "aep.approval_requested"}},
        "send": {
            "specversion": "1.0",
            "id": "{{event.id}}-resolved",
            "source": "aep://supervisor",
            "type": "aep.approval_resolved",
            "subject": run_id,
            "time": "{{now}}",
            "datacontenttype": "application/json",
            "data": send_data,
        },
    }


def _build_runner(
    *,
    run_id: str,
    on_failure: str,
    approval_step: dict[str, Any] | None,
) -> AEPRunner:
    """Helper: scripted parent that calls `deploy` once, then says DONE.

    Deploy is registered as a LOCAL tool (via ScriptedTools) so we
    aren't waiting for tool_exec_resolved on the approved-path tests.
    The approval gate fires regardless of dispatch_target — pre_tool
    is name-keyed.
    """
    cfg = Config(
        schema_version="0.1",
        run_id=run_id,
        verifiers=[
            Verifier(
                name="ask-before-deploy",
                trigger="pre_tool:deploy",
                source={"approval": {"prompt": "Deploy to prod?"}},
                on_failure=on_failure,
                correction_message=(
                    "Deploy denied — pick a less destructive action."
                    if on_failure == "inject_correction"
                    else None
                ),
                timeout_ms=5000,
            )
        ],
        model="test/mock",
    )
    return AEPRunner(
        config=cfg,
        model=ScriptedModel([_resp_calling("deploy"), _resp_text()]),
        tools=ScriptedTools({"deploy": {"output": "deployed"}}),
        supervisor=ScriptedSupervisor([approval_step] if approval_step else []),
    )


# ── Approved → tool dispatches ─────────────────────────────────────────────


def test_approved_lets_tool_dispatch() -> None:
    """When the supervisor approves, the verifier passes and the tool
    runs as if no gate were present. The tool ends up emitting
    tool_exec_request (because it's a Config.tools entry, not local) —
    we check the verifier outcome and the wire shape."""
    runner = _build_runner(
        run_id="approve-deploy",
        on_failure="halt",
        approval_step=_approval_step(
            run_id="approve-deploy", approved=True, reason="approved by alice"
        ),
    )
    runner.run()

    # The verifier_evaluated event records passed=True.
    verifiers = _by_type(runner.trajectory, VerifierEvaluatedEvent)
    assert len(verifiers) == 1
    assert verifiers[0].data.aep_verifier_passed
    assert verifiers[0].data.aep_verifier_name == "ask-before-deploy"
    # And both approval lifecycle events are present.
    assert _by_type(runner.trajectory, ApprovalRequestedEvent)
    assert _by_type(runner.trajectory, ApprovalResolvedEvent)


def test_approved_wire_shape_carries_tool_context() -> None:
    """approval_requested MUST carry the tool name + call_id +
    arguments so the supervisor's UI / policy engine can decide
    based on what's actually being approved."""
    runner = _build_runner(
        run_id="wire-shape",
        on_failure="halt",
        approval_step=_approval_step(run_id="wire-shape", approved=True),
    )
    runner.run()
    requested = _by_type(runner.trajectory, ApprovalRequestedEvent)[0]
    assert requested.data.gen_ai_tool_name == "deploy"
    assert requested.data.gen_ai_tool_call_id == "c1"
    assert requested.data.gen_ai_tool_call_arguments == {"target": "prod"}
    assert requested.data.aep_verifier_name == "ask-before-deploy"
    assert requested.data.aep_approval_prompt == "Deploy to prod?"


# ── Denied → tool does not dispatch ────────────────────────────────────────


def test_denied_with_halt_terminates_run() -> None:
    """on_failure: halt — the tool doesn't run and the run terminates
    with verifier_failed."""
    runner = _build_runner(
        run_id="deny-halt",
        on_failure="halt",
        approval_step=_approval_step(run_id="deny-halt", approved=False, reason="not approved"),
    )
    stopped = runner.run()
    assert stopped.data.aep_reason == StopReason.verifier_failed
    # Tool never ran.
    assert not _by_type(runner.trajectory, ToolReturnedEvent)


def test_denied_with_continue_skips_tool_and_run_proceeds() -> None:
    """on_failure: continue — the tool is rejected (model sees
    tool_failed), but the run continues. The model can try a different
    approach next turn."""
    runner = _build_runner(
        run_id="deny-continue",
        on_failure="continue",
        approval_step=_approval_step(run_id="deny-continue", approved=False),
    )
    stopped = runner.run()
    # Run converged via the second scripted turn.
    assert stopped.data.aep_reason == StopReason.converged
    # Tool was rejected — tool_failed emitted, tool_returned wasn't.
    failed = _by_type(runner.trajectory, ToolFailedEvent)
    assert failed and "pre_tool verifier" in failed[0].data.aep_tool_error


def test_denied_with_inject_correction_pushes_correction() -> None:
    """on_failure: inject_correction — the tool is rejected AND the
    correction message lands in history so the model's next turn
    knows what to do instead."""
    runner = _build_runner(
        run_id="deny-correct",
        on_failure="inject_correction",
        approval_step=_approval_step(run_id="deny-correct", approved=False),
    )
    runner.run()
    user_messages = [m for m in runner._history if m.get("role") == "user"]
    correction = next((m for m in user_messages if m.get("kind") == "correction"), None)
    assert correction is not None
    assert "less destructive" in correction["content"]


# ── Timeout → treated as denial ────────────────────────────────────────────


def test_timeout_treated_as_denial_with_source_timed_out() -> None:
    """When the supervisor doesn't respond within the verifier's
    timeout, the verifier records `aep.verifier.error: source_timed_out`
    so consumers can distinguish 'supervisor said no' from 'supervisor
    went away'. Stop reason follows on_failure (halt → verifier_failed)."""
    # No supervisor step → the request has no matching response → timeout.
    runner = _build_runner(
        run_id="timeout",
        on_failure="halt",
        approval_step={
            "on": {"match": {"type": "aep.approval_requested"}},
            "skip": True,  # explicit no-reply
        },
    )
    # Use a tiny timeout to keep the test fast.
    runner.config.verifiers[0].timeout_ms = 50
    stopped = runner.run()
    assert stopped.data.aep_reason == StopReason.verifier_failed
    verifiers = _by_type(runner.trajectory, VerifierEvaluatedEvent)
    assert len(verifiers) == 1
    assert not verifiers[0].data.aep_verifier_passed
    assert verifiers[0].data.aep_verifier_error == "source_timed_out"


# ── Span tree consistency ──────────────────────────────────────────────────


def test_supervisor_reply_is_re_stamped_with_runner_trace_context() -> None:
    """The supervisor doesn't know the runner's trace_id. The runner
    re-stamps the recorded approval_resolved with its own trace_id /
    span_id so the trajectory stays one tree (same convention as
    tool_exec_resolved)."""
    runner = _build_runner(
        run_id="span-stamp",
        on_failure="halt",
        approval_step=_approval_step(run_id="span-stamp", approved=True),
    )
    runner.run()
    requested = _by_type(runner.trajectory, ApprovalRequestedEvent)[0]
    resolved = _by_type(runner.trajectory, ApprovalResolvedEvent)[0]
    # Same trace_id (runner's), and the resolved event's span matches the
    # request's span (paired RPC, like tool_exec_*).
    assert requested.data.trace_id == resolved.data.trace_id
    assert requested.data.span_id == resolved.data.span_id
    # The original "0...0" placeholder span the test used in the scripted
    # supervisor was overwritten by the runner.
    assert resolved.data.trace_id != "0" * 32
