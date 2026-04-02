"""Tests for AEP event types — construction, serialization, deserialization."""

import json
import io
import pytest
from agent_execution_protocol import (
    AgentStart, ModelTurnStart, ModelTurnEnd,
    ToolCall, ToolResult, ToolCallFailed,
    TextOutput, CostUpdate, ContextCompaction, RunError, AgentStop,
    HookRequest, HookVerdict, HookVerdictApplied,
    SkillRead, SkillExecute,
    event_from_dict,
    emit_agent_start, emit_tool_call, emit_tool_result,
    emit_agent_stop, emit_error,
    emit_hook_request, emit_hook_verdict_applied,
    emit_skill_read, emit_skill_execute,
)
from agent_execution_protocol.events import VALID_STOP_REASONS


# ── AgentStart ────────────────────────────────────────────────────────────────

def test_agent_start_round_trip():
    e = AgentStart(run_id="r1", model="anthropic/claude-sonnet-4-6",
                   thread_id="t1", tags=["x"], meta={"k": "v"})
    d = e.to_dict()
    assert d["type"] == "agent_start"
    assert d["run_id"] == "r1"
    assert d["thread_id"] == "t1"
    assert d["tags"] == ["x"]
    assert d["meta"] == {"k": "v"}
    e2 = event_from_dict(d)
    assert isinstance(e2, AgentStart)
    assert e2.run_id == "r1"


def test_agent_start_omits_optional_nones():
    d = AgentStart(run_id="r1", model="m").to_dict()
    assert "thread_id" not in d
    assert "session_id" not in d
    assert "tags" not in d
    assert "meta" not in d


def test_agent_start_with_observability_fields():
    tools = [{"name": "bash", "description": "Run shell commands"}, {"name": "read"}]
    e = AgentStart(run_id="r1", model="m", prompt="Do the thing",
                   system_prompt="You are a helpful agent.", tools=tools)
    d = e.to_dict()
    assert d["prompt"] == "Do the thing"
    assert d["system_prompt"] == "You are a helpful agent."
    assert d["tools"] == tools

    e2 = AgentStart(run_id="r1", model="m")
    d2 = e2.to_dict()
    assert "prompt" not in d2
    assert "system_prompt" not in d2
    assert "tools" not in d2


# ── ModelTurnStart ────────────────────────────────────────────────────────────

def test_model_turn_start_no_messages_field():
    """messages array was removed — must not appear."""
    e = ModelTurnStart(run_id="r1", step=1)
    d = e.to_dict()
    assert "messages" not in d


def test_model_turn_start_context_messages():
    e = ModelTurnStart(run_id="r1", step=3, context_messages=42)
    d = e.to_dict()
    assert d["context_messages"] == 42


def test_model_turn_start_omits_context_messages_when_none():
    d = ModelTurnStart(run_id="r1", step=1).to_dict()
    assert "context_messages" not in d


# ── ModelTurnEnd ──────────────────────────────────────────────────────────────

def test_model_turn_end_cache_tokens():
    e = ModelTurnEnd(run_id="r1", step=1, tokens_input=10, tokens_output=5,
                     cost_usd=0.001, duration_ms=200,
                     tokens_cache_read=5000, tokens_cache_write=100)
    d = e.to_dict()
    assert d["tokens_cache_read"] == 5000
    assert d["tokens_cache_write"] == 100


def test_model_turn_end_omits_cache_when_none():
    d = ModelTurnEnd(run_id="r1", step=1, tokens_input=10, tokens_output=5,
                     cost_usd=0.001, duration_ms=200).to_dict()
    assert "tokens_cache_read" not in d
    assert "tokens_cache_write" not in d


# ── ToolCall / ToolResult ─────────────────────────────────────────────────────

def test_tool_call_round_trip():
    e = ToolCall(run_id="r1", step=2, call_id="c1", tool="myrunner__bash",
                 input={"command": "ls"}, subtype="shell")
    d = e.to_dict()
    assert d["type"] == "tool_call"
    assert d["subtype"] == "shell"
    e2 = event_from_dict(d)
    assert isinstance(e2, ToolCall)
    assert e2.call_id == "c1"


def test_tool_call_omits_none_subtype():
    d = ToolCall(run_id="r1", step=1, call_id="c1", tool="t", input={}).to_dict()
    assert "subtype" not in d


def test_tool_result_rejected_fields():
    e = ToolResult(run_id="r1", step=1, call_id="c1", tool="t", output="err",
                   duration_ms=1, rejected=True, rejection_reason="ceiling_reached")
    d = e.to_dict()
    assert d["rejected"] is True
    assert d["rejection_reason"] == "ceiling_reached"


def test_tool_result_omits_rejected_when_false():
    d = ToolResult(run_id="r1", step=1, call_id="c1", tool="t",
                   output="ok", duration_ms=5).to_dict()
    assert "rejected" not in d
    assert "rejection_reason" not in d


# ── AgentStop ─────────────────────────────────────────────────────────────────

def test_agent_stop_with_output():
    e = AgentStop(run_id="r1", reason="converged", total_tokens=100,
                  total_cost_usd=0.01, total_turns=3, duration_ms=5000,
                  output={"result": "done"})
    d = e.to_dict()
    assert d["output"] == {"result": "done"}
    e2 = event_from_dict(d)
    assert isinstance(e2, AgentStop)
    assert e2.output == {"result": "done"}


def test_agent_stop_omits_none_output():
    d = AgentStop(run_id="r1", reason="converged", total_tokens=0,
                  total_cost_usd=0.0, total_turns=1, duration_ms=0).to_dict()
    assert "output" not in d


def test_agent_stop_supervisor_stopped_reason():
    e = AgentStop(run_id="r1", reason="supervisor_stopped", total_tokens=50,
                  total_cost_usd=0.005, total_turns=2, duration_ms=1000)
    d = e.to_dict()
    assert d["reason"] == "supervisor_stopped"
    e2 = event_from_dict(d)
    assert isinstance(e2, AgentStop)
    assert e2.reason == "supervisor_stopped"


# ── VALID_STOP_REASONS ────────────────────────────────────────────────────────

def test_valid_stop_reasons_includes_supervisor_stopped():
    assert "supervisor_stopped" in VALID_STOP_REASONS


def test_valid_stop_reasons_includes_all_original():
    for reason in ("converged", "budget_exhausted", "token_limit", "turn_limit", "error", "interrupted"):
        assert reason in VALID_STOP_REASONS


# ── ContextCompaction ─────────────────────────────────────────────────────────

def test_context_compaction_round_trip():
    e = ContextCompaction(run_id="r1", step=3, tokens_before=148000, tokens_after=12000)
    d = e.to_dict()
    assert d["type"] == "context_compaction"
    assert d["tokens_before"] == 148000
    assert d["tokens_after"] == 12000
    e2 = event_from_dict(d)
    assert isinstance(e2, ContextCompaction)
    assert e2.tokens_before == 148000


def test_context_compaction_omits_compacted_messages_when_none():
    d = ContextCompaction(run_id="r1", step=1, tokens_before=50000, tokens_after=5000).to_dict()
    assert "compacted_messages" not in d


def test_context_compaction_with_compacted_messages():
    msgs = [{"role": "user", "content": "Summary of prior work: implemented auth module."}]
    e = ContextCompaction(run_id="r1", step=5, tokens_before=148000, tokens_after=3000,
                          compacted_messages=msgs)
    d = e.to_dict()
    assert d["compacted_messages"] == msgs
    e2 = event_from_dict(d)
    assert isinstance(e2, ContextCompaction)
    assert e2.compacted_messages == msgs


def test_context_compaction_multiple_compacted_messages():
    msgs = [
        {"role": "user", "content": "Context summary part 1."},
        {"role": "assistant", "content": "Acknowledged. Continuing from here."},
    ]
    e = ContextCompaction(run_id="r1", step=10, tokens_before=200000, tokens_after=4000,
                          compacted_messages=msgs)
    d = e.to_dict()
    assert len(d["compacted_messages"]) == 2


def test_context_compaction_empty_compacted_messages_list():
    # Empty list is different from None — it means compaction produced no messages
    e = ContextCompaction(run_id="r1", step=1, tokens_before=100, tokens_after=10,
                          compacted_messages=[])
    d = e.to_dict()
    assert "compacted_messages" in d
    assert d["compacted_messages"] == []


# ── HookRequest ───────────────────────────────────────────────────────────────

def test_hook_request_minimal():
    e = HookRequest(run_id="r1", request_id="hr-001", hook_name="check-writes",
                    trigger="on_tool:write_file", step=3, timeout_ms=10000)
    d = e.to_dict()
    assert d["type"] == "hook_request"
    assert d["request_id"] == "hr-001"
    assert d["hook_name"] == "check-writes"
    assert d["trigger"] == "on_tool:write_file"
    assert d["step"] == 3
    assert d["timeout_ms"] == 10000


def test_hook_request_omits_call_id_when_none():
    e = HookRequest(run_id="r1", request_id="hr-001", hook_name="h",
                    trigger="on_turn_end", step=1, timeout_ms=30000)
    d = e.to_dict()
    assert "call_id" not in d


def test_hook_request_omits_context_when_none():
    e = HookRequest(run_id="r1", request_id="hr-001", hook_name="h",
                    trigger="on_stop", step=5, timeout_ms=30000)
    d = e.to_dict()
    assert "context" not in d


def test_hook_request_with_call_id_and_context():
    ctx = {"tool": "write_file", "input": {"path": "/etc/evil"}, "output": "written"}
    e = HookRequest(run_id="r1", request_id="hr-002", hook_name="review-writes",
                    trigger="on_tool:write_file", step=2, timeout_ms=15000,
                    call_id="c7", context=ctx)
    d = e.to_dict()
    assert d["call_id"] == "c7"
    assert d["context"] == ctx


def test_hook_request_round_trip():
    ctx = {"tool": "bash", "input": {"command": "rm -rf /"}, "output": "error"}
    e = HookRequest(run_id="r1", request_id="hr-003", hook_name="safety",
                    trigger="on_tool:bash", step=4, timeout_ms=5000,
                    call_id="c1", context=ctx)
    d = e.to_dict()
    e2 = event_from_dict(d)
    assert isinstance(e2, HookRequest)
    assert e2.request_id == "hr-003"
    assert e2.context == ctx


# ── HookVerdict ───────────────────────────────────────────────────────────────

def test_hook_verdict_continue():
    e = HookVerdict(run_id="r1", request_id="hr-001", verdict="continue")
    d = e.to_dict()
    assert d["type"] == "hook_verdict"
    assert d["verdict"] == "continue"
    assert "message" not in d


def test_hook_verdict_stop():
    e = HookVerdict(run_id="r1", request_id="hr-001", verdict="stop")
    d = e.to_dict()
    assert d["verdict"] == "stop"
    assert "message" not in d


def test_hook_verdict_inject_with_message():
    e = HookVerdict(run_id="r1", request_id="hr-001", verdict="inject",
                    message="You wrote to /etc — try src/ instead.")
    d = e.to_dict()
    assert d["verdict"] == "inject"
    assert d["message"] == "You wrote to /etc — try src/ instead."


def test_hook_verdict_omits_message_when_none():
    d = HookVerdict(run_id="r1", request_id="hr-001", verdict="continue").to_dict()
    assert "message" not in d


def test_hook_verdict_round_trip():
    e = HookVerdict(run_id="r1", request_id="hr-001", verdict="inject",
                    message="Please reconsider this approach.")
    d = e.to_dict()
    e2 = event_from_dict(d)
    assert isinstance(e2, HookVerdict)
    assert e2.verdict == "inject"
    assert e2.message == "Please reconsider this approach."


# ── HookVerdictApplied ────────────────────────────────────────────────────────

def test_hook_verdict_applied_continue():
    e = HookVerdictApplied(run_id="r1", request_id="hr-001", verdict="continue")
    d = e.to_dict()
    assert d["type"] == "hook_verdict_applied"
    assert d["verdict"] == "continue"
    assert "timed_out" not in d


def test_hook_verdict_applied_stop():
    e = HookVerdictApplied(run_id="r1", request_id="hr-001", verdict="stop")
    d = e.to_dict()
    assert d["verdict"] == "stop"


def test_hook_verdict_applied_timed_out():
    e = HookVerdictApplied(run_id="r1", request_id="hr-001", verdict="continue", timed_out=True)
    d = e.to_dict()
    assert d["timed_out"] is True


def test_hook_verdict_applied_omits_timed_out_when_false():
    d = HookVerdictApplied(run_id="r1", request_id="hr-001", verdict="stop").to_dict()
    assert "timed_out" not in d


def test_hook_verdict_applied_round_trip():
    e = HookVerdictApplied(run_id="r1", request_id="hr-005", verdict="inject", timed_out=False)
    d = e.to_dict()
    e2 = event_from_dict(d)
    assert isinstance(e2, HookVerdictApplied)
    assert e2.request_id == "hr-005"
    assert e2.verdict == "inject"


def test_hook_verdict_applied_timed_out_round_trip():
    e = HookVerdictApplied(run_id="r1", request_id="hr-006", verdict="stop", timed_out=True)
    d = e.to_dict()
    e2 = event_from_dict(d)
    assert isinstance(e2, HookVerdictApplied)
    assert e2.timed_out is True


# ── SkillRead ─────────────────────────────────────────────────────────────────

def test_skill_read_minimal():
    e = SkillRead(run_id="r1", step=2, name="pdf-processing")
    d = e.to_dict()
    assert d["type"] == "skill_read"
    assert d["name"] == "pdf-processing"
    assert d["step"] == 2
    assert "source" not in d


def test_skill_read_with_source():
    e = SkillRead(run_id="r1", step=1, name="code-review",
                  source="~/.claude/skills/code-review")
    d = e.to_dict()
    assert d["source"] == "~/.claude/skills/code-review"


def test_skill_read_omits_source_when_none():
    d = SkillRead(run_id="r1", step=1, name="my-skill").to_dict()
    assert "source" not in d


def test_skill_read_round_trip():
    e = SkillRead(run_id="r1", step=3, name="data-analysis", source="/skills/data-analysis")
    d = e.to_dict()
    e2 = event_from_dict(d)
    assert isinstance(e2, SkillRead)
    assert e2.name == "data-analysis"
    assert e2.source == "/skills/data-analysis"


def test_skill_read_round_trip_no_source():
    e = SkillRead(run_id="r1", step=1, name="my-skill")
    d = e.to_dict()
    e2 = event_from_dict(d)
    assert isinstance(e2, SkillRead)
    assert e2.source is None


# ── SkillExecute ──────────────────────────────────────────────────────────────

def test_skill_execute_basic():
    e = SkillExecute(run_id="r1", step=4, name="pdf-processing")
    d = e.to_dict()
    assert d["type"] == "skill_execute"
    assert d["name"] == "pdf-processing"
    assert d["step"] == 4


def test_skill_execute_round_trip():
    e = SkillExecute(run_id="r1", step=2, name="code-review")
    d = e.to_dict()
    e2 = event_from_dict(d)
    assert isinstance(e2, SkillExecute)
    assert e2.name == "code-review"
    assert e2.step == 2


def test_skill_execute_no_extra_fields():
    d = SkillExecute(run_id="r1", step=1, name="my-skill").to_dict()
    assert set(d.keys()) == {"type", "run_id", "step", "name", "ts"}


# ── Parametrized round-trips for all event types ──────────────────────────────

@pytest.mark.parametrize("cls,kwargs", [
    (ModelTurnStart, {"run_id": "r1", "step": 1}),
    (ModelTurnEnd, {"run_id": "r1", "step": 1, "tokens_input": 10, "tokens_output": 5,
                    "cost_usd": 0.001, "duration_ms": 200}),
    (ToolCallFailed, {"run_id": "r1", "step": 1, "call_id": "c1", "tool": "t", "error": "oops"}),
    (TextOutput, {"run_id": "r1", "step": 1, "text": "hello"}),
    (CostUpdate, {"run_id": "r1", "total_cost_usd": 0.05, "total_tokens": 500}),
    (RunError, {"run_id": "r1", "code": "rate_limit", "message": "429"}),
    (ContextCompaction, {"run_id": "r1", "step": 1, "tokens_before": 50000, "tokens_after": 5000}),
    (SkillRead, {"run_id": "r1", "step": 1, "name": "my-skill"}),
    (SkillExecute, {"run_id": "r1", "step": 2, "name": "my-skill"}),
    (HookRequest, {"run_id": "r1", "request_id": "hr-1", "hook_name": "h",
                   "trigger": "on_stop", "step": 1, "timeout_ms": 30000}),
    (HookVerdict, {"run_id": "r1", "request_id": "hr-1", "verdict": "continue"}),
    (HookVerdictApplied, {"run_id": "r1", "request_id": "hr-1", "verdict": "continue"}),
])
def test_event_type_round_trips(cls, kwargs):
    e = cls(**kwargs)
    d = e.to_dict()
    e2 = event_from_dict(d)
    assert type(e2) is cls
    assert e2.run_id == "r1"


# ── event_from_dict passthrough for unknown types ─────────────────────────────

def test_unknown_event_type_returns_dict():
    d = {"type": "not_a_real_type", "run_id": "r1"}
    result = event_from_dict(d)
    assert result == d


def test_missing_type_returns_dict():
    d = {"run_id": "r1"}
    result = event_from_dict(d)
    assert result == d


def test_event_from_dict_custom_namespaced_type():
    d = {"type": "myframework.verifier_result", "run_id": "r1", "ts": "2026-01-01T00:00:00Z"}
    result = event_from_dict(d)
    assert isinstance(result, dict)
    assert result["type"] == "myframework.verifier_result"


# ── Emit helpers ──────────────────────────────────────────────────────────────

def test_emit_agent_start_writes_ndjson():
    buf = io.StringIO()
    emit_agent_start(run_id="r1", model="m", file=buf)
    line = buf.getvalue().strip()
    d = json.loads(line)
    assert d["type"] == "agent_start"
    assert d["run_id"] == "r1"


def test_emit_flushes_immediately():
    buf = io.StringIO()
    emit_tool_call(run_id="r1", step=1, call_id="c1", tool="bash", input={}, file=buf)
    assert buf.getvalue().endswith("\n")


def test_emit_agent_stop_writes_valid_json():
    buf = io.StringIO()
    emit_agent_stop(run_id="r1", reason="converged", total_tokens=100,
                    total_cost_usd=0.01, total_turns=2, duration_ms=3000, file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["type"] == "agent_stop"
    assert d["reason"] == "converged"


def test_emit_error_writes_code_and_message():
    buf = io.StringIO()
    emit_error(run_id="r1", code="rate_limit", message="Too many requests", file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["code"] == "rate_limit"
    assert d["message"] == "Too many requests"


def test_emit_hook_request():
    buf = io.StringIO()
    emit_hook_request(run_id="r1", request_id="hr-001", hook_name="check-writes",
                      trigger="on_tool:write_file", step=3, timeout_ms=10000,
                      call_id="c5", context={"tool": "write_file"}, file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["type"] == "hook_request"
    assert d["request_id"] == "hr-001"
    assert d["call_id"] == "c5"
    assert d["context"] == {"tool": "write_file"}


def test_emit_hook_request_minimal():
    buf = io.StringIO()
    emit_hook_request(run_id="r1", request_id="hr-001", hook_name="h",
                      trigger="on_stop", step=1, file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["type"] == "hook_request"
    assert "call_id" not in d
    assert "context" not in d


def test_emit_hook_verdict_applied():
    buf = io.StringIO()
    emit_hook_verdict_applied(run_id="r1", request_id="hr-001", verdict="stop", file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["type"] == "hook_verdict_applied"
    assert d["verdict"] == "stop"
    assert "timed_out" not in d


def test_emit_hook_verdict_applied_timed_out():
    buf = io.StringIO()
    emit_hook_verdict_applied(run_id="r1", request_id="hr-001", verdict="continue",
                              timed_out=True, file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["timed_out"] is True


def test_emit_skill_read():
    buf = io.StringIO()
    emit_skill_read(run_id="r1", step=1, name="pdf-processing",
                    source="~/.claude/skills/pdf-processing", file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["type"] == "skill_read"
    assert d["name"] == "pdf-processing"
    assert d["source"] == "~/.claude/skills/pdf-processing"


def test_emit_skill_read_no_source():
    buf = io.StringIO()
    emit_skill_read(run_id="r1", step=1, name="my-skill", file=buf)
    d = json.loads(buf.getvalue().strip())
    assert "source" not in d


def test_emit_skill_execute():
    buf = io.StringIO()
    emit_skill_execute(run_id="r1", step=2, name="code-review", file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["type"] == "skill_execute"
    assert d["name"] == "code-review"


def test_each_emit_produces_exactly_one_line():
    """Every emit helper must produce exactly one NDJSON line."""
    cases = [
        lambda buf: emit_agent_start(run_id="r1", model="m", file=buf),
        lambda buf: emit_hook_request(run_id="r1", request_id="x", hook_name="h",
                                       trigger="on_stop", step=1, file=buf),
        lambda buf: emit_hook_verdict_applied(run_id="r1", request_id="x",
                                               verdict="continue", file=buf),
        lambda buf: emit_skill_read(run_id="r1", step=1, name="s", file=buf),
        lambda buf: emit_skill_execute(run_id="r1", step=1, name="s", file=buf),
    ]
    for emit_fn in cases:
        buf = io.StringIO()
        emit_fn(buf)
        lines = [l for l in buf.getvalue().splitlines() if l]
        assert len(lines) == 1
        json.loads(lines[0])  # must be valid JSON
