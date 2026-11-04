"""The installed SDK notifications cross the adapter and Recorder into wire events."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
from openai_codex.client import CodexClient
from openai_codex.generated.v2_all import AskForApproval, TurnStartResponse
from pydantic import TypeAdapter

from avp.agent_cli import main
from avp.trajectory import Event
from avp_codex import agent, descriptor

MODEL = {"provider": "openai", "id": "gpt-5-mini"}


def raw(item):
    return {"method": "rawResponseItem/completed", "item": item}


def text(value="DONE"):
    return raw(
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": value}],
        }
    )


def boundary(tokens=10):
    return {
        "method": "rawResponse/completed",
        "usage": {
            "inputTokens": tokens,
            "outputTokens": 2,
            "cachedInputTokens": 3,
            "reasoningOutputTokens": 1,
        },
    }


def completed(status="completed"):
    return {
        "method": "turn/completed",
        "turn": {"id": "turn", "items": [], "itemsView": "full", "status": status},
    }


def run_cli(tmp_path, *, raises=False, **fields):
    received = {
        "avp_version": "0.1",
        "run_id": "test",
        "model": MODEL,
        "prompt": "Say DONE",
        **fields,
    }
    path = tmp_path / "trajectory.ndjson"
    argv = ["run", "--commission", json.dumps(received), "--out", str(path)]
    if raises:
        with pytest.raises((ValueError, RuntimeError)):
            main(run=agent.run, describe=descriptor.describe, argv=argv)
        code = 1
    else:
        code = main(run=agent.run, describe=descriptor.describe, argv=argv)
    events = [json.loads(line) for line in path.read_text().splitlines()]
    parser = TypeAdapter(Event)
    for event in events:
        parser.validate_python(event)
    return code, events


@pytest.fixture
def script(monkeypatch):
    class Server:
        config: ClassVar[Any] = None
        events = []
        calls = []

        def __init__(self, config):
            Server.config = config

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            pass

        async def request(self, method, params, *, response_model):
            self.calls.append((method, params))
            values = {
                "skills/list": {
                    "data": [
                        {
                            "cwd": "/workspace",
                            "errors": [],
                            "skills": [
                                {
                                    "path": "/host/secret/SKILL.md",
                                    "name": "secret",
                                    "description": "host",
                                    "enabled": True,
                                    "scope": "user",
                                }
                            ],
                        }
                    ]
                },
                "mcpServerStatus/list": {
                    "data": [
                        {
                            "name": "echo",
                            "runtimeStatus": "connected",
                            "authStatus": "unsupported",
                            "resources": [],
                            "resourceTemplates": [],
                            "tools": {"Echo": {"name": "Echo", "inputSchema": {"type": "object"}}},
                        }
                    ]
                },
            }
            return response_model.model_validate(values[method])

        async def thread_start(self, params):
            self.calls.append(("thread/start", params))
            return SimpleNamespace(
                thread=SimpleNamespace(id="thread", cli_version=agent.CODEX_VERSION),
                approval_policy=AskForApproval.model_validate("never"),
            )

        async def turn_start(self, thread, input_items, *, params):
            self.calls.append(("turn/start", params))
            return TurnStartResponse.model_validate(
                {"turn": {"id": "turn", "items": [], "itemsView": "full", "status": "inProgress"}}
            )

        async def next_turn_notification(self, turn):
            if not self.events:
                raise RuntimeError("unexpected EOF")
            event = self.events.pop(0)
            if isinstance(event, asyncio.CancelledError):
                raise event
            event = dict(event)
            method = event.pop("method")
            return CodexClient()._coerce_notification(
                method, {"threadId": "thread", "turnId": turn, **event}
            )

        def unregister_turn_notifications(self, turn):
            assert turn == "turn"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(agent, "AsyncCodexClient", Server)
    return Server


def test_native_responses_pair_tool_results_and_keep_usage_deltas(script, tmp_path):
    script.events = [
        raw(
            {
                "type": "function_call",
                "namespace": "mcp__echo",
                "name": "Echo",
                "call_id": "call",
                "arguments": '{"text":"hello"}',
            }
        ),
        boundary(10),
        {
            "method": "item/completed",
            "completedAtMs": 1,
            "item": {
                "type": "mcpToolCall",
                "id": "call",
                "status": "failed",
                "server": "echo",
                "tool": "Echo",
                "arguments": {"text": "hello"},
            },
        },
        raw({"type": "function_call_output", "call_id": "call", "output": "failed"}),
        {
            "method": "thread/tokenUsage/updated",
            "tokenUsage": {
                key: {
                    "inputTokens": value,
                    "outputTokens": 2,
                    "cachedInputTokens": 3,
                    "reasoningOutputTokens": 1,
                    "totalTokens": value + 2,
                }
                for key, value in [("last", 10), ("total", 999)]
            },
        },
        text(),
        boundary(20),
        completed(),
    ]
    code, events = run_cli(
        tmp_path, mcp_servers=[{"id": "echo", "type": "stdio", "command": ["echo"]}]
    )
    assert code == 0
    assert [event["type"] for event in events] == [
        "run_requested",
        "agent_described",
        "agent_started",
        "assistant_message",
        "tool_invoked",
        "tool_returned",
        "assistant_message",
        "agent_stopped",
    ]
    responses = [event["data"] for event in events if event["type"] == "assistant_message"]
    assert [item["usage"]["input_tokens"] for item in responses] == [10, 20]
    assert responses[0]["usage"]["cache_read_input_tokens"] == 3
    assert events[4]["data"]["mcp_server_id"] == "echo"
    assert events[5]["data"]["tool_result"]["is_error"] is True
    assert events[-1]["data"] == {"reason": "converged", "output": "DONE"}
    assert dict(script.calls)["thread/start"]["config"]["skills.config"] == [
        {"path": "/host/secret/SKILL.md", "enabled": False}
    ]


@pytest.mark.parametrize(
    "fields,message",
    [
        ({"agents": {"other": {}}}, "no entry"),
        ({"agents": {"avp-codex": {"enabled_tools": ["unknown"]}}}, "doesn't have"),
        ({"model": {"provider": "anthropic", "id": "test"}}, "Responses"),
        ({"agents": {"avp-codex": {"enabled_tools": ["exec_command"]}}}, "together"),
    ],
)
def test_refusal_uses_sdk_prelude_before_starting_codex(script, tmp_path, fields, message):
    _, events = run_cli(tmp_path, **fields)
    assert [event["type"] for event in events] == [
        "run_requested",
        "agent_described",
        "error_occurred",
    ]
    assert events[-1]["data"]["error_code"] == "invalid_commission"
    assert message in events[-1]["data"]["error_message"]
    assert not script.calls


@pytest.mark.parametrize(
    "payload,raises",
    [
        ([text(), completed()], True),
        ([raw({"type": "unknown"}), completed()], True),
        ([completed("failed")], False),
    ],
)
def test_incomplete_streams_do_not_converge(script, tmp_path, payload, raises):
    script.events = payload
    _, events = run_cli(tmp_path, raises=raises)
    assert events[-1]["data"]["reason"] == "error"


def test_credentials_skills_prompt_schema_and_output_validation(script, tmp_path):
    script.events = [text('{"answer":42}'), boundary(), completed()]
    _, events = run_cli(
        tmp_path,
        model={**MODEL, "credential": {"proxy": "openai"}},
        system_prompt="Be brief",
        skills=[
            {
                "name": "greet",
                "files": {
                    "SKILL.md": "---\nname: greet\ndescription: Say hi\n---\nSay hi",
                    "extra.txt": "support",
                },
            }
        ],
        output_schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "integer"}},
        },
    )
    assert events[-1]["data"]["output"] == {"answer": 42}
    assert script.config.env == {"AVP_CODEX_API_KEY": "avp-proxy-stand-in"}
    params = dict(script.calls)["thread/start"]
    assert params["baseInstructions"] == "Be brief"
    assert "support" in params["developerInstructions"]
    script.events = [text("invalid JSON"), boundary(), completed()]
    _, events = run_cli(tmp_path, output_schema={"type": "object"})
    assert events[-2]["data"]["error_code"] == "output_invalid"
    assert events[-1]["data"]["reason"] == "error"


def test_missing_env_secret_fails_without_starting_codex(script, tmp_path):
    _, events = run_cli(tmp_path, model={**MODEL, "credential": {"env": "MISSING_AVP_TEST_KEY"}})
    assert events[-1]["type"] == "error_occurred"
    assert events[-1]["data"]["error_code"] == "auth_error"
    assert not script.calls


def test_disabled_tool_call_is_reported_as_failure(script, tmp_path):
    script.events = [
        raw(
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call",
                "arguments": '{"cmd":"pwd"}',
            }
        ),
        boundary(),
        completed(),
    ]
    _, events = run_cli(tmp_path, raises=True, agents={"avp-codex": {"enabled_tools": []}})
    assert events[-1]["data"]["reason"] == "error"
    assert "disabled tool" in events[-2]["data"]["error_message"]


def test_ping_and_describe_are_lazy_and_match_the_pinned_catalog(tmp_path):
    import os
    import subprocess
    import sys

    for verb in ("ping", "describe"):
        result = subprocess.run(
            [sys.executable, "-m", "avp_codex.cli", verb],
            capture_output=True,
            text=True,
            check=True,
            env={name: value for name, value in os.environ.items() if name != "OPENAI_API_KEY"},
        )
        value = json.loads(result.stdout)
        if verb == "ping":
            assert value == {"type": "pong"}
        else:
            assert value["agent_name"] == "avp-codex"
            assert {tool["name"] for tool in value["tools"]} == set(descriptor.BUILTIN_TOOLS)
            assert all(tool["inputSchema"]["type"] == "object" for tool in value["tools"])
    assert descriptor.catalog()["codex"] == agent.CODEX_VERSION


def test_final_output_keeps_all_text_parts(script, tmp_path):
    script.events = [
        raw(
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "first "},
                    {"type": "output_text", "text": "second"},
                ],
            }
        ),
        boundary(),
        completed(),
    ]
    _, events = run_cli(tmp_path)
    assert events[-1]["data"]["output"] == "first second"


@pytest.mark.parametrize(
    "info,code",
    [
        ("unauthorized", "auth_error"),
        ("usageLimitExceeded", "rate_limit"),
        ("contextWindowExceeded", "context_limit"),
    ],
)
def test_provider_errors_keep_their_classification(script, tmp_path, info, code):
    script.events = [
        {
            "method": "error",
            "error": {"message": "provider failed", "codexErrorInfo": info},
            "willRetry": False,
        },
        completed("failed"),
    ]
    _, events = run_cli(tmp_path)
    assert events[-2]["data"]["error_code"] == code
    assert events[-1]["data"]["reason"] == "error"
    assert not any(event["type"] == "assistant_message" for event in events)


def test_cancellation_finishes_the_trajectory_and_returns_130(script, tmp_path):
    script.events = [asyncio.CancelledError()]
    code, events = run_cli(tmp_path)
    assert code == 130
    assert events[-1]["data"]["reason"] == "interrupted"
