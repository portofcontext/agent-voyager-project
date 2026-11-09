import copy
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from avp.trajectory import parse_trajectory_event
from avp.utils.atif import to_atif

DATA = Path(__file__).resolve().parents[2] / "testdata"
SCHEMA = Draft202012Validator(json.loads((DATA / "atif/schema.json").read_text()))


def case(name):
    rows = json.loads((DATA / "recorder" / f"{name}.json").read_text())["events"]
    return [
        {
            **{k: v for k, v in row.items() if k != "t"},
            "id": f"e{i}",
            "time": (
                datetime(2026, 1, 1, tzinfo=UTC) + timedelta(milliseconds=row["t"])
            ).isoformat(),
        }
        for i, row in enumerate(rows)
    ]


def export(rows):
    events = []
    for row in rows:
        event = parse_trajectory_event(row)
        assert event is not None
        events.append(event)
    return to_atif(events)


def check_document(document):
    SCHEMA.validate(document)
    assert document["schema_version"] == "ATIF-v1.8"
    assert [s["step_id"] for s in document["steps"]] == list(range(1, len(document["steps"]) + 1))
    children = document.get("subagent_trajectories", [])
    ids = {child["trajectory_id"] for child in children}
    assert len(ids) == len(children)
    for step in document["steps"]:
        calls = {c["tool_call_id"] for c in step.get("tool_calls", [])}
        for result in step.get("observation", {}).get("results", []):
            if "source_call_id" in result:
                assert result["source_call_id"] in calls
            for ref in result.get("subagent_trajectory_ref", []):
                assert ref["trajectory_id"] in ids
    for child in children:
        check_document(child)


@pytest.mark.parametrize("name", [p.stem for p in sorted((DATA / "recorder").glob("*.json"))])
def test_shared_recorder_cases_match_upstream_schema_and_references(name):
    rows = case(name)
    result = export(rows)
    check_document(result.trajectory)
    assert (
        not {"events", "event_metadata", "event_defaults"}
        & result.trajectory["extra"]["avp"].keys()
    )
    assert result.trajectory["extra"]["avp"]["complete"]
    assert export(rows).trajectory == result.trajectory


def test_child_steps_and_totals_are_not_duplicated_on_the_parent():
    result = export(case("subagent-from-tool")).trajectory
    child = result["subagent_trajectories"][0]
    parent_responses = [s for s in result["steps"] if s["source"] == "agent"]
    child_responses = [s for s in child["steps"] if s["source"] == "agent"]
    assert len(parent_responses) == len(child_responses) == 2
    assert result["final_metrics"]["total_prompt_tokens"] == 4000
    assert child["final_metrics"]["total_prompt_tokens"] == 2000
    assert result["final_metrics"]["total_cost_usd"] == pytest.approx(0.018)
    assert parent_responses[0]["observation"]["results"][0]["subagent_trajectory_ref"] == [
        {"trajectory_id": child["trajectory_id"]}
    ]
    assert child["agent"]["version"] == "unknown"  # AVP doesn't report a child version.


def test_unknown_cost_is_omitted_instead_of_exported_as_free():
    rows = case("plain-response")
    response = next(e for e in rows if e["type"] == "assistant_message")
    response["data"]["usage"].update(cost_usd=0, cost_source="unknown")
    result = export(rows).trajectory
    response = next(s for s in result["steps"] if s["source"] == "agent")
    assert "cost_usd" not in response["metrics"]
    assert "total_cost_usd" not in result["final_metrics"]
    assert result["final_metrics"]["extra"]["avp"]["known_totals"]["total_cost_usd"] == 0


def test_opaque_subagent_usage_is_counted_once_without_inventing_model_responses():
    rows = case("subagent-from-tool")
    rows = [e for e in rows if "subagent_invocation_id" not in e["data"]]
    returned = next(e for e in rows if e["type"] == "subagent_returned")
    returned["data"]["subagent_usage"] = {"input_tokens": 2000, "responses": 2}
    result = export(rows).trajectory
    check_document(result)
    child = result["subagent_trajectories"][0]
    assert all(s["source"] != "agent" for s in child["steps"])
    assert result["final_metrics"]["total_prompt_tokens"] == 4000
    assert "total_cost_usd" not in result["final_metrics"]
    assert "total_completion_tokens" not in result["final_metrics"]
    assert child["final_metrics"]["total_prompt_tokens"] == 2000
    assert child["extra"]["avp"]["usage_details"]["responses"] == 2


def test_nested_delegation_keeps_each_reference_in_its_parent():
    rows = case("subagent-from-tool")
    child_call = next(
        e for e in rows if e["type"] == "tool_invoked" and e["data"].get("subagent_invocation_id")
    )
    nested_start = {
        **child_call,
        "id": "nested-start",
        "type": "subagent_invoked",
        "data": {
            "invocation_id": "call-2",
            "subagent_name": "nested",
            "subagent_input": {"q": "find"},
            "subagent_invocation_id": "call-1",
        },
    }
    nested_end = {
        **child_call,
        "id": "nested-end",
        "type": "subagent_returned",
        "data": {
            "invocation_id": "call-2",
            "subagent_name": "nested",
            "subagent_result_text": "found",
            "subagent_invocation_id": "call-1",
            "subagent_reason": "converged",
            "duration_ms": 0,
            "subagent_usage": {
                "input_tokens": 50,
                "output_tokens": 5,
                "cost_usd": 0.01,
                "cost_source": "reported",
            },
        },
    }
    position = rows.index(child_call) + 1
    rows[position:position] = [nested_start, nested_end]
    result = export(rows).trajectory
    check_document(result)
    child = result["subagent_trajectories"][0]
    grandchild = child["subagent_trajectories"][0]
    assert grandchild["final_metrics"]["total_prompt_tokens"] == 50
    assert child["final_metrics"]["total_prompt_tokens"] == 2050
    assert result["final_metrics"]["total_prompt_tokens"] == 4050
    assert result["final_metrics"]["total_cost_usd"] == pytest.approx(0.028)


def tool_run():
    rows = case("plain-response")
    response = next(e for e in rows if e["type"] == "assistant_message")
    response["data"]["content"] = [
        {"type": "tool_use", "id": "a", "name": "echo", "input": {"text": "A"}},
        {"type": "tool_use", "id": "b", "name": "echo", "input": {"text": "B"}},
    ]
    for call_id in ("b", "a"):
        returned = copy.deepcopy(response)
        returned.update(
            id=f"result-{call_id}",
            type="tool_returned",
            data={
                "tool_call_id": call_id,
                "tool_name": "echo",
                "duration_ms": 1,
                "tool_result": {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": call_id.upper(),
                    "is_error": call_id == "b",
                    "structured_content": {"letter": call_id},
                },
            },
        )
        rows.insert(-1, returned)
    return rows


def test_out_of_order_parallel_results_keep_call_ids_errors_and_structured_content():
    rows = tool_run()
    result = export(rows).trajectory
    check_document(result)
    step = next(s for s in result["steps"] if "tool_calls" in s)
    observations = {r["source_call_id"]: r for r in step["observation"]["results"]}
    assert observations["a"]["content"] == "A"
    assert observations["b"]["content"] == "B"
    assert observations["b"]["extra"]["avp"]["is_error"] is True
    assert observations["a"]["extra"]["avp"]["structured_content"] == {"letter": "a"}
    assert rows[3]["data"]["content"][0]["type"] == "tool_use"  # Input is unchanged.


def test_content_preserves_images_and_does_not_publish_encrypted_reasoning_as_text(tmp_path):
    rows = case("plain-response")
    response = next(e for e in rows if e["type"] == "assistant_message")
    image = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRHsAAAAASUVORK5CYII=",
        },
    }
    response["data"]["content"] = [
        {"type": "thinking", "thinking": "ciphertext", "redacted": True, "signature": "sig"},
        {"type": "thinking", "thinking": "visible reasoning"},
        {"type": "text", "text": "before", "provider_extension": {"annotation": "kept"}},
        image,
        {"type": "text", "text": "after"},
    ]
    result = export(rows)
    step = next(s for s in result.trajectory["steps"] if s["source"] == "agent")
    assert step["reasoning_content"] == "visible reasoning"
    assert step["extra"]["avp"]["reasoning_metadata"] == [
        {"redacted": True, "signature": "sig", "encrypted_content": "ciphertext"}
    ]
    assert step["extra"]["avp"]["message_metadata"] == [
        {"part_index": 0, "annotations": {"provider_extension": {"annotation": "kept"}}}
    ]
    assert [p["type"] for p in step["message"]] == ["text", "image", "text"]
    result.write(tmp_path / "trajectory.json")
    path = tmp_path / step["message"][1]["source"]["path"]
    assert image["source"]["data"] not in json.dumps(result.trajectory)
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    check_document(json.loads((tmp_path / "trajectory.json").read_text()))
    image["source"]["data"] = "not base64!"
    with pytest.raises(ValueError):
        export(rows)


def test_provider_tools_are_in_the_same_step_with_their_results():
    rows = case("plain-response")
    response = next(e for e in rows if e["type"] == "assistant_message")
    response["data"]["content"] = [
        {"type": "server_tool_use", "id": "search", "name": "web_search", "input": {"q": "avp"}},
        {
            "type": "server_tool_result",
            "tool_use_id": "search",
            "name": "web_search",
            "content": {"hits": [1]},
        },
        {"type": "refusal", "refusal": "I cannot complete this task."},
    ]
    result = export(rows).trajectory
    check_document(result)
    step = next(s for s in result["steps"] if s["source"] == "agent")
    assert step["message"] == "I cannot complete this task."
    assert step["tool_calls"][0]["extra"]["avp"]["server_side"]
    assert json.loads(step["observation"]["results"][0]["content"]) == {"hits": [1]}


@pytest.mark.parametrize(
    "content",
    [
        [{"type": "text", "content": "a provider-specific shape"}],
        [{"type": "image", "source": {"type": "url", "url": "https://example.com/a.png"}}],
    ],
)
def test_arbitrary_provider_results_are_preserved_as_json(content):
    rows = case("plain-response")
    response = next(e for e in rows if e["type"] == "assistant_message")
    response["data"]["content"] = [
        {"type": "server_tool_use", "id": "search", "name": "web_search", "input": {}},
        {
            "type": "server_tool_result",
            "tool_use_id": "search",
            "name": "web_search",
            "content": content,
        },
    ]
    result = export(rows).trajectory
    check_document(result)
    step = next(s for s in result["steps"] if s["source"] == "agent")
    assert json.loads(step["observation"]["results"][0]["content"]) == content


def test_truncated_run_is_not_marked_converged_and_has_no_invented_result():
    rows = tool_run()[:-3]
    result = export(rows).trajectory
    check_document(result)
    assert result["extra"]["avp"]["complete"] is False
    assert "stop_reason" not in result["extra"]["avp"]
    assert "observation" not in result["steps"][-1]


@pytest.mark.parametrize(
    "problem",
    [
        "mixed",
        "duplicate-event",
        "missing-agent",
        "unmatched-result",
        "duplicate-call",
        "unknown-scope",
    ],
)
def test_invalid_inputs_fail_visibly(problem):
    rows = tool_run()
    if problem == "mixed":
        rows[-1]["run_id"] = "another-run"
    elif problem == "duplicate-event":
        rows[-1]["id"] = rows[0]["id"]
    elif problem == "missing-agent":
        rows = [e for e in rows if e["type"] != "agent_described"]
    elif problem == "unmatched-result":
        rows[-2]["data"]["tool_result"]["tool_use_id"] = "unknown"
    elif problem == "duplicate-call":
        rows[3]["data"]["content"][1]["id"] = "a"
    elif problem == "unknown-scope":
        rows[3]["data"]["subagent_invocation_id"] = "unknown"
    with pytest.raises(ValueError):
        export(rows)


def test_command_exports_ndjson_and_rejects_unknown_events(tmp_path):
    source, target = tmp_path / "trajectory.ndjson", tmp_path / "export/trajectory.json"
    source.write_text("\n".join(json.dumps(e) for e in tool_run()) + "\n")
    command = [sys.executable, "-m", "avp.utils.atif", str(source), "--out", str(target)]
    subprocess.run(command, check=True)
    compact = json.loads(target.read_text())
    check_document(compact)
    assert "events" not in compact["extra"]["avp"]
    with source.open("a") as file:
        file.write(json.dumps({**tool_run()[-1], "type": "future_event"}) + "\n")
    failed = subprocess.run(command, capture_output=True, text=True)
    assert failed.returncode == 1
    assert "unknown event type" in failed.stderr


def test_long_payloads_are_stored_once():
    rows = tool_run()
    message = "Long distinct payload. " * 1000
    response = next(e for e in rows if e["type"] == "assistant_message")
    response["data"]["content"].insert(0, {"type": "text", "text": message})
    result = export(rows)
    assert json.dumps(result.trajectory).count(message) == 1
    assert "usage" not in next(s for s in result.trajectory["steps"] if s["source"] == "agent")[
        "metrics"
    ].get("extra", {}).get("avp", {})


def test_provider_annotations_and_reasoning_signatures_belong_to_steps():
    rows = case("plain-response")
    response = next(e for e in rows if e["type"] == "assistant_message")
    response["data"]["content"] = [
        {"type": "thinking", "thinking": "first 🧪", "signature": "one"},
        {"type": "text", "text": "middle"},
        {"type": "thinking", "thinking": "second", "signature": "two"},
        {"type": "text", "text": "last", "x/y~z": "long annotation " * 100},
        {
            "type": "tool_use",
            "id": "odd",
            "name": "echo",
            "input": {"source": "agent", "step_id": 1},
        },
    ]
    response["data"]["usage"].update(cost_source="unknown", cost_usd=0)
    result = export(rows)
    step = next(s for s in result.trajectory["steps"] if s["source"] == "agent")
    assert step["reasoning_content"] == "first 🧪\nsecond"
    assert step["extra"]["avp"]["reasoning_metadata"] == [
        {"signature": "one", "start": 0, "end": 7},
        {"signature": "two", "start": 8, "end": 14},
    ]
    assert step["extra"]["avp"]["message_metadata"] == [
        {"part_index": 1, "annotations": {"x/y~z": "long annotation " * 100}}
    ]
    assert step["message"] == [{"type": "text", "text": "middle"}, {"type": "text", "text": "last"}]
    check_document(result.trajectory)


def test_original_commission_and_unused_descriptor_catalog_are_not_archived():
    rows = case("plain-response")
    baseline = export(rows).trajectory
    request = next(e for e in rows if e["type"] == "run_requested")
    request["data"]["commission"] = {"old_wire_format": "discard this original request"}
    descriptor = next(e for e in rows if e["type"] == "agent_described")["data"]["descriptor"]
    descriptor["tools"] = [
        {"name": "unused", "description": "unused catalog entry", "inputSchema": {"type": "object"}}
    ]
    assert export(rows).trajectory == baseline
    encoded = json.dumps(baseline)
    assert all(key not in encoded for key in ('"event_id"', '"event_metadata"', '"event_defaults"'))


def test_final_output_response_identity_and_execution_timing_survive():
    rows = tool_run()
    response = next(e for e in rows if e["type"] == "assistant_message")
    response["data"].update(
        response_model="dated-model", finish_reasons=["tool_use"], duration_ms=42
    )
    response["meta"] = {"trace": "span-1"}
    invoked = {
        **response,
        "id": "invoked",
        "type": "tool_invoked",
        "data": {
            "tool_call_id": "a",
            "tool_name": "echo",
            "tool_input": {"text": "A"},
            "mcp_server_id": "test",
        },
    }
    rows.insert(rows.index(response) + 1, invoked)
    rows[-1]["data"]["output"] = {"answer": 42}
    result = export(rows).trajectory
    check_document(result)
    assert result["extra"]["avp"]["output"] == {"answer": 42}
    assert result["extra"]["avp"]["stopped_at"]
    step = next(s for s in result["steps"] if s["source"] == "agent")
    assert step["model_name"] == "dated-model"
    assert step["extra"]["avp"]["requested_model"] == response["data"]["model"]["id"]
    assert step["extra"]["avp"]["duration_ms"] == 42
    assert step["extra"]["avp"]["finish_reasons"] == ["tool_use"]
    assert step["extra"]["avp"]["annotations"] == {"trace": "span-1"}
    call = next(c for c in step["tool_calls"] if c["tool_call_id"] == "a")
    assert call["extra"]["avp"]["started_at"]
    assert call["extra"]["avp"]["mcp_server_id"] == "test"
    observation = next(r for r in step["observation"]["results"] if r["source_call_id"] == "a")
    assert observation["extra"]["avp"]["duration_ms"] == 1
    assert observation["extra"]["avp"]["finished_at"]


def test_refusals_and_tool_content_annotations_survive():
    rows = tool_run()
    response = next(e for e in rows if e["type"] == "assistant_message")
    response["data"]["content"].append({"type": "refusal", "refusal": "declined"})
    result = next(e for e in rows if e["type"] == "tool_returned")["data"]["tool_result"]
    result["content"] = [
        {
            "type": "text",
            "text": "result",
            "citations": [{"type": "url_citation", "source_url": "https://example.com"}],
        }
    ]
    result["provider_info"] = {"trace": "tool-span"}
    document = export(rows).trajectory
    step = next(s for s in document["steps"] if s["source"] == "agent")
    assert step["extra"]["avp"]["message_metadata"] == [
        {"part_index": 0, "annotations": {"refusal": True}}
    ]
    observation = step["observation"]["results"][0]
    assert observation["extra"]["avp"]["content_metadata"][0]["annotations"]["citations"] == [
        {"type": "url_citation", "source_url": "https://example.com"}
    ]
    assert observation["extra"]["avp"]["provider_metadata"] == {
        "provider_info": {"trace": "tool-span"}
    }
