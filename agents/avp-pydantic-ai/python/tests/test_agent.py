"""The agent's command line runs `run` end to end over the real Pydantic AI loop,
with only the model scripted (Pydantic AI's `FunctionModel`). Every event must
parse as a Trajectory event."""

import asyncio
import json
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from anthropic import AsyncAnthropic
from pydantic import TypeAdapter
from pydantic_ai import (
    FinishReason,
    ModelHTTPError,
    ModelResponse,
    ModelResponsePart,
    RequestUsage,
    TextPart,
    ThinkingPart,
    ToolCallPart,
)
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel

from avp.agent_cli import main
from avp.commission import Commission
from avp.trajectory import Event
from avp_pydantic_ai import agent
from avp_pydantic_ai import commission as cm
from avp_pydantic_ai.cli import describe, run

TEST_MCP = Path(__file__).resolve().parents[4] / "testing" / "mcp" / "avp_test_mcp.py"
USAGE = RequestUsage(input_tokens=1000, output_tokens=50, cache_read_tokens=400)
MODEL = {"provider": "anthropic", "id": "claude-haiku-4-5"}
EVENT = TypeAdapter(Event)
Step = ModelResponse | Exception | Callable[[], Awaitable[ModelResponse]]
"""A scripted model's answer: a response, an error to raise, or a coroutine."""


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch):
    """Install a model that answers with each response in turn, recording the
    messages and tools it was given."""

    def install(*responses: Step) -> list[tuple[list, AgentInfo]]:
        seen: list[tuple[list, AgentInfo]] = []

        async def respond(messages: list, info: AgentInfo) -> ModelResponse:
            seen.append((messages, info))
            step = responses[len(seen) - 1]
            if isinstance(step, Exception):
                raise step
            if isinstance(step, ModelResponse):
                return step
            return await step()

        monkeypatch.setattr(agent, "model", lambda c: FunctionModel(respond, model_name="scripted"))
        return seen

    return install


def _reply(*parts: ModelResponsePart, finish: FinishReason | None = "stop") -> ModelResponse:
    return ModelResponse(
        parts=list(parts), usage=USAGE, model_name="scripted", finish_reason=finish
    )


def _run(tmp_path: Path, exit_code: int = 0, **fields: object) -> list[dict]:
    commission = {"avp_version": "0.1", "run_id": "r1", "model": MODEL, "prompt": "hi"}
    commission.update(fields)
    out = tmp_path / "t.ndjson"
    argv = ["run", "--commission", json.dumps(commission), "--out", str(out)]
    assert main(run=run, describe=describe, argv=argv) == exit_code
    events = [json.loads(line) for line in out.read_text().splitlines()]
    for event in events:
        EVENT.validate_python(event)
    return events


def _types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


def test_plain_text_response(script, tmp_path: Path) -> None:
    seen = script(_reply(ThinkingPart("short", signature="sig"), TextPart("DONE")))
    events = _run(tmp_path, prompt="say DONE", system_prompt="be terse")
    assert _types(events) == [
        "run_requested",
        "agent_described",
        "agent_started",
        "assistant_message",
        "agent_stopped",
    ]
    message, stopped = events[3]["data"], events[4]["data"]
    assert message["content"] == [
        {"type": "thinking", "thinking": "short", "signature": "sig"},
        {"type": "text", "text": "DONE"},
    ]
    usage = message["usage"]
    assert (usage["input_tokens"], usage["output_tokens"]) == (1000, 50)
    assert usage["cache_read_input_tokens"] == 400
    assert usage["cost_source"] == "computed"
    assert message["model"] == MODEL
    assert message["response_model"] == "scripted"
    assert stopped == {"reason": "converged", "output": "DONE"}
    assert seen[0][0][0].instructions == "be terse"


def _results(events: list[dict]) -> dict[str, dict]:
    return {
        e["data"]["tool_call_id"]: e["data"]["tool_result"]
        for e in events
        if e["type"] == "tool_returned"
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
    events = _run(tmp_path, mcp_servers=[server])
    assert _types(events).count("assistant_message") == 2
    started = events[2]["data"]
    assert started["mcp_servers"] == [{"id": "t", "status": "connected"}]
    add = next(t for t in started["tools"] if t["name"] == "Avptest_Add")
    assert add["mcp_server_id"] == "t" and add["description"] and add["inputSchema"]
    invoked = [e["data"] for e in events if e["type"] == "tool_invoked"]
    assert {i["mcp_server_id"] for i in invoked} == {"t"}
    results = _results(events)
    assert set(results) == {"c_add", "c_result", "c_proto"}
    for call, text, failed in [
        ("c_add", "5", False),
        ("c_result", "BAD-RESULT", True),
        ("c_proto", "BAD-PROTO", True),
    ]:
        assert text in json.dumps(results[call]["content"]), call
        assert bool(results[call].get("is_error")) is failed, call
    assert events[-1]["data"]["reason"] == "converged"
    assert {t.name for t in seen[0][1].function_tools} >= {"Avptest_Add", fail}


def test_a_server_that_fails_to_connect_stops_the_run(script, tmp_path: Path) -> None:
    seen = script()
    server = {"id": "broken", "type": "stdio", "command": [sys.executable, "-c", "exit(1)"]}
    events = _run(tmp_path, mcp_servers=[server])
    assert _types(events) == ["run_requested", "agent_described", "error_occurred"]
    assert events[2]["data"]["error_code"] == "mcp_connect_failed"
    assert events[2]["data"]["error_message"].startswith("broken:")
    assert seen == []


def test_output_schema_ends_on_the_output_tool(script, tmp_path: Path) -> None:
    script(_reply(ToolCallPart("final_result", {"answer": 3}, tool_call_id="o1")))
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
    events = _run(tmp_path, output_schema=schema)
    assert _types(events)[3:] == [
        "assistant_message",
        "tool_invoked",
        "tool_returned",
        "agent_stopped",
    ]
    assert events[-1]["data"]["output"] == {"answer": 3}


def test_skills_reach_the_instructions(script, tmp_path: Path) -> None:
    seen = script(_reply(TextPart("hi")))
    skill = {
        "name": "greet",
        "files": {"SKILL.md": "---\nname: greet\ndescription: Greet people.\n---\nSay hi."},
    }
    events = _run(tmp_path, system_prompt="base", skills=[skill])
    assert events[2]["data"]["skills"] == [{"name": "greet", "description": "Greet people."}]
    assert "Say hi." in seen[0][0][0].instructions


def test_rate_limit_ends_the_run(script, tmp_path: Path) -> None:
    script(ModelHTTPError(429, "claude-haiku-4-5", {"error": "slow down"}))
    events = _run(tmp_path)
    assert _types(events)[-2:] == ["error_occurred", "agent_stopped"]
    assert events[-2]["data"]["error_code"] == "rate_limit"
    assert events[-1]["data"]["reason"] == "error"


def test_content_filter_is_a_refusal(script, tmp_path: Path) -> None:
    script(_reply(TextPart("I can't help with that."), finish="content_filter"))
    events = _run(tmp_path, prompt="something bad")
    assert events[-1]["data"]["reason"] == "refused"


def test_sigterm_stops_interrupted(script, tmp_path: Path) -> None:
    """SIGTERM during a model call: the command line cancels the run and the
    Trajectory ends `interrupted`."""

    async def hang() -> ModelResponse:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(60)
        raise AssertionError("not cancelled")

    script(hang)
    events = _run(tmp_path, exit_code=130)
    assert _types(events)[-1] == "agent_stopped"
    assert events[-1]["data"]["reason"] == "interrupted"


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"agents": {"avp-pydantic-ai": {"enabled_tools": ["bash"]}}}, "invalid_commission"),
        ({"model": {"provider": "mistral", "id": "mistral-large"}}, "invalid_commission"),
    ],
)
def test_commissions_it_cannot_run_end_before_start(
    script, tmp_path: Path, fields: dict, code: str
) -> None:
    seen = script()
    events = _run(tmp_path, **fields)
    assert _types(events) == ["run_requested", "agent_described", "error_occurred"]
    assert events[2]["data"]["error_code"] == code
    assert seen == []


def test_a_missing_env_credential_ends_before_start(tmp_path: Path) -> None:
    events = _run(tmp_path, model={**MODEL, "credential": {"env": "AVP_TEST_UNSET_KEY"}})
    assert _types(events) == ["run_requested", "agent_described", "error_occurred"]
    assert events[2]["data"]["error_code"] == "auth_error"


def _commission(**fields: object) -> Commission:
    return Commission.model_validate(
        {"avp_version": "0.1", "run_id": "r1", "model": MODEL, "prompt": "hi", **fields}
    )


def test_a_proxy_credential_sends_a_stand_in_key() -> None:
    model = cm.model(_commission(model={**MODEL, "credential": {"proxy": "anthropic-key"}}))
    assert isinstance(model, AnthropicModel) and isinstance(model.client, AsyncAnthropic)
    assert model.client.api_key == cm.STAND_IN_KEY


def test_an_env_credential_reads_the_variable(monkeypatch) -> None:
    monkeypatch.setenv("AVP_TEST_KEY", "sk-test")
    model = cm.model(_commission(model={**MODEL, "credential": {"env": "AVP_TEST_KEY"}}))
    assert isinstance(model, AnthropicModel) and isinstance(model.client, AsyncAnthropic)
    assert model.client.api_key == "sk-test"


def test_mcp_headers_leave_proxy_secrets_out(monkeypatch) -> None:
    monkeypatch.setenv("AVP_TEST_TOKEN", "Bearer t")
    servers = _commission(
        mcp_servers=[
            {
                "id": "docs",
                "type": "http",
                "url": "https://mcp.example.com",
                "headers": {
                    "X-Plain": "1",
                    "X-Env": {"env": "AVP_TEST_TOKEN"},
                    "Authorization": {"proxy": "docs-token"},
                },
            }
        ]
    ).mcp_servers
    assert servers is not None
    transport = cm.mcp_toolset(servers[0]).client.transport
    assert transport.headers == {"X-Plain": "1", "X-Env": "Bearer t"}


@pytest.mark.parametrize("provider", sorted(cm.PROVIDERS))
def test_every_described_provider_builds_a_model(provider: str) -> None:
    model = cm.model(
        _commission(model={"provider": provider, "id": "m", "credential": {"proxy": "key"}})
    )
    assert model.model_name == "m"


def test_raise_sse_event_limit_passes_the_cap_when_the_sdk_has_one(monkeypatch) -> None:
    import functools

    from fastmcp.client.transports import http

    seen = {}

    def limited(url, *, http_client=None, max_sse_event_size=1024 * 1024):
        seen["max"] = max_sse_event_size

    monkeypatch.setattr(http, "streamable_http_client", limited)
    assert cm.raise_sse_event_limit() is True
    assert isinstance(http.streamable_http_client, functools.partial)
    http.streamable_http_client("http://x")
    assert seen["max"] == cm.MAX_SSE_EVENT_BYTES
    assert cm.raise_sse_event_limit() is True


def test_raise_sse_event_limit_is_a_no_op_without_the_setting(monkeypatch) -> None:
    from fastmcp.client.transports import http

    def unlimited(url, *, http_client=None):
        return None

    monkeypatch.setattr(http, "streamable_http_client", unlimited)
    assert cm.raise_sse_event_limit() is False
    assert http.streamable_http_client is unlimited
