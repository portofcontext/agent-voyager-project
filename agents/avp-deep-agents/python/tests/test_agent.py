"""Seam tests: the stock command line drives `run` end to end over the real
Deep Agents loop (`create_deep_agent`, its filesystem backend, its `task`
subagent, real MCP sessions), with only the chat model scripted. Every emitted
line must parse as AVP."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import httpx
import pytest
from conftest import reply

from avp.agent_cli import main
from avp.trajectory import parse_event
from avp_deep_agents.agent import describe, run

TEST_MCP = Path(__file__).resolve().parents[4] / "testing" / "mcp" / "avp_test_mcp.py"
BUILTIN_TOOLS = ["ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "workspace"
    path.mkdir()
    monkeypatch.setenv("AVP_WORKSPACE", str(path))
    return path


def _run(tmp_path: Path, exit_code: int = 0, **fields: object) -> list[dict]:
    commission = {"schema_version": "0.1", "run_id": "r1", "model": "openai/gpt-4o-mini"}
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


def _of(events: list[dict], kind: str) -> list[dict]:
    return [e["data"] for e in events if e["type"] == f"avp.{kind}"]


def test_describe_mirrors_what_deep_agents_ships() -> None:
    descriptor = describe()
    assert [t.name for t in descriptor.tools] == [*BUILTIN_TOOLS, "task"]
    assert all(t.description and t.inputSchema for t in descriptor.tools)
    assert [s.name for s in descriptor.subagents] == ["general-purpose"]


def test_plain_text_turn(script, workspace: Path, tmp_path: Path) -> None:
    model = script(reply("DONE"))
    events = _run(tmp_path, prompt="say DONE", system_prompt="be terse")
    assert _types(events) == [
        "run_requested",
        "agent_described",
        "agent_started",
        "assistant_message",
        "agent_stopped",
    ]
    started, msg, stopped = events[2]["data"], events[3]["data"], events[4]["data"]
    assert [t["name"] for t in started["avp.tools"]] == [*BUILTIN_TOOLS, "task"]
    assert started["avp.subagents"] == [
        {"name": "general-purpose", "description": describe().subagents[0].description}
    ]
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
    assert msg["avp.response.model"] == "gpt-4o-mini-2024-07-18"
    assert msg["avp.request.model"] == "openai/gpt-4o-mini"
    assert msg["avp.response.finish_reasons"] == ["stop"]
    assert stopped == {**stopped, "avp.reason": "converged", "avp.output": "DONE"}
    assert model.requests[0][0].type == "system"
    assert model.requests[0][0].text.startswith("be terse")


def test_file_tool_writes_into_the_workspace(script, workspace: Path, tmp_path: Path) -> None:
    script(
        reply("", ("call_1", "write_file", {"file_path": "/notes.txt", "content": "OK"})),
        reply("DONE"),
    )
    events = _run(tmp_path, prompt="write notes.txt")
    assert (workspace / "notes.txt").read_text() == "OK"
    invoked, returned = _of(events, "tool_invoked")[0], _of(events, "tool_returned")[0]
    assert invoked["avp.tool.name"] == "write_file"
    assert invoked["avp.tool.dispatch_target"] == "local"
    assert returned["avp.tool_result"]["tool_use_id"] == "call_1"
    assert returned["avp.tool_result"]["is_error"] is False
    assert _types(events)[3:] == [
        "assistant_message",
        "tool_invoked",
        "tool_returned",
        "assistant_message",
        "agent_stopped",
    ]


def test_parallel_tool_calls_pair_by_id(script, workspace: Path, tmp_path: Path) -> None:
    script(
        reply(
            "",
            ("a", "write_file", {"file_path": "/a.txt", "content": "A"}),
            ("b", "write_file", {"file_path": "/b.txt", "content": "B"}),
            ("c", "read_file", {"file_path": "/missing.txt"}),
            ("d", "no_such_tool", {}),
        ),
        reply("DONE"),
    )
    events = _run(tmp_path, prompt="write two files")
    assert (workspace / "a.txt").read_text() == "A" and (workspace / "b.txt").read_text() == "B"
    assert [e["avp.tool.call_id"] for e in _of(events, "tool_invoked")] == ["a", "b", "c", "d"]
    results = {r["avp.tool.call_id"]: r["avp.tool_result"] for r in _of(events, "tool_returned")}
    assert set(results) == {"a", "b", "c", "d"}
    assert not results["a"]["is_error"] and not results["b"]["is_error"]
    # A tool error the tool reports, and a call the agent rejects without
    # running anything, both close as errors.
    assert results["c"]["is_error"] and results["d"]["is_error"]
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_mcp_server_tools_round_trip(script, workspace: Path, tmp_path: Path) -> None:
    tool = "mcp__avptest__Avptest_Echo"
    model = script(reply("", ("call_1", tool, {"text": "PING"})), reply("PING"))
    events = _run(
        tmp_path,
        prompt="echo PING",
        enabled_builtin_tools={"avp-deep-agents": []},
        mcp_servers=[
            {"type": "stdio", "id": "avptest", "command": [sys.executable, str(TEST_MCP)]}
        ],
    )
    started = events[2]["data"]
    assert started["avp.mcp_servers"] == [{"id": "avptest", "status": "connected"}]
    assert {t["name"] for t in started["avp.tools"]} == {tool, "mcp__avptest__Avptest_Add"}
    assert all(t["avp.mcp_server_id"] == "avptest" for t in started["avp.tools"])
    assert sorted(model.tool_sets[0]) == sorted(t["name"] for t in started["avp.tools"])
    invoked, returned = _of(events, "tool_invoked")[0], _of(events, "tool_returned")[0]
    assert invoked["avp.tool.dispatch_target"] == "mcp_server"
    assert returned["avp.tool_result"]["is_error"] is False
    assert "PING" in json.dumps(returned["avp.tool_result"]["content"])
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_unreachable_mcp_server_is_reported(script, workspace: Path, tmp_path: Path) -> None:
    script(reply("DONE"))
    events = _run(
        tmp_path,
        prompt="hi",
        mcp_servers=[{"type": "stdio", "id": "gone", "command": ["/nonexistent/mcp"]}],
    )
    assert _types(events)[2:4] == ["error_occurred", "agent_started"]
    assert events[2]["data"]["avp.error.code"] == "mcp_connect_failed"
    assert events[3]["data"]["avp.mcp_servers"] == [{"id": "gone", "status": "failed"}]
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_task_subagent_round_trip(script, workspace: Path, tmp_path: Path) -> None:
    """The child's inferences and tool calls stay inside its frame: its spend
    rolls up onto `subagent_returned`, and its file still lands in the
    workspace."""
    model = script(
        reply(
            "", ("task_1", "task", {"description": "say PONG", "subagent_type": "general-purpose"})
        ),
        reply("", ("child_1", "write_file", {"file_path": "/child.txt", "content": "C"})),
        reply("PONG"),
        reply("PONG"),
    )
    events = _run(tmp_path, prompt="delegate")
    assert (workspace / "child.txt").read_text() == "C"
    assert _types(events)[3:] == [
        "assistant_message",
        "tool_invoked",
        "subagent_invoked",
        "subagent_returned",
        "tool_returned",
        "assistant_message",
        "agent_stopped",
    ]
    turn = events[3]["data"]
    invoked, returned = _of(events, "subagent_invoked")[0], _of(events, "subagent_returned")[0]
    assert invoked["avp.subagent.name"] == "general-purpose"
    assert invoked["avp.subagent.invocation_id"] == "task_1"
    assert invoked["parent_span_id"] == turn["span_id"]
    assert returned["span_id"] == invoked["span_id"]
    assert returned["avp.subagent.reason"] == "converged"
    assert returned["avp.subagent.result.text"] == "PONG"
    assert returned["avp.subagent.usage"] == {
        "turns": 2,
        "tokens_input": 2000,
        "tokens_output": 100,
        "cost_usd": pytest.approx(0.0003),
    }
    result = _of(events, "tool_returned")[0]["avp.tool_result"]
    assert result == {**result, "tool_use_id": "task_1", "content": "PONG", "is_error": False}
    assert len(model.requests) == 4


def test_empty_allowlists_hide_builtins_and_block_calls(
    script, workspace: Path, tmp_path: Path
) -> None:
    model = script(
        reply("", ("call_1", "write_file", {"file_path": "/x.txt", "content": "X"})),
        reply("DONE"),
    )
    events = _run(
        tmp_path,
        prompt="hi",
        enabled_builtin_tools={"avp-deep-agents": []},
        enabled_builtin_subagents={"avp-deep-agents": []},
    )
    started = events[2]["data"]
    assert started["avp.tools"] == [] and started["avp.subagents"] == []
    assert not any(model.tool_sets)  # no tools bound at all
    # A call the model makes anyway is rejected, not run.
    assert not (workspace / "x.txt").exists()
    returned = _of(events, "tool_returned")[0]["avp.tool_result"]
    assert returned["tool_use_id"] == "call_1" and returned["is_error"] is True
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_allowlist_keeps_named_tools(script, workspace: Path, tmp_path: Path) -> None:
    model = script(reply("DONE"))
    events = _run(
        tmp_path,
        prompt="hi",
        enabled_builtin_tools={"avp-deep-agents": ["read_file", "task"]},
    )
    assert [t["name"] for t in events[2]["data"]["avp.tools"]] == ["read_file", "task"]
    assert model.tool_sets[0] == ["read_file", "task"]


def test_skill_loads_through_deep_agents_skills(script, workspace: Path, tmp_path: Path) -> None:
    body = "---\nname: greet\ndescription: How to greet.\n---\nSay AVP-HELLO."
    model = script(
        reply("", ("call_1", "read_file", {"file_path": "/.avp-skills/greet/SKILL.md"})),
        reply("AVP-HELLO"),
    )
    events = _run(
        tmp_path,
        prompt="greet",
        skills=[{"id": "greet", "files": {"SKILL.md": body, "notes/extra.md": "more"}}],
    )
    assert events[2]["data"]["avp.skills"] == [{"name": "greet", "description": "How to greet."}]
    assert "/.avp-skills/greet/SKILL.md" in model.requests[0][0].text
    assert "Say AVP-HELLO." in json.dumps(_of(events, "tool_returned")[0]["avp.tool_result"])
    # Skill files stay out of the workspace.
    assert list(workspace.iterdir()) == []


def _http_error(cls: type, status: int, body: dict) -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return cls(
        body.get("message", "error"),
        response=httpx.Response(status, request=request),
        body=body,
    )


def _provider_failures() -> list:
    import anthropic
    import openai
    from langchain_google_genai.chat_models import (
        GoogleAPIError,
        GoogleAuthenticationError,
        GoogleInvalidRequestError,
        GoogleRateLimitError,
    )

    return [
        pytest.param(
            _http_error(openai.AuthenticationError, 401, {"message": "Incorrect API key"}),
            "auth_error",
            id="openai-auth",
        ),
        pytest.param(
            _http_error(
                openai.RateLimitError,
                429,
                {"message": "You exceeded your current quota", "code": "insufficient_quota"},
            ),
            "rate_limit",
            id="openai-insufficient-quota",
        ),
        pytest.param(
            _http_error(
                openai.BadRequestError,
                400,
                {"message": "maximum context length", "code": "context_length_exceeded"},
            ),
            "context_limit",
            id="openai-context",
        ),
        pytest.param(
            _http_error(anthropic.AuthenticationError, 401, {"message": "invalid x-api-key"}),
            "auth_error",
            id="anthropic-auth",
        ),
        pytest.param(
            _http_error(anthropic.RateLimitError, 429, {"message": "rate limited"}),
            "rate_limit",
            id="anthropic-rate-limit",
        ),
        pytest.param(
            GoogleAuthenticationError("Error calling model (UNAUTHENTICATED)"),
            "auth_error",
            id="google-auth",
        ),
        pytest.param(
            # What the Gemini API answers an invalid key with: a 400, not a 401.
            GoogleInvalidRequestError(
                "Error calling model 'gemini-3.1-flash-lite' (INVALID_ARGUMENT): 400"
                " INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid."
                " Please pass a valid API key.', 'status': 'INVALID_ARGUMENT', 'details':"
                " [{'reason': 'API_KEY_INVALID', 'domain': 'googleapis.com'}]}}"
            ),
            "auth_error",
            id="google-invalid-key",
        ),
        pytest.param(
            GoogleRateLimitError("429 RESOURCE_EXHAUSTED. You exceeded your current quota"),
            "rate_limit",
            id="google-quota",
        ),
        pytest.param(
            # What a Gemini model out of capacity raises once retries are spent.
            GoogleAPIError(
                code=503,
                response_json={
                    "error": {
                        "code": 503,
                        "message": "This model is currently experiencing high demand.",
                        "status": "UNAVAILABLE",
                    }
                },
                response=None,
            ),
            "rate_limit",
            id="google-unavailable",
        ),
        pytest.param(
            _http_error(anthropic.InternalServerError, 529, {"message": "Overloaded"}),
            "rate_limit",
            id="anthropic-overloaded",
        ),
    ]


@pytest.mark.parametrize(("failure", "code"), _provider_failures())
def test_provider_failure_ends_the_run_cleanly(
    script, workspace: Path, tmp_path: Path, failure: Exception, code: str
) -> None:
    script(failure)
    events = _run(tmp_path, prompt="hi")
    assert _types(events)[2:] == ["agent_started", "error_occurred", "agent_stopped"]
    assert events[-2]["data"]["avp.error.code"] == code
    assert events[-1]["data"]["avp.reason"] == "error"


def test_unexpected_crash_is_recorded_then_raised(script, workspace: Path, tmp_path: Path) -> None:
    script(RuntimeError("boom"))
    commission = {"schema_version": "0.1", "run_id": "r1", "model": "openai/gpt-4o-mini"}
    out = tmp_path / "t.jsonl"
    with pytest.raises(RuntimeError, match="boom"):
        main(
            run=run,
            describe=describe,
            argv=["run", "--commission", json.dumps(commission), "--out", str(out)],
        )
    events = [json.loads(line) for line in out.read_text().splitlines()]
    assert events[-2]["data"]["avp.error.code"] == "agent_crash"
    assert events[-1]["data"]["avp.reason"] == "error"


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"enabled_builtin_tools": {"avp-deep-agents": ["nope"]}}, "commission_collision"),
        ({"enabled_builtin_subagents": {"avp-deep-agents": ["nope"]}}, "commission_collision"),
        ({"enabled_builtin_tools": {"other-agent": []}}, "commission_collision"),
        ({"agent_versions": {"avp-deep-agents": "9.9.9"}}, "unsupported_agent_version"),
        ({"provider": {"id": "openrouter"}}, "unsupported_provider"),
        ({"model": "mistral/mistral-large-latest"}, "unsupported_model"),
    ],
)
def test_fail_fast_refusals(
    script, workspace: Path, tmp_path: Path, fields: dict, code: str
) -> None:
    model = script()
    events = _run(tmp_path, prompt="hi", **fields)
    assert _types(events) == ["run_requested", "agent_described", "error_occurred", "agent_stopped"]
    assert events[2]["data"]["avp.error.code"] == code
    assert events[3]["data"]["avp.reason"] == "error"
    assert model.requests == []


def test_sigterm_stops_interrupted(script, workspace: Path, tmp_path: Path) -> None:
    """SIGTERM during an inference: the stock entrypoint cancels the run and
    the trajectory closes `interrupted`."""

    async def hang() -> None:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(60)

    script(reply("", ("call_1", "ls", {"path": "/"})), lambda messages: hang())
    events = _run(tmp_path, exit_code=130, prompt="hi")
    assert _types(events)[-1] == "agent_stopped"
    assert events[-1]["data"]["avp.reason"] == "interrupted"
    assert "tool_returned" in _types(events)


def test_chat_model_follows_the_commission(monkeypatch: pytest.MonkeyPatch) -> None:
    from avp.commission import Commission
    from avp_deep_agents import commission as cm

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    base = {"schema_version": "0.1", "run_id": "r1"}
    openai = cm.chat_model(
        Commission(
            **base,
            model="openai/gpt-5-mini",
            provider={"id": "openai", "base_url": "http://localhost:9/v1"},
        )
    )
    assert type(openai).__name__ == "ChatOpenAI"
    assert openai.model_name == "gpt-5-mini"
    # Deep Agents' OpenAI provider profile: the Responses API.
    assert openai.use_responses_api is True
    assert openai.openai_api_base == "http://localhost:9/v1"
    anthropic = cm.chat_model(Commission(**base, model="anthropic/claude-haiku-4-5"))
    assert type(anthropic).__name__ == "ChatAnthropic"
    assert anthropic.model == "claude-haiku-4-5"
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    google = cm.chat_model(Commission(**base, model="google/gemini-2.5-flash"))
    assert type(google).__name__ == "ChatGoogleGenerativeAI"
    assert google.model.endswith("gemini-2.5-flash")
    assert google.max_retries == cm.GOOGLE_ATTEMPTS


def test_output_schema_is_the_run_output(script, workspace: Path, tmp_path: Path) -> None:
    """The scripted model has no native structured output, so LangChain asks
    for it as a tool call; the call pairs from the run's final messages."""
    schema = {
        "title": "Answer",
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    model = script(reply("", ("call_1", "Answer", {"answer": "42"})))
    events = _run(tmp_path, prompt="answer", output_schema=schema)
    assert "Answer" in model.tool_sets[0]
    returned = _of(events, "tool_returned")[0]["avp.tool_result"]
    assert returned["tool_use_id"] == "call_1" and not returned["is_error"]
    assert events[-1]["data"] == {
        **events[-1]["data"],
        "avp.reason": "converged",
        "avp.output": {"answer": "42"},
    }
