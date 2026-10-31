import json

import pytest

from avp.trajectory import parse_trajectory_event
from avp.utils.cloudevents import to_cloudevent
from avp.utils.otel import to_otlp_json, to_spans

MODEL = {"provider": "anthropic", "id": "claude-sonnet-4-5"}
USAGE = {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001, "cost_source": "computed"}
DESCRIPTOR = {"avp_version": "0.1", "agent_name": "demo", "agent_version": "1.0.0"}


def event(n: int, type: str, data: dict) -> dict:
    return {
        "avp_version": "0.1",
        "id": f"e{n}",
        "time": f"2026-10-31T12:00:{n:02d}Z",
        "run_id": "run-1",
        "type": type,
        "data": data,
    }


def response(n: int, content: list, **extra) -> dict:
    data = {"content": content, "model": MODEL, "duration_ms": 500, "usage": USAGE, **extra}
    return event(n, "assistant_message", data)


TRAJECTORY = [
    event(0, "run_requested", {}),
    event(1, "agent_described", {"descriptor": DESCRIPTOR}),
    event(2, "agent_started", {"prompt": "Go.", "system_prompt": "Be brief.", "model": MODEL}),
    response(3, [{"type": "tool_use", "id": "t1", "name": "explore", "input": {"q": "x"}}]),
    event(
        4, "tool_invoked", {"tool_call_id": "t1", "tool_name": "explore", "tool_input": {"q": "x"}}
    ),
    event(
        5,
        "subagent_invoked",
        {"subagent_name": "explorer", "invocation_id": "t1", "subagent_input": {"q": "x"}},
    ),
    response(6, [{"type": "text", "text": "found"}], subagent_invocation_id="t1"),
    event(
        7,
        "subagent_returned",
        {
            "subagent_name": "explorer",
            "invocation_id": "t1",
            "duration_ms": 2000,
            "subagent_reason": "converged",
            "subagent_result_text": "found",
        },
    ),
    event(
        8,
        "tool_returned",
        {
            "tool_call_id": "t1",
            "tool_name": "explore",
            "duration_ms": 4000,
            "tool_result": {"type": "tool_result", "tool_use_id": "t1", "content": "found"},
        },
    ),
    response(9, [{"type": "text", "text": "done"}], response_model="claude-sonnet-4-5-20250929"),
    event(10, "agent_stopped", {"reason": "converged"}),
]


def events():
    return [parse_trajectory_event(e) for e in TRAJECTORY]


def test_spans_nest_the_run_responses_tools_and_subagents():
    spans = {span.name + f"@{span.start.second}": span for span in to_spans(events())}
    run = spans["invoke_agent demo@2"]
    first = spans["chat claude-sonnet-4-5@2"]
    tool = spans["execute_tool explore@4"]
    subagent = spans["invoke_agent explorer@5"]
    inner = spans["chat claude-sonnet-4-5@5"]
    last = spans["chat claude-sonnet-4-5@8"]

    assert run.parent_span_id is None
    assert (run.start.second, run.end.second) == (2, 10)
    assert first.parent_span_id == run.span_id and first.end.second == 3
    assert tool.parent_span_id == first.span_id and tool.end.second == 8
    assert subagent.parent_span_id == tool.span_id and subagent.end.second == 7
    assert inner.parent_span_id == subagent.span_id
    assert last.attributes["gen_ai.response.model"] == "claude-sonnet-4-5-20250929"
    assert {s.trace_id for s in spans.values()} == {run.trace_id}
    assert to_spans(events()) == list(spans.values())  # same IDs every time


def test_content_is_left_out_unless_asked_for():
    def attribute_names(include_content: bool) -> set[str]:
        spans = to_spans(events(), include_content=include_content)
        return {name for span in spans for name in span.attributes}

    content = {
        "gen_ai.system_instructions",
        "gen_ai.tool.call.arguments",
        "gen_ai.tool.call.result",
    }
    assert not content & attribute_names(False)
    assert content <= attribute_names(True)


def test_a_parent_traceparent_puts_the_run_in_its_trace():
    parent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    run = to_spans(events(), parent=parent)[0]
    assert run.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert run.parent_span_id == "b7ad6b7169203331"
    with pytest.raises(ValueError):
        to_spans(events(), parent="nope")


def test_a_span_the_trajectory_never_closes_ends_at_the_last_event():
    spans = to_spans(events()[:5])
    assert all(span.end.second <= 4 for span in spans)
    assert any(span.name == "execute_tool explore" and span.end.second == 4 for span in spans)


def test_otlp_json():
    body = to_otlp_json(to_spans(events()))
    run, chat = body["resourceSpans"][0]["scopeSpans"][0]["spans"][:2]
    assert run["name"] == "invoke_agent demo" and run["kind"] == 1
    assert run["startTimeUnixNano"] == "1793448002000000000"
    assert chat["parentSpanId"] == run["spanId"] and chat["kind"] == 3
    assert {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "100"}} in chat["attributes"]
    json.dumps(body)


def test_cloudevent_carries_the_whole_event():
    tool_invoked = events()[4]
    cloudevent = to_cloudevent(tool_invoked, source="avp-cli")
    assert cloudevent["type"] == "avp.tool_invoked"
    assert cloudevent["subject"] == "run-1"
    assert cloudevent["time"] == "2026-10-31T12:00:04Z"
    assert parse_trajectory_event(cloudevent["data"]) == tool_invoked
