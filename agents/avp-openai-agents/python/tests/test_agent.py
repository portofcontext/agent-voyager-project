"The real Agents Runner, a scripted model, and native MCP cross into wire events."

import json
import subprocess
import sys
from pathlib import Path

import assertions as atif
import pytest
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from agents.usage import InputTokensDetails, OutputTokensDetails, Usage

from avp.agent_cli import main
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
    out = tmp_path / "trajectory.json"
    code = main(
        run=agent.run,
        describe=describe,
        argv=["run", "--commission", json.dumps(received), "--out", str(out)],
    )
    events = atif.load(out)
    return (code, events)


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
    assert (
        len(atif.responses(events)),
        len(atif.calls(events)),
        len(atif.errors(events)),
        atif.meta(events)["complete"],
    ) == (1, 0, 0, True)
    usage = atif.responses(events)[0]["metrics"]
    assert usage["prompt_tokens"] == 1000 and usage["completion_tokens"] == 50
    assert usage["cached_tokens"] == 400 and atif.meta(usage)["reasoning_output_tokens"] == 10
    assert "SYSTEM" in model.first_call.system_instructions
    assert "SUPPORT" in model.first_call.system_instructions
    assert {
        "reason": atif.meta(events).get("stop_reason"),
        "output": atif.meta(events).get("output"),
    } == {"reason": "converged", "output": "DONE"}


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
    assert (
        len(atif.responses(events)),
        len(atif.calls(events)),
        len(atif.errors(events)),
        atif.meta(events)["complete"],
    ) == (0, 0, 1, True)
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "invalid_commission"
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
    responses = atif.responses(events)
    assert len(responses) == 2
    assert [e["metrics"]["prompt_tokens"] for e in responses] == [1000, 1000]
    results = {e["source_call_id"]: e for e in atif.results(events)}
    invoked = {e["tool_call_id"]: e for e in atif.calls(events)}
    assert set(results) == set(invoked)
    assert all(atif.meta(e)["mcp_server_id"] == "fixture" for e in invoked.values())
    assert "BOUNDARY" in str(results["one"]["content"])
    if mode == "parallel":
        assert "SECOND" in str(results["two"]["content"])
    if mode == "errors":
        assert atif.meta(results["result"])["is_error"] is True
        assert atif.meta(results["protocol"])["is_error"] is True
    assert atif.meta(events)["stop_reason"] == "converged"


def test_mcp_failure_never_starts_the_model(script, tmp_path):
    model = script()
    _, events = run_cli(
        tmp_path, mcp_servers=[{"id": "missing", "type": "stdio", "command": ["/nonexistent/mcp"]}]
    )
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "mcp_connect_failed"
    assert not model.calls


def test_schema_validation_crosses_native_runner(script, tmp_path):
    script([assistant_message('{"answer":42}')])
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "integer"}},
    }
    _, events = run_cli(tmp_path, output_schema=schema)
    assert atif.meta(events)["output"] == {"answer": 42}
    script([assistant_message('{"answer":"wrong"}')])
    _, events = run_cli(tmp_path, output_schema=schema)
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "output_invalid"
    assert atif.meta(events)["stop_reason"] == "error"


def test_missing_secret_is_an_auth_error(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_AVP_KEY", raising=False)
    _, events = run_cli(tmp_path, model={**MODEL, "credential": {"env": "MISSING_AVP_KEY"}})
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "auth_error"


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
    assert atif.meta(events)["stop_reason"] == "refused"
    assert atif.responses(events)[0]["message"] == "Declined"
    assert atif.meta(atif.responses(events)[0])["message_metadata"][0]["annotations"]["refusal"]


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
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "rate_limit"
    assert atif.meta(events)["stop_reason"] == "error"


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
