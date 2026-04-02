"""Tests for AEP stream validator."""

import pytest
from agent_execution_protocol import (
    AgentStart, AgentStop, ModelTurnStart, ModelTurnEnd,
    ToolCall, ToolResult, ToolCallFailed, TextOutput,
    CostUpdate, ContextCompaction, RunError,
    HookRequest, HookVerdictApplied,
    SkillRead, SkillExecute,
    validate, Violation,
)


def _start(run_id="r1"):
    return AgentStart(run_id=run_id, model="m")


def _stop(run_id="r1", reason="converged"):
    return AgentStop(run_id=run_id, reason=reason,
                     total_tokens=10, total_cost_usd=0.001,
                     total_turns=1, duration_ms=100)


def _minimal(run_id="r1"):
    return [_start(run_id), _stop(run_id)]


def _hook_req(request_id="hr-1", hook_name="h", trigger="on_stop", step=1):
    return HookRequest(run_id="r1", request_id=request_id, hook_name=hook_name,
                       trigger=trigger, step=step, timeout_ms=30000)


def _hook_applied(request_id="hr-1", verdict="continue"):
    return HookVerdictApplied(run_id="r1", request_id=request_id, verdict=verdict)


# ── Happy path ────────────────────────────────────────────────────────────────

def test_valid_minimal_stream():
    assert validate(_minimal()) == []


def test_valid_stream_with_tool_call():
    events = [
        _start(),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="bash", input={"cmd": "ls"}),
        ToolResult(run_id="r1", step=1, call_id="c1", tool="bash", output="file.txt", duration_ms=5),
        _stop(),
    ]
    assert validate(events) == []


def test_valid_stream_with_tool_call_failed():
    events = [
        _start(),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="bash", input={}),
        ToolCallFailed(run_id="r1", step=1, call_id="c1", tool="bash", error="timeout"),
        _stop(),
    ]
    assert validate(events) == []


def test_valid_stream_multiple_tool_calls():
    events = [
        _start(),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="bash", input={}),
        ToolCall(run_id="r1", step=1, call_id="c2", tool="bash", input={}),
        ToolResult(run_id="r1", step=1, call_id="c1", tool="bash", output="a", duration_ms=1),
        ToolResult(run_id="r1", step=1, call_id="c2", tool="bash", output="b", duration_ms=1),
        _stop(),
    ]
    assert validate(events) == []


# ── Hook happy paths ──────────────────────────────────────────────────────────

def test_valid_stream_with_hook_pair():
    events = [
        _start(),
        _hook_req("hr-1"),
        _hook_applied("hr-1", "continue"),
        _stop(),
    ]
    assert validate(events) == []


def test_valid_stream_with_hook_stop_verdict():
    events = [
        _start(),
        _hook_req("hr-1"),
        _hook_applied("hr-1", "stop"),
        _stop(reason="supervisor_stopped"),
    ]
    assert validate(events) == []


def test_valid_stream_with_hook_inject_verdict():
    events = [
        _start(),
        _hook_req("hr-1"),
        _hook_applied("hr-1", "inject"),
        _stop(),
    ]
    assert validate(events) == []


def test_valid_stream_with_multiple_hooks():
    events = [
        _start(),
        _hook_req("hr-1", trigger="on_start"),
        _hook_applied("hr-1", "continue"),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="write_file", input={}),
        ToolResult(run_id="r1", step=1, call_id="c1", tool="write_file", output="ok", duration_ms=5),
        _hook_req("hr-2", trigger="on_tool:write_file", step=1),
        _hook_applied("hr-2", "continue"),
        _stop(),
    ]
    assert validate(events) == []


def test_valid_stream_with_timed_out_hook():
    start = _start()
    start.ts = "2026-01-01T00:00:00Z"
    hr = _hook_req("hr-1")
    hr.ts = "2026-01-01T00:00:01Z"
    applied = HookVerdictApplied(run_id="r1", request_id="hr-1", verdict="continue", timed_out=True)
    applied.ts = "2026-01-01T00:00:02Z"
    stop = _stop()
    stop.ts = "2026-01-01T00:00:03Z"
    events = [start, hr, applied, stop]
    assert validate(events) == []


# ── Hook error cases ──────────────────────────────────────────────────────────

def test_unmatched_hook_verdict_applied():
    events = [
        _start(),
        _hook_applied("hr-99"),  # no matching hook_request
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "UNMATCHED_HOOK_VERDICT_APPLIED" in codes


def test_unclosed_hook_request():
    events = [
        _start(),
        _hook_req("hr-1"),  # never resolved
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "UNCLOSED_HOOK_REQUEST" in codes


def test_unclosed_hook_request_event_index():
    events = [_start(), _hook_req("hr-1"), _stop()]
    v = next(x for x in validate(events) if x.code == "UNCLOSED_HOOK_REQUEST")
    assert v.event_index == 1


def test_duplicate_hook_request_id():
    events = [
        _start(),
        _hook_req("hr-1"),
        _hook_req("hr-1"),   # same request_id
        _hook_applied("hr-1"),
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "DUPLICATE_HOOK_REQUEST_ID" in codes


def test_invalid_hook_verdict_value():
    applied = HookVerdictApplied(run_id="r1", request_id="hr-1", verdict="maybe")
    events = [_start(), _hook_req("hr-1"), applied, _stop()]
    codes = [v.code for v in validate(events)]
    assert "INVALID_HOOK_VERDICT" in codes


@pytest.mark.parametrize("verdict", ["continue", "stop", "inject"])
def test_valid_hook_verdict_values(verdict):
    events = [_start(), _hook_req("hr-1"), _hook_applied("hr-1", verdict), _stop()]
    codes = [v.code for v in validate(events)]
    assert "INVALID_HOOK_VERDICT" not in codes


def test_multiple_unclosed_hook_requests():
    events = [
        _start(),
        _hook_req("hr-1"),
        _hook_req("hr-2"),
        # neither resolved
        _stop(),
    ]
    violations = [v for v in validate(events) if v.code == "UNCLOSED_HOOK_REQUEST"]
    assert len(violations) == 2


def test_hook_request_resolved_does_not_produce_unclosed():
    events = [
        _start(),
        _hook_req("hr-1"),
        _hook_applied("hr-1"),
        _hook_req("hr-2"),
        _hook_applied("hr-2"),
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "UNCLOSED_HOOK_REQUEST" not in codes
    assert "UNMATCHED_HOOK_VERDICT_APPLIED" not in codes


def test_hook_verdict_applied_before_request_is_unmatched():
    """Verdict applied before the request was emitted."""
    events = [
        _start(),
        _hook_applied("hr-1"),  # no prior hook_request
        _hook_req("hr-1"),
        _hook_applied("hr-1"),  # second applied — first was unmatched, second resolves the request
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "UNMATCHED_HOOK_VERDICT_APPLIED" in codes


# ── Skill events ──────────────────────────────────────────────────────────────

def test_skill_read_passes_validation():
    events = [
        _start(),
        SkillRead(run_id="r1", step=1, name="pdf-processing"),
        _stop(),
    ]
    assert validate(events) == []


def test_skill_execute_passes_validation():
    events = [
        _start(),
        SkillExecute(run_id="r1", step=1, name="pdf-processing"),
        _stop(),
    ]
    assert validate(events) == []


def test_skill_read_then_execute_passes_validation():
    events = [
        _start(),
        SkillRead(run_id="r1", step=1, name="code-review"),
        SkillExecute(run_id="r1", step=1, name="code-review"),
        _stop(),
    ]
    assert validate(events) == []


def test_skill_events_run_id_mismatch_caught():
    events = [
        _start("r1"),
        SkillRead(run_id="r2", step=1, name="my-skill"),
        _stop("r1"),
    ]
    codes = [v.code for v in validate(events)]
    assert "RUN_ID_MISMATCH" in codes


# ── Stop reasons ──────────────────────────────────────────────────────────────

def test_supervisor_stopped_is_valid_stop_reason():
    events = [_start(), _stop(reason="supervisor_stopped")]
    codes = [v.code for v in validate(events)]
    assert "INVALID_STOP_REASON" not in codes


def test_invalid_stop_reason():
    events = [_start(), _stop(reason="finished_maybe")]
    codes = [v.code for v in validate(events)]
    assert "INVALID_STOP_REASON" in codes


@pytest.mark.parametrize("reason", [
    "converged", "budget_exhausted", "token_limit",
    "turn_limit", "error", "interrupted", "supervisor_stopped",
])
def test_all_valid_stop_reasons(reason):
    events = [_start(), _stop(reason=reason)]
    codes = [v.code for v in validate(events)]
    assert "INVALID_STOP_REASON" not in codes, f"unexpected violation for reason={reason!r}"


# ── EMPTY_STREAM ──────────────────────────────────────────────────────────────

def test_empty_stream():
    violations = validate([])
    assert len(violations) == 1
    assert violations[0].code == "EMPTY_STREAM"
    assert violations[0].event_index is None


# ── MISSING_AGENT_START ───────────────────────────────────────────────────────

def test_missing_agent_start():
    events = [_stop()]
    violations = validate(events)
    codes = [v.code for v in violations]
    assert "MISSING_AGENT_START" in codes
    start_v = next(v for v in violations if v.code == "MISSING_AGENT_START")
    assert start_v.event_index == 0


# ── MISSING_AGENT_STOP ────────────────────────────────────────────────────────

def test_missing_agent_stop():
    events = [_start()]
    violations = validate(events)
    codes = [v.code for v in violations]
    assert "MISSING_AGENT_STOP" in codes
    stop_v = next(v for v in violations if v.code == "MISSING_AGENT_STOP")
    assert stop_v.event_index == 0


def test_missing_both_start_and_stop():
    events = [TextOutput(run_id="r1", step=1, text="hi")]
    codes = [v.code for v in validate(events)]
    assert "MISSING_AGENT_START" in codes
    assert "MISSING_AGENT_STOP" in codes


# ── RUN_ID_MISMATCH ───────────────────────────────────────────────────────────

def test_run_id_mismatch():
    events = [
        _start("r1"),
        ModelTurnStart(run_id="r2", step=1),
        _stop("r1"),
    ]
    violations = validate(events)
    codes = [v.code for v in violations]
    assert "RUN_ID_MISMATCH" in codes
    v = next(v for v in violations if v.code == "RUN_ID_MISMATCH")
    assert v.event_index == 1


def test_no_run_id_mismatch_when_consistent():
    events = [
        _start("abc"),
        TextOutput(run_id="abc", step=1, text="hi"),
        _stop("abc"),
    ]
    assert validate(events) == []


def test_hook_events_run_id_checked():
    events = [
        _start("r1"),
        HookRequest(run_id="r2", request_id="hr-1", hook_name="h",
                    trigger="on_stop", step=1, timeout_ms=30000),
        HookVerdictApplied(run_id="r1", request_id="hr-1", verdict="continue"),
        _stop("r1"),
    ]
    codes = [v.code for v in validate(events)]
    assert "RUN_ID_MISMATCH" in codes


# ── TIMESTAMP_REGRESSION ─────────────────────────────────────────────────────

def test_timestamp_regression():
    start = _start()
    stop = _stop()
    start.ts = "2026-01-01T00:00:02Z"
    stop.ts = "2026-01-01T00:00:01Z"
    violations = validate([start, stop])
    codes = [v.code for v in violations]
    assert "TIMESTAMP_REGRESSION" in codes
    v = next(v for v in violations if v.code == "TIMESTAMP_REGRESSION")
    assert v.event_index == 1


def test_equal_timestamps_are_ok():
    start = _start()
    stop = _stop()
    start.ts = "2026-01-01T00:00:00Z"
    stop.ts = "2026-01-01T00:00:00Z"
    assert validate([start, stop]) == []


# ── DUPLICATE_CALL_ID ─────────────────────────────────────────────────────────

def test_duplicate_call_id():
    events = [
        _start(),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="bash", input={}),
        ToolCall(run_id="r1", step=2, call_id="c1", tool="bash", input={}),
        ToolResult(run_id="r1", step=1, call_id="c1", tool="bash", output="a", duration_ms=1),
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "DUPLICATE_CALL_ID" in codes


# ── UNMATCHED_TOOL_RESULT ─────────────────────────────────────────────────────

def test_unmatched_tool_result():
    events = [
        _start(),
        ToolResult(run_id="r1", step=1, call_id="c99", tool="bash", output="x", duration_ms=1),
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "UNMATCHED_TOOL_RESULT" in codes


def test_unmatched_tool_call_failed():
    events = [
        _start(),
        ToolCallFailed(run_id="r1", step=1, call_id="c99", tool="bash", error="oops"),
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "UNMATCHED_TOOL_RESULT" in codes


# ── UNCLOSED_TOOL_CALL ────────────────────────────────────────────────────────

def test_unclosed_tool_call():
    events = [
        _start(),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="bash", input={}),
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "UNCLOSED_TOOL_CALL" in codes


# ── INVALID_ERROR_CODE ────────────────────────────────────────────────────────

def test_invalid_error_code():
    events = [
        _start(),
        RunError(run_id="r1", code="oops_unknown", message="bad"),
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "INVALID_ERROR_CODE" in codes


def test_valid_error_codes():
    for code in ("rate_limit", "context_limit", "auth_error", "runner_crash", "unknown"):
        events = [_start(), RunError(run_id="r1", code=code, message="msg"), _stop()]
        codes = [v.code for v in validate(events)]
        assert "INVALID_ERROR_CODE" not in codes, f"unexpected violation for code={code!r}"


# ── INVALID_REJECTION_REASON ──────────────────────────────────────────────────

def test_invalid_rejection_reason():
    events = [
        _start(),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="bash", input={}),
        ToolResult(run_id="r1", step=1, call_id="c1", tool="bash",
                   output="x", duration_ms=1,
                   rejected=True, rejection_reason="made_up_reason"),
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "INVALID_REJECTION_REASON" in codes


# ── REJECTION_REASON_WITHOUT_REJECTED ────────────────────────────────────────

def test_rejection_reason_without_rejected():
    events = [
        _start(),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="bash", input={}),
        ToolResult(run_id="r1", step=1, call_id="c1", tool="bash",
                   output="x", duration_ms=1,
                   rejected=False, rejection_reason="ceiling_reached"),
        _stop(),
    ]
    codes = [v.code for v in validate(events)]
    assert "REJECTION_REASON_WITHOUT_REJECTED" in codes


def test_rejected_true_with_valid_reason_passes():
    events = [
        _start(),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="bash", input={}),
        ToolResult(run_id="r1", step=1, call_id="c1", tool="bash",
                   output="blocked", duration_ms=1,
                   rejected=True, rejection_reason="ceiling_reached"),
        _stop(),
    ]
    assert validate(events) == []


# ── Custom / unknown event types ──────────────────────────────────────────────

def test_custom_event_type_passes_validation():
    start = _start()
    stop = _stop()
    custom = {"type": "myframework.verifier_result", "run_id": "r1", "ts": start.ts}
    events = [start, custom, stop]
    assert validate(events) == []


# ── Violation.__str__ ─────────────────────────────────────────────────────────

def test_violation_str_with_index():
    v = Violation("SOME_CODE", "something went wrong", event_index=3)
    assert "SOME_CODE" in str(v)
    assert "event 3" in str(v)
    assert "something went wrong" in str(v)


def test_violation_str_without_index():
    v = Violation("EMPTY_STREAM", "no events")
    assert "stream" in str(v)


# ── Context compaction ────────────────────────────────────────────────────────

def test_context_compaction_passes_validation():
    events = [
        _start(),
        ContextCompaction(run_id="r1", step=1, tokens_before=148000, tokens_after=12000),
        _stop(),
    ]
    assert validate(events) == []


def test_context_compaction_with_compacted_messages_passes():
    events = [
        _start(),
        ContextCompaction(run_id="r1", step=1, tokens_before=148000, tokens_after=12000,
                          compacted_messages=[{"role": "user", "content": "Summary here."}]),
        _stop(),
    ]
    assert validate(events) == []


# ── Complex combined scenarios ────────────────────────────────────────────────

def test_full_run_with_hooks_skills_and_tools():
    events = [
        _start(),
        SkillRead(run_id="r1", step=1, name="code-review"),
        SkillExecute(run_id="r1", step=1, name="code-review"),
        ModelTurnStart(run_id="r1", step=1),
        ModelTurnEnd(run_id="r1", step=1, tokens_input=100, tokens_output=50,
                     cost_usd=0.001, duration_ms=500),
        ToolCall(run_id="r1", step=1, call_id="c1", tool="write_file", input={"path": "a.py"}),
        ToolResult(run_id="r1", step=1, call_id="c1", tool="write_file", output="ok", duration_ms=5),
        _hook_req("hr-1", trigger="on_tool:write_file", step=1),
        _hook_applied("hr-1", "continue"),
        _stop(),
    ]
    assert validate(events) == []


def test_multiple_violations_reported_together():
    """Validator reports all violations, not just the first."""
    events = [
        _start("r1"),
        ToolResult(run_id="r1", step=1, call_id="c99", tool="bash", output="x", duration_ms=1),
        _hook_applied("hr-99"),
        AgentStop(run_id="r1", reason="made_up",
                  total_tokens=0, total_cost_usd=0, total_turns=1, duration_ms=0),
    ]
    codes = [v.code for v in validate(events)]
    assert "UNMATCHED_TOOL_RESULT" in codes
    assert "UNMATCHED_HOOK_VERDICT_APPLIED" in codes
    assert "INVALID_STOP_REASON" in codes
