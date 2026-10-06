"""Seam tests: the stock command line drives `run` end to end over the real
OpenAI Agents SDK loop, with only the model scripted (the SDK's own
`ScriptedModel`, which synthesizes the Responses stream including
`response.completed` with usage). Every emitted line must parse as AVP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agents import ModelProvider
from agents.testing import ScriptedModel, assistant_message, function_call
from agents.usage import InputTokensDetails, OutputTokensDetails, Usage

from avp.agent_cli import main
from avp.trajectory import parse_event
from avp_openai_agents import agent
from avp_openai_agents.agent import describe, run

USAGE = Usage(
    requests=1,
    input_tokens=1000,
    input_tokens_details=InputTokensDetails(cached_tokens=400, cache_write_tokens=0),
    output_tokens=50,
    output_tokens_details=OutputTokensDetails(reasoning_tokens=10),
    total_tokens=1050,
)


class _Provider(ModelProvider):
    def __init__(self, model: ScriptedModel) -> None:
        self.model = model

    def get_model(self, model_name: str | None) -> ScriptedModel:
        return self.model


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch):
    def install(*steps: object) -> ScriptedModel:
        model = ScriptedModel(steps, default_usage=USAGE)
        monkeypatch.setattr(agent, "model_provider", lambda plan: _Provider(model))
        return model

    return install


def _run(tmp_path: Path, **fields: object) -> list[dict]:
    commission = {"schema_version": "0.1", "run_id": "r1", "model": "openai/gpt-4o-mini"}
    commission.update(fields)
    out = tmp_path / "t.jsonl"
    argv = ["run", "--commission", json.dumps(commission), "--out", str(out)]
    assert main(run=run, describe=describe, argv=argv) == 0
    events = [json.loads(line) for line in out.read_text().splitlines()]
    for event in events:
        parse_event(event)
    return events


def _types(events: list[dict]) -> list[str]:
    return [e["type"].removeprefix("avp.") for e in events]


def test_plain_text_turn(script, tmp_path: Path) -> None:
    model = script([assistant_message("DONE")])
    events = _run(tmp_path, prompt="say DONE", system_prompt="be terse")
    assert _types(events) == [
        "run_requested",
        "agent_described",
        "agent_started",
        "assistant_message",
        "agent_stopped",
    ]
    started, msg, stopped = events[2]["data"], events[3]["data"], events[4]["data"]
    assert msg["avp.content"] == [{"type": "text", "text": "DONE"}]
    assert msg["avp.usage"] == {
        "input_tokens": 1000,
        "output_tokens": 50,
        "cache_read_input_tokens": 400,
        "reasoning_output_tokens": 10,
    }
    # 600 fresh * 0.15 + 400 cached * 0.075 + 50 * 0.6, per million tokens.
    assert msg["avp.cost.source"] == "computed"
    assert msg["avp.cost_usd"] == pytest.approx(0.00015)
    # The wire keeps the model that answered; the table lacks it, so the turn is
    # priced as the requested model.
    assert msg["avp.response.model"] == "scripted-model"
    assert msg["avp.request.model"] == "openai/gpt-4o-mini"
    assert stopped == {**stopped, "avp.reason": "converged", "avp.output": "DONE"}
    assert model.first_call.system_instructions == "be terse"


def test_skills_reach_the_instructions(script, tmp_path: Path) -> None:
    model = script([assistant_message("DONE")])
    skill = {"id": "greet", "files": {"SKILL.md": "---\nname: greet\n---\nSay hi."}}
    events = _run(tmp_path, prompt="hi", system_prompt="base", skills=[skill])
    assert events[2]["data"]["avp.skills"] == [{"name": "greet"}]
    assert "Say hi." in model.first_call.system_instructions


def test_unknown_allowlisted_tool_fails_fast(script, tmp_path: Path) -> None:
    model = script()
    events = _run(tmp_path, enabled_builtin_tools={"avp-openai-agents": ["nope"]})
    assert _types(events) == [
        "run_requested",
        "agent_described",
        "error_occurred",
        "agent_stopped",
    ]
    assert events[2]["data"]["avp.error.code"] == "commission_collision"
    assert events[3]["data"]["avp.reason"] == "error"
    assert model.calls == ()


def test_foreign_provider_fails_fast(script, tmp_path: Path) -> None:
    script()
    events = _run(tmp_path, provider={"id": "openrouter"})
    assert events[-2]["data"]["avp.error.code"] == "unsupported_provider"
    assert events[-1]["data"]["avp.reason"] == "error"


def test_refusal_stops_refused(script, tmp_path: Path) -> None:
    from openai.types.responses import ResponseOutputMessage, ResponseOutputRefusal

    refusal = ResponseOutputMessage(
        id="m1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputRefusal(type="refusal", refusal="I can't help with that.")],
    )
    script([refusal])
    events = _run(tmp_path, prompt="something bad")
    assert events[3]["data"]["avp.content"] == [
        {"type": "refusal", "refusal": "I can't help with that."}
    ]
    assert events[-1]["data"]["avp.reason"] == "refused"


TEST_MCP = Path(__file__).resolve().parents[4] / "testing" / "mcp" / "avp_test_mcp.py"


def test_mcp_server_tools_round_trip(script, tmp_path: Path) -> None:
    """The real MCP seam: dial the repo's stdio test server, surface its tools
    with `avp.mcp_server_id`, and dispatch one through the SDK."""
    from agents.testing import ModelStep

    def call_echo(call):
        echo = next(t.name for t in call.tools if "echo" in t.name.lower())
        return [function_call(echo, {"text": "PING"}, call_id="call_1")]

    script(ModelStep.respond(call_echo), [assistant_message("PING")])
    events = _run(
        tmp_path,
        prompt="echo PING",
        enabled_builtin_tools={"avp-openai-agents": []},
        mcp_servers=[{"type": "stdio", "id": "avptest", "command": ["uv", "run", str(TEST_MCP)]}],
    )
    started = events[2]["data"]
    assert started["avp.mcp_servers"] == [{"id": "avptest", "status": "connected"}]
    assert started["avp.tools"] and all(
        t["avp.mcp_server_id"] == "avptest" for t in started["avp.tools"]
    )
    invoked = next(e["data"] for e in events if e["type"] == "avp.tool_invoked")
    returned = next(e["data"] for e in events if e["type"] == "avp.tool_returned")
    assert invoked["avp.tool.dispatch_target"] == "mcp_server"
    assert "PING" in json.dumps(returned["avp.tool_result"]["content"])
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_unreachable_mcp_server_is_reported(script, tmp_path: Path) -> None:
    script([assistant_message("DONE")])
    events = _run(
        tmp_path,
        prompt="hi",
        mcp_servers=[{"type": "stdio", "id": "gone", "command": ["/nonexistent/mcp"]}],
    )
    assert "error_occurred" in _types(events)
    assert events[3]["data"]["avp.mcp_servers"] == [{"id": "gone", "status": "failed"}]
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_ships_no_builtins_and_rejects_allowlisted_names(script, tmp_path: Path) -> None:
    # A framework's agents ship nothing: the descriptor and agent_started
    # declare no tools / subagents, empty allow-lists are fine, and any
    # allow-listed name is a collision.
    script([assistant_message("DONE")])
    events = _run(
        tmp_path,
        prompt="hi",
        enabled_builtin_tools={"avp-openai-agents": []},
        enabled_builtin_subagents={"avp-openai-agents": []},
    )
    described, started = events[1]["data"]["avp.descriptor"], events[2]["data"]
    assert "tools" not in described and "subagents" not in described
    assert started.get("avp.tools", []) == []
    assert events[-1]["data"]["avp.reason"] == "converged"
