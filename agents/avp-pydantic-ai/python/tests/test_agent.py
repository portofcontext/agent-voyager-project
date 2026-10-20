"""Integration tests: the stock command line drives `run` end to end over the real
Pydantic AI loop, with only the model scripted (Pydantic AI's own
`FunctionModel`). Every emitted line must parse as AVP."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import pytest
from pydantic_ai import (
    ModelHTTPError,
    ModelResponse,
    RequestUsage,
    TextPart,
    ThinkingPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from avp.agent_cli import main
from avp.trajectory import parse_event
from avp_pydantic_ai import agent
from avp_pydantic_ai.agent import describe, run

TEST_MCP = Path(__file__).resolve().parents[4] / "testing" / "mcp" / "avp_test_mcp.py"
USAGE = RequestUsage(input_tokens=1000, output_tokens=50, cache_read_tokens=400)


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch):
    """Install a model that answers with each response in turn, recording the
    messages and tools it was given."""

    def install(*responses: object) -> list[tuple[list, AgentInfo]]:
        seen: list[tuple[list, AgentInfo]] = []

        async def respond(messages: list, info: AgentInfo) -> ModelResponse:
            seen.append((messages, info))
            step = responses[len(seen) - 1]
            if isinstance(step, Exception):
                raise step
            if callable(step):
                return await step()
            return step

        monkeypatch.setattr(agent, "model", lambda c: FunctionModel(respond, model_name="scripted"))
        return seen

    return install


def _reply(*parts: object, finish: str | None = "stop") -> ModelResponse:
    return ModelResponse(
        parts=list(parts), usage=USAGE, model_name="scripted", finish_reason=finish
    )


def _run(tmp_path: Path, exit_code: int = 0, **fields: object) -> list[dict]:
    commission = {"schema_version": "0.1", "run_id": "r1", "model": "anthropic/claude-haiku-4-5"}
    commission.update(fields)
    out = tmp_path / "t.jsonl"
    argv = ["run", "--commission", json.dumps(commission), "--out", str(out)]
    assert main(run=run, describe=describe, argv=argv) == exit_code
    events = [json.loads(line) for line in out.read_text().splitlines()]
    for event in events:
        parse_event(event)
    return events


def _types(events: list[dict]) -> list[str]:
    return [e["type"].removeprefix("avp.") for e in events]


def test_plain_text_turn(script, tmp_path: Path) -> None:
    seen = script(_reply(ThinkingPart("short", signature="sig"), TextPart("DONE")))
    events = _run(tmp_path, prompt="say DONE", system_prompt="be terse")
    assert _types(events) == [
        "run_requested",
        "agent_described",
        "agent_started",
        "assistant_message",
        "agent_stopped",
    ]
    msg, stopped = events[3]["data"], events[4]["data"]
    assert msg["avp.content"] == [
        {"type": "thinking", "thinking": "short", "signature": "sig"},
        {"type": "text", "text": "DONE"},
    ]
    assert msg["avp.usage"] == {
        "input_tokens": 1000,
        "output_tokens": 50,
        "cache_read_input_tokens": 400,
    }
    assert msg["avp.cost.source"] == "computed"
    assert msg["avp.response.model"] == "scripted"
    assert msg["avp.request.model"] == "anthropic/claude-haiku-4-5"
    assert stopped == {**stopped, "avp.reason": "converged", "avp.output": "DONE"}
    assert seen[0][0][0].instructions == "be terse"


def _results(events: list[dict]) -> dict[str, dict]:
    return {
        e["data"]["avp.tool.call_id"]: e["data"]["avp.tool_result"]
        for e in events
        if e["type"] == "avp.tool_returned"
    }


def test_mcp_calls_each_carry_their_own_result(script, tmp_path: Path) -> None:
    """Three calls in one response against a real stdio MCP server: an add and
    both ways an MCP tool fails. Only the failures are errors."""
    fail = "Avptest_Fail"
    seen = script(
        _reply(
            ToolCallPart("Avptest_Add", {"a": 2, "b": 3}, tool_call_id="c_add"),
            ToolCallPart(
                fail, {"message": "BAD-RESULT", "mode": "result"}, tool_call_id="c_result"
            ),
            ToolCallPart(
                fail, {"message": "BAD-PROTO", "mode": "protocol"}, tool_call_id="c_proto"
            ),
        ),
        _reply(TextPart("5")),
    )
    server = {"id": "t", "type": "stdio", "command": [sys.executable, str(TEST_MCP)]}
    events = _run(tmp_path, prompt="add", mcp_servers=[server])
    assert _types(events).count("assistant_message") == 2, "one turn per model response"
    started = events[2]["data"]
    assert started["avp.mcp_servers"] == [{"id": "t", "status": "connected"}]
    add = next(t for t in started["avp.tools"] if t["name"] == "Avptest_Add")
    assert add["avp.mcp_server_id"] == "t" and add["description"] and add["inputSchema"]
    results = _results(events)
    assert set(results) == {"c_add", "c_result", "c_proto"}
    for call, text, failed in [
        ("c_add", "5", False),
        ("c_result", "BAD-RESULT", True),
        ("c_proto", "BAD-PROTO", True),
    ]:
        assert text in json.dumps(results[call]["content"]), call
        assert bool(results[call].get("is_error")) is failed, call
    assert events[-1]["data"]["avp.reason"] == "converged"
    assert {t.name for t in seen[0][1].function_tools} >= {"Avptest_Add", fail}


def test_output_schema_ends_on_the_output_tool(script, tmp_path: Path) -> None:
    script(_reply(ToolCallPart("final_result", {"answer": 3}, tool_call_id="o1")))
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
    events = _run(tmp_path, prompt="3", output_schema=schema)
    assert _types(events)[3:] == [
        "assistant_message",
        "tool_invoked",
        "tool_returned",
        "agent_stopped",
    ]
    assert events[-1]["data"]["avp.output"] == {"answer": 3}


def test_skills_reach_the_instructions(script, tmp_path: Path) -> None:
    seen = script(_reply(TextPart("hi")))
    skill = {"id": "greet", "files": {"SKILL.md": "---\nname: greet\n---\nSay hi."}}
    events = _run(tmp_path, prompt="hi", system_prompt="base", skills=[skill])
    assert events[2]["data"]["avp.skills"] == [{"name": "greet"}]
    assert "Say hi." in seen[0][0][0].instructions


def test_rate_limit_ends_the_run(script, tmp_path: Path) -> None:
    script(ModelHTTPError(429, "claude-haiku-4-5", {"error": "slow down"}))
    events = _run(tmp_path, prompt="hi")
    assert _types(events)[-2:] == ["error_occurred", "agent_stopped"]
    assert events[-2]["data"]["avp.error.code"] == "rate_limit"
    assert events[-1]["data"]["avp.reason"] == "error"


def test_content_filter_is_a_refusal(script, tmp_path: Path) -> None:
    script(_reply(TextPart("I can't help with that."), finish="content_filter"))
    events = _run(tmp_path, prompt="something bad")
    assert events[-1]["data"]["avp.reason"] == "refused"


def test_sigterm_stops_interrupted(script, tmp_path: Path) -> None:
    """SIGTERM during an inference: the stock entrypoint cancels the run and
    the trajectory closes `interrupted`."""

    async def hang() -> ModelResponse:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(60)
        raise AssertionError("not cancelled")

    script(hang)
    events = _run(tmp_path, exit_code=130, prompt="hi")
    assert _types(events)[-1] == "agent_stopped"
    assert events[-1]["data"]["avp.reason"] == "interrupted"


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"enabled_builtin_tools": {"avp-pydantic-ai": ["bash"]}}, "commission_collision"),
        ({"provider": {"id": "openrouter"}}, "unsupported_provider"),
        ({"model": "mistral/mistral-large"}, "unsupported_model"),
    ],
)
def test_unreachable_commissions_fail_fast(script, tmp_path: Path, fields: dict, code: str) -> None:
    seen = script()
    events = _run(tmp_path, **fields)
    assert _types(events) == ["run_requested", "agent_described", "error_occurred", "agent_stopped"]
    assert events[2]["data"]["avp.error.code"] == code
    assert seen == []


def test_describe_declares_no_built_ins() -> None:
    descriptor = describe()
    assert descriptor.agent_name == "avp-pydantic-ai"
    assert not descriptor.tools and not descriptor.subagents and not descriptor.skills
