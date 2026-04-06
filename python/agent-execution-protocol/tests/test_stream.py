"""Tests for stream parsing utilities."""

import io
import json
import pytest
from agent_execution_protocol import (
    AgentStart,
    AgentStop,
    ToolCall,
    ToolResult,
    HookRequest,
    HookVerdict,
    HookVerdictApplied,
    SkillRead,
    SkillExecute,
    parse_stream,
    iter_stream,
    write_event,
    read_config,
    read_verdict,
    send_verdict,
)


MINIMAL_STREAM = """\
{"type":"agent_start","schema_version":"0.2","run_id":"r1","model":"m","ts":"2026-01-01T00:00:00Z"}
{"type":"agent_stop","run_id":"r1","reason":"converged","total_tokens":10,"total_cost_usd":0.001,"total_turns":1,"duration_ms":100,"ts":"2026-01-01T00:00:01Z"}
"""


# ── parse_stream ──────────────────────────────────────────────────────────────


def test_parse_stream_minimal():
    events, errors = parse_stream(MINIMAL_STREAM)
    assert len(events) == 2
    assert errors == []
    assert isinstance(events[0], AgentStart)
    assert isinstance(events[1], AgentStop)


def test_parse_stream_skips_blank_lines():
    text = "\n\n" + MINIMAL_STREAM + "\n\n"
    events, errors = parse_stream(text)
    assert len(events) == 2
    assert errors == []


def test_parse_stream_reports_bad_json():
    text = MINIMAL_STREAM + "not json\n"
    events, errors = parse_stream(text)
    assert len(events) == 2
    assert len(errors) == 1
    assert "JSON parse error" in errors[0]
    assert "line 3" in errors[0]


def test_parse_stream_unknown_event_type_passes_through_as_dict():
    text = (
        MINIMAL_STREAM
        + '{"type":"future_event","run_id":"r1","ts":"2026-01-01T00:00:02Z"}\n'
    )
    events, errors = parse_stream(text)
    assert len(events) == 3
    assert errors == []
    assert isinstance(events[2], dict)
    assert events[2]["type"] == "future_event"


def test_parse_stream_empty_string():
    events, errors = parse_stream("")
    assert events == []
    assert errors == []


def test_parse_stream_hook_events():
    text = (
        '{"type":"agent_start","schema_version":"0.2","run_id":"r1","model":"m","ts":"2026-01-01T00:00:00Z"}\n'
        '{"type":"hook_request","run_id":"r1","request_id":"hr-1","hook_name":"h","trigger":"on_stop","step":1,"timeout_ms":30000,"ts":"2026-01-01T00:00:01Z"}\n'
        '{"type":"hook_verdict_applied","run_id":"r1","request_id":"hr-1","verdict":"continue","ts":"2026-01-01T00:00:02Z"}\n'
        '{"type":"agent_stop","run_id":"r1","reason":"converged","total_tokens":10,"total_cost_usd":0.001,"total_turns":1,"duration_ms":100,"ts":"2026-01-01T00:00:03Z"}\n'
    )
    events, errors = parse_stream(text)
    assert errors == []
    assert isinstance(events[1], HookRequest)
    assert isinstance(events[2], HookVerdictApplied)


def test_parse_stream_skill_events():
    text = (
        '{"type":"agent_start","schema_version":"0.2","run_id":"r1","model":"m","ts":"2026-01-01T00:00:00Z"}\n'
        '{"type":"skill_read","run_id":"r1","step":1,"name":"pdf-processing","ts":"2026-01-01T00:00:01Z"}\n'
        '{"type":"skill_execute","run_id":"r1","step":1,"name":"pdf-processing","ts":"2026-01-01T00:00:02Z"}\n'
        '{"type":"agent_stop","run_id":"r1","reason":"converged","total_tokens":10,"total_cost_usd":0.001,"total_turns":1,"duration_ms":100,"ts":"2026-01-01T00:00:03Z"}\n'
    )
    events, errors = parse_stream(text)
    assert errors == []
    assert isinstance(events[1], SkillRead)
    assert isinstance(events[2], SkillExecute)
    assert events[1].name == "pdf-processing"


def test_parse_stream_continues_after_bad_line():
    text = (
        '{"type":"agent_start","schema_version":"0.2","run_id":"r1","model":"m","ts":"2026-01-01T00:00:00Z"}\n'
        "GARBAGE\n"
        '{"type":"agent_stop","run_id":"r1","reason":"converged","total_tokens":0,"total_cost_usd":0,"total_turns":1,"duration_ms":0,"ts":"2026-01-01T00:00:01Z"}\n'
    )
    events, errors = parse_stream(text)
    assert len(events) == 2
    assert len(errors) == 1
    assert isinstance(events[0], AgentStart)
    assert isinstance(events[1], AgentStop)


def test_parse_stream_multiple_bad_lines():
    text = "bad1\nbad2\nbad3\n"
    events, errors = parse_stream(text)
    assert events == []
    assert len(errors) == 3


def test_parse_stream_supervisor_stopped_reason():
    text = (
        '{"type":"agent_start","schema_version":"0.2","run_id":"r1","model":"m","ts":"2026-01-01T00:00:00Z"}\n'
        '{"type":"agent_stop","run_id":"r1","reason":"supervisor_stopped","total_tokens":5,"total_cost_usd":0.0,"total_turns":1,"duration_ms":100,"ts":"2026-01-01T00:00:01Z"}\n'
    )
    events, errors = parse_stream(text)
    assert errors == []
    assert isinstance(events[1], AgentStop)
    assert events[1].reason == "supervisor_stopped"


# ── iter_stream ───────────────────────────────────────────────────────────────


def test_iter_stream_yields_tuples():
    f = io.StringIO(MINIMAL_STREAM)
    results = list(iter_stream(f))
    assert len(results) == 2
    for lineno, event, error in results:
        assert event is not None
        assert error is None


def test_iter_stream_yields_error_on_bad_line():
    f = io.StringIO("bad json\n")
    results = list(iter_stream(f))
    assert len(results) == 1
    lineno, event, error = results[0]
    assert event is None
    assert error is not None
    assert lineno == 1


def test_iter_stream_lineno_is_1_indexed():
    f = io.StringIO(MINIMAL_STREAM)
    results = list(iter_stream(f))
    assert results[0][0] == 1
    assert results[1][0] == 2


def test_iter_stream_skips_blank_lines():
    text = "\n" + MINIMAL_STREAM + "\n"
    f = io.StringIO(text)
    results = list(iter_stream(f))
    assert len(results) == 2


# ── write_event ───────────────────────────────────────────────────────────────


def test_write_event_produces_single_ndjson_line():
    buf = io.StringIO()
    e = AgentStart(run_id="r1", model="m")
    write_event(e, file=buf)
    lines = buf.getvalue().splitlines()
    assert len(lines) == 1
    d = json.loads(lines[0])
    assert d["type"] == "agent_start"


def test_write_event_multiple_events():
    buf = io.StringIO()
    write_event(AgentStart(run_id="r1", model="m"), file=buf)
    write_event(
        AgentStop(
            run_id="r1",
            reason="converged",
            total_tokens=0,
            total_cost_usd=0,
            total_turns=1,
            duration_ms=0,
        ),
        file=buf,
    )
    lines = [l for l in buf.getvalue().splitlines() if l]
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "agent_start"
    assert json.loads(lines[1])["type"] == "agent_stop"


def test_write_event_hook_request():
    buf = io.StringIO()
    e = HookRequest(
        run_id="r1",
        request_id="hr-1",
        hook_name="h",
        trigger="on_stop",
        step=1,
        timeout_ms=30000,
    )
    write_event(e, file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["type"] == "hook_request"


def test_write_event_skill_read():
    buf = io.StringIO()
    e = SkillRead(run_id="r1", step=1, name="pdf-processing")
    write_event(e, file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["type"] == "skill_read"
    assert d["name"] == "pdf-processing"


# ── read_config ───────────────────────────────────────────────────────────────


def test_read_config_parses_json():
    d = {"run_id": "r1", "model": "m"}
    f = io.StringIO(json.dumps(d) + "\n")
    result = read_config(f)
    assert result == d


def test_read_config_raises_on_empty():
    with pytest.raises(ValueError, match="empty input"):
        read_config(io.StringIO(""))


def test_read_config_raises_on_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        read_config(io.StringIO("not json\n"))


def test_read_config_reads_only_first_line():
    """Config is only the first line; remaining stdin is for hook verdicts."""
    lines = (
        json.dumps({"run_id": "r1", "model": "m"})
        + "\n"
        + json.dumps({"type": "hook_verdict"})
        + "\n"
    )
    f = io.StringIO(lines)
    result = read_config(f)
    assert result["run_id"] == "r1"
    # Second line still available for read_verdict
    remaining = f.readline()
    assert "hook_verdict" in remaining


# ── read_verdict ──────────────────────────────────────────────────────────────


def test_read_verdict_continue():
    payload = {
        "type": "hook_verdict",
        "run_id": "r1",
        "request_id": "hr-001",
        "verdict": "continue",
        "ts": "2026-01-01T00:00:00Z",
    }
    f = io.StringIO(json.dumps(payload) + "\n")
    v = read_verdict(f)
    assert isinstance(v, HookVerdict)
    assert v.verdict == "continue"
    assert v.request_id == "hr-001"


def test_read_verdict_stop():
    payload = {
        "type": "hook_verdict",
        "run_id": "r1",
        "request_id": "hr-002",
        "verdict": "stop",
        "ts": "2026-01-01T00:00:00Z",
    }
    f = io.StringIO(json.dumps(payload) + "\n")
    v = read_verdict(f)
    assert v.verdict == "stop"


def test_read_verdict_inject_with_message():
    payload = {
        "type": "hook_verdict",
        "run_id": "r1",
        "request_id": "hr-003",
        "verdict": "inject",
        "message": "Try a safer path.",
        "ts": "2026-01-01T00:00:00Z",
    }
    f = io.StringIO(json.dumps(payload) + "\n")
    v = read_verdict(f)
    assert v.verdict == "inject"
    assert v.message == "Try a safer path."


def test_read_verdict_raises_on_empty_input():
    with pytest.raises(ValueError, match="empty input"):
        read_verdict(io.StringIO(""))


def test_read_verdict_raises_on_wrong_type():
    payload = {"type": "agent_start", "run_id": "r1", "model": "m"}
    f = io.StringIO(json.dumps(payload) + "\n")
    with pytest.raises(ValueError, match="hook_verdict"):
        read_verdict(f)


def test_read_verdict_raises_on_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        read_verdict(io.StringIO("not json\n"))


@pytest.mark.parametrize("missing_field", ["run_id", "request_id", "verdict"])
def test_read_verdict_raises_on_missing_required_field(missing_field):
    payload = {
        "type": "hook_verdict",
        "run_id": "r1",
        "request_id": "hr-001",
        "verdict": "continue",
        "ts": "2026-01-01T00:00:00Z",
    }
    del payload[missing_field]
    f = io.StringIO(json.dumps(payload) + "\n")
    with pytest.raises(ValueError, match=missing_field):
        read_verdict(f)


def test_read_verdict_message_is_none_when_absent():
    payload = {
        "type": "hook_verdict",
        "run_id": "r1",
        "request_id": "hr-001",
        "verdict": "continue",
        "ts": "2026-01-01T00:00:00Z",
    }
    f = io.StringIO(json.dumps(payload) + "\n")
    v = read_verdict(f)
    assert v.message is None


# ── send_verdict ──────────────────────────────────────────────────────────────


def test_send_verdict_writes_ndjson():
    buf = io.StringIO()
    v = HookVerdict(run_id="r1", request_id="hr-001", verdict="continue")
    send_verdict(v, file=buf)
    line = buf.getvalue()
    assert line.endswith("\n")
    d = json.loads(line.strip())
    assert d["type"] == "hook_verdict"
    assert d["verdict"] == "continue"


def test_send_verdict_stop():
    buf = io.StringIO()
    v = HookVerdict(run_id="r1", request_id="hr-001", verdict="stop")
    send_verdict(v, file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["verdict"] == "stop"


def test_send_verdict_inject_with_message():
    buf = io.StringIO()
    v = HookVerdict(
        run_id="r1", request_id="hr-001", verdict="inject", message="Please reconsider."
    )
    send_verdict(v, file=buf)
    d = json.loads(buf.getvalue().strip())
    assert d["verdict"] == "inject"
    assert d["message"] == "Please reconsider."


def test_send_verdict_produces_exactly_one_line():
    buf = io.StringIO()
    v = HookVerdict(run_id="r1", request_id="hr-001", verdict="continue")
    send_verdict(v, file=buf)
    lines = [l for l in buf.getvalue().splitlines() if l]
    assert len(lines) == 1


# ── read_verdict / send_verdict round trip ────────────────────────────────────


def test_send_then_read_verdict_round_trip():
    """Supervisor writes a verdict; runner reads it back."""
    pipe = io.StringIO()
    original = HookVerdict(
        run_id="r1",
        request_id="hr-042",
        verdict="inject",
        message="Course-correct: avoid /etc paths.",
    )
    send_verdict(original, file=pipe)
    pipe.seek(0)
    received = read_verdict(pipe)
    assert received.run_id == original.run_id
    assert received.request_id == original.request_id
    assert received.verdict == original.verdict
    assert received.message == original.message


@pytest.mark.parametrize("verdict", ["continue", "stop", "inject"])
def test_round_trip_all_verdict_types(verdict):
    pipe = io.StringIO()
    msg = "hint" if verdict == "inject" else None
    v = HookVerdict(run_id="r1", request_id="hr-1", verdict=verdict, message=msg)
    send_verdict(v, file=pipe)
    pipe.seek(0)
    received = read_verdict(pipe)
    assert received.verdict == verdict
    assert received.message == msg
