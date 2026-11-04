"""The real Agents Runner, a scripted model, and native MCP cross into wire events."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from agents.usage import InputTokensDetails, OutputTokensDetails, Usage
from pydantic import TypeAdapter

from avp.agent_cli import main
from avp.trajectory import Event
from avp_openai_agents import agent
from avp_openai_agents.descriptor import describe

MODEL = {"provider": "openai", "id": "gpt-5-mini"}
FIXTURE = Path(__file__).resolve().parents[4] / "testing/mcp/avp_test_mcp.py"
USAGE = Usage(
    requests=1,
    input_tokens=1000,
    input_tokens_details=InputTokensDetails(cached_tokens=400, cache_write_tokens=0),
    output_tokens=50,
    output_tokens_details=OutputTokensDetails(reasoning_tokens=10),
    total_tokens=1050,
)


@pytest.fixture
def script(monkeypatch):
    def install(*steps):
        model = ScriptedModel(steps, default_usage=USAGE)
        monkeypatch.setattr(agent, "model", lambda commission: model)
        return model

    return install


def run_cli(tmp_path, **fields):
    received = {
        "avp_version": "0.1",
        "run_id": "test",
        "model": MODEL,
        "prompt": "Say DONE",
        **fields,
    }
    out = tmp_path / "trajectory.ndjson"
    code = main(
        run=agent.run,
        describe=describe,
        argv=["run", "--commission", json.dumps(received), "--out", str(out)],
    )
    events = [json.loads(line) for line in out.read_text().splitlines()]
    for event in events:
        TypeAdapter(Event).validate_python(event)
    return code, events


def fixture(tmp_path, **fields):
    return run_cli(
        tmp_path,
        mcp_servers=[{"type": "stdio", "id": "fixture", "command": [sys.executable, str(FIXTURE)]}],
        **fields,
    )


def test_native_text_response_and_instructions(script, tmp_path):
    model = script([assistant_message("DONE")])
    _, events = run_cli(
        tmp_path,
        system_prompt="SYSTEM",
        skills=[
            {
                "name": "hello",
                "files": {
                    "SKILL.md": "---\nname: hello\ndescription: Hello\n---\nGREETING",
                    "support.txt": "SUPPORT",
                },
            }
        ],
    )
    assert [e["type"] for e in events] == [
        "run_requested",
        "agent_described",
        "agent_started",
        "assistant_message",
        "agent_stopped",
    ]
    usage = events[3]["data"]["usage"]
    assert usage["input_tokens"] == 1000 and usage["output_tokens"] == 50
    assert usage["cache_read_input_tokens"] == 400 and usage["reasoning_output_tokens"] == 10
    assert "SYSTEM" in model.first_call.system_instructions
    assert "SUPPORT" in model.first_call.system_instructions
    assert events[-1]["data"] == {"reason": "converged", "output": "DONE"}


@pytest.mark.parametrize(
    "fields",
    [
        {"agents": {"other": {}}},
        {"agents": {"avp-openai-agents": {"enabled_tools": ["missing"]}}},
        {"model": {"provider": "google", "id": "gemini-2.5-flash"}},
    ],
)
def test_invalid_commissions_are_refused_by_sdk(script, tmp_path, fields):
    model = script()
    _, events = run_cli(tmp_path, **fields)
    assert [e["type"] for e in events] == ["run_requested", "agent_described", "error_occurred"]
    assert events[-1]["data"]["error_code"] == "invalid_commission"
    assert not model.calls


@pytest.mark.parametrize("mode", ["one", "parallel", "errors"])
def test_native_mcp_tools_and_error_results_pair(script, tmp_path, mode):
    def choose(call):
        name = next(t.name for t in call.tools if t.name.endswith("Avptest_Echo"))
        calls = [function_call(name, {"text": "BOUNDARY"}, call_id="one")]
        if mode == "parallel":
            calls.append(function_call(name, {"text": "SECOND"}, call_id="two"))
        if mode == "errors":
            fail = next(t.name for t in call.tools if t.name.endswith("Avptest_Fail"))
            calls += [
                function_call(fail, {"message": "BAD-RESULT", "mode": "result"}, call_id="result"),
                function_call(
                    fail, {"message": "BAD-PROTOCOL", "mode": "protocol"}, call_id="protocol"
                ),
            ]
        return calls

    script(ModelStep.respond(choose), [assistant_message("DONE")])
    _, events = fixture(tmp_path)
    responses = [e for e in events if e["type"] == "assistant_message"]
    assert len(responses) == 2
    assert [e["data"]["usage"]["input_tokens"] for e in responses] == [1000, 1000]
    results = {e["data"]["tool_call_id"]: e["data"] for e in events if e["type"] == "tool_returned"}
    invoked = {e["data"]["tool_call_id"]: e["data"] for e in events if e["type"] == "tool_invoked"}
    assert set(results) == set(invoked)
    assert all(e["mcp_server_id"] == "fixture" for e in invoked.values())
    assert "BOUNDARY" in str(results["one"]["tool_result"]["content"])
    if mode == "parallel":
        assert "SECOND" in str(results["two"]["tool_result"]["content"])
    if mode == "errors":
        assert results["result"]["tool_result"]["is_error"] is True
        assert results["protocol"]["tool_result"]["is_error"] is True
    assert events[-1]["data"]["reason"] == "converged"


def test_mcp_failure_never_starts_the_model(script, tmp_path):
    model = script()
    _, events = run_cli(
        tmp_path, mcp_servers=[{"id": "missing", "type": "stdio", "command": ["/nonexistent/mcp"]}]
    )
    assert events[-1]["data"]["error_code"] == "mcp_connect_failed"
    assert not model.calls


def test_schema_validation_crosses_native_runner(script, tmp_path):
    script([assistant_message('{"answer":42}')])
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "integer"}},
    }
    _, events = run_cli(tmp_path, output_schema=schema)
    assert events[-1]["data"]["output"] == {"answer": 42}
    script([assistant_message('{"answer":"wrong"}')])
    _, events = run_cli(tmp_path, output_schema=schema)
    assert events[-2]["data"]["error_code"] == "output_invalid"
    assert events[-1]["data"]["reason"] == "error"


def test_missing_secret_is_an_auth_error(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_AVP_KEY", raising=False)
    _, events = run_cli(tmp_path, model={**MODEL, "credential": {"env": "MISSING_AVP_KEY"}})
    assert events[-1]["data"]["error_code"] == "auth_error"


def test_native_refusal_stops_refused(script, tmp_path):
    from openai.types.responses import ResponseOutputMessage, ResponseOutputRefusal

    script(
        [
            ResponseOutputMessage(
                id="refusal",
                type="message",
                role="assistant",
                status="completed",
                content=[ResponseOutputRefusal(type="refusal", refusal="Declined")],
            )
        ]
    )
    _, events = run_cli(tmp_path)
    assert events[-1]["data"]["reason"] == "refused"
    assert events[3]["data"]["content"] == [{"type": "refusal", "refusal": "Declined"}]


def test_provider_quota_error_is_reported(script, tmp_path):
    import httpx2
    from openai import APIError

    script(
        APIError(
            "You have no credits remaining.",
            httpx2.Request("POST", "https://api.openai.com/v1/responses"),
            body=None,
        )
    )
    _, events = run_cli(tmp_path)
    assert events[-2]["data"]["error_code"] == "rate_limit"
    assert events[-1]["data"]["reason"] == "error"


def test_ping_and_descriptor_are_lazy():
    for verb in ["ping", "describe"]:
        value = json.loads(
            subprocess.check_output(
                [sys.executable, "-m", "avp_openai_agents.cli", verb], text=True
            )
        )
        assert (
            value["type"] == "pong"
            if verb == "ping"
            else value["agent_name"] == "avp-openai-agents"
        )
