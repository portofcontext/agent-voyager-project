"""Native SDK messages cross the agent and Recorder into validated wire events."""

import asyncio
import json
import subprocess
import sys

import pytest
from claude_agent_sdk._internal.message_parser import parse_message
from pydantic import TypeAdapter

from avp.agent_cli import main
from avp.trajectory import Event
from avp_claude_agent_sdk import agent
from avp_claude_agent_sdk.descriptor import CLAUDE_VERSION, describe

MODEL = {"provider": "anthropic", "id": "claude-haiku-4-5"}


def stream(event, parent=None):
    return {
        "type": "stream_event",
        "uuid": "event",
        "session_id": "session",
        "parent_tool_use_id": parent,
        "event": event,
    }


def response(blocks=None, tokens=10, parent=None):
    events = [
        stream(
            {
                "type": "message_start",
                "message": {
                    "id": "message",
                    "model": MODEL["id"],
                    "usage": {
                        "input_tokens": tokens,
                        "output_tokens": 0,
                        "cache_read_input_tokens": 3,
                        "cache_creation_input_tokens": 2,
                    },
                },
            },
            parent,
        )
    ]
    for i, b in enumerate(blocks or [{"type": "text", "text": "DONE"}]):
        events += [
            stream({"type": "content_block_start", "index": i, "content_block": b}, parent),
            stream({"type": "content_block_stop", "index": i}, parent),
        ]
    events += [
        stream(
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 4},
            },
            parent,
        ),
        stream({"type": "message_stop"}, parent),
    ]
    return events


def result(**fields):
    return {
        "type": "result",
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "session",
        "result": "DONE",
        "usage": {"input_tokens": 999},
        **fields,
    }


def init():
    return {"type": "system", "subtype": "init", "claude_code_version": CLAUDE_VERSION}


def run_cli(tmp_path, *, raises=False, **fields):
    received = {
        "avp_version": "0.1",
        "run_id": "test",
        "model": MODEL,
        "prompt": "Reply DONE",
        **fields,
    }
    path = tmp_path / "trajectory.ndjson"
    argv = ["run", "--commission", json.dumps(received), "--out", str(path)]
    if raises:
        with pytest.raises((ValueError, RuntimeError)):
            main(run=agent.run, describe=describe, argv=argv)
        code = 1
    else:
        code = main(run=agent.run, describe=describe, argv=argv)
    events = [json.loads(line) for line in path.read_text().splitlines()]
    for event in events:
        TypeAdapter(Event).validate_python(event)
    return code, events


@pytest.fixture
def script(monkeypatch):
    class Client:
        messages = []
        options = None
        statuses = []

        def __init__(self, options):
            Client.options = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def query(self, prompt):
            pass

        async def get_mcp_status(self):
            return {"mcpServers": self.statuses}

        async def receive_response(self):
            for data in self.messages:
                if isinstance(data, asyncio.CancelledError):
                    raise data
                yield parse_message(data)

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    return Client


def test_native_response_usage_and_tool_pairing(script, tmp_path):
    script.messages = [
        init(),
        *response(
            [{"type": "tool_use", "id": "call", "name": "Bash", "input": {"command": "echo hi"}}]
        ),
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call",
                        "content": "hi",
                        "is_error": False,
                    }
                ],
            },
        },
        *response(tokens=20),
        result(),
    ]
    code, events = run_cli(tmp_path)
    assert code == 0
    assert [e["type"] for e in events] == [
        "run_requested",
        "agent_described",
        "agent_started",
        "assistant_message",
        "tool_invoked",
        "tool_returned",
        "assistant_message",
        "agent_stopped",
    ]
    assert [
        e["data"]["usage"]["input_tokens"] for e in events if e["type"] == "assistant_message"
    ] == [15, 25]
    assert events[-1]["data"] == {"reason": "converged", "output": "DONE"}


@pytest.mark.parametrize(
    "fields",
    [
        {"agents": {"other": {}}},
        {"agents": {"avp-claude-agent-sdk": {"enabled_tools": ["missing"]}}},
        {"model": {"provider": "openai", "id": "gpt-5-mini"}},
    ],
)
def test_invalid_commission_is_refused_before_sdk_start(script, tmp_path, fields):
    _, events = run_cli(tmp_path, **fields)
    assert [e["type"] for e in events] == ["run_requested", "agent_described", "error_occurred"]
    assert events[-1]["data"]["error_code"] == "invalid_commission"
    assert script.options is None


def test_proxy_credentials_skills_allowlists_and_schema(script, tmp_path):
    script.messages = [init(), *response(), result(structured_output={"answer": 42})]
    _, events = run_cli(
        tmp_path,
        model={**MODEL, "credential": {"proxy": "anthropic"}},
        agents={
            "avp-claude-agent-sdk": {
                "enabled_tools": [],
                "enabled_skills": [],
                "enabled_subagents": [],
            }
        },
        skills=[
            {
                "name": "hello",
                "files": {
                    "SKILL.md": "---\nname: hello\ndescription: Hello\n---\nHi",
                    "guide.txt": "SUPPORT",
                },
            }
        ],
        system_prompt="SYSTEM",
        output_schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "integer"}},
        },
    )
    assert events[-1]["data"]["output"] == {"answer": 42}
    assert script.options.env["ANTHROPIC_API_KEY"] == "avp-proxy-stand-in"
    assert script.options.tools == []
    assert "SUPPORT" in script.options.system_prompt
    assert "SYSTEM" in script.options.system_prompt
    assert script.options.output_format["schema"]["type"] == "object"


def test_invalid_structured_output_never_converges(script, tmp_path):
    script.messages = [init(), *response(), result(structured_output={"answer": "wrong"})]
    _, events = run_cli(
        tmp_path, output_schema={"type": "object", "properties": {"answer": {"type": "integer"}}}
    )
    assert events[-2]["data"]["error_code"] == "output_invalid"
    assert events[-1]["data"]["reason"] == "error"


def test_missing_secret_and_mcp_failure_happen_before_started(script, tmp_path):
    _, events = run_cli(tmp_path, model={**MODEL, "credential": {"env": "MISSING_AVP_TEST_SECRET"}})
    assert events[-1]["data"]["error_code"] == "auth_error"
    script.messages = [init()]
    _, events = run_cli(
        tmp_path, mcp_servers=[{"id": "missing", "type": "stdio", "command": ["missing"]}]
    )
    assert events[-1]["data"]["error_code"] == "mcp_connect_failed"
    assert not any(e["type"] == "agent_started" for e in events)


@pytest.mark.parametrize(
    "info,code",
    [
        ("authentication_failed", "auth_error"),
        ("rate_limit", "rate_limit"),
        ("billing_error", "rate_limit"),
    ],
)
def test_native_errors_are_reported(script, tmp_path, info, code):
    script.messages = [
        init(),
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "synthetic",
                "content": [{"type": "text", "text": "failed"}],
            },
            "error": info,
        },
        result(is_error=True),
    ]
    _, events = run_cli(tmp_path)
    assert events[-2]["data"]["error_code"] == code
    assert events[-1]["data"]["reason"] == "error"


def test_incomplete_response_and_disabled_tool_fail(script, tmp_path):
    script.messages = [init(), result()]
    _, events = run_cli(tmp_path, raises=True)
    assert events[-1]["data"]["reason"] == "error"
    script.messages = [
        init(),
        *response([{"type": "tool_use", "id": "call", "name": "Bash", "input": {}}]),
        result(),
    ]
    _, events = run_cli(
        tmp_path, raises=True, agents={"avp-claude-agent-sdk": {"enabled_tools": []}}
    )
    assert "disabled" in events[-2]["data"]["error_message"]


def test_cancellation_stops_and_returns_130(script, tmp_path):
    script.messages = [init(), asyncio.CancelledError()]
    code, events = run_cli(tmp_path)
    assert code == 130
    assert events[-1]["data"]["reason"] == "interrupted"


def test_cli_ping_and_descriptor_do_not_need_credentials():
    for verb in ["ping", "describe"]:
        value = json.loads(
            subprocess.check_output(
                [sys.executable, "-m", "avp_claude_agent_sdk.cli", verb], text=True
            )
        )
        assert (
            value["type"] == "pong"
            if verb == "ping"
            else value["agent_name"] == "avp-claude-agent-sdk"
        )


@pytest.mark.parametrize("background", [False, True])
def test_subagent_responses_keep_frames_and_usage(script, tmp_path, background):
    call = {
        "type": "tool_use",
        "id": "child",
        "name": "Agent",
        "input": {
            "description": "Child task",
            "prompt": "Say hi",
            "subagent_type": "general-purpose",
            "run_in_background": background,
        },
    }
    returned = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "child",
                    "content": "CHILD",
                    "is_error": False,
                }
            ],
        },
    }
    script.messages = [init(), *response([call]), *response(tokens=30, parent="child"), returned]
    if background:
        script.messages.append(
            {
                "type": "system",
                "subtype": "task_notification",
                "task_id": "native-task",
                "status": "completed",
                "output_file": "/tmp/output",
                "summary": "CHILD",
                "uuid": "notification",
                "session_id": "session",
                "tool_use_id": "child",
            }
        )
    script.messages += [*response(tokens=20), result()]
    _, events = run_cli(tmp_path)
    invoked = next(e["data"] for e in events if e["type"] == "subagent_invoked")
    assert invoked["invocation_id"] == "child"
    child = next(
        e["data"]
        for e in events
        if e["type"] == "assistant_message" and e["data"].get("subagent_invocation_id")
    )
    assert child["usage"]["input_tokens"] == 35
    assert child["subagent_invocation_id"] == "child"
    returned = next(e["data"] for e in events if e["type"] == "subagent_returned")
    assert returned["subagent_reason"] == "converged"
    assert "subagent_usage" not in returned
    assert events[-1]["data"]["reason"] == "converged"


@pytest.mark.parametrize("child", [False, True])
def test_eager_results_wait_for_complete_parent_response(script, tmp_path, child):
    tool = {
        "type": "tool_use",
        "id": "eager",
        "name": "Agent" if child else "Bash",
        "input": {"description": "Check", "prompt": "Say DONE", "subagent_type": "general-purpose"}
        if child
        else {"command": "printf DONE"},
    }
    parent = response([tool, {"type": "text", "text": "after the call"}])
    returned = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "eager",
                    "content": "DONE",
                    "is_error": False,
                }
            ],
        },
    }
    early = [*response(tokens=30, parent="eager"), returned] if child else [returned]
    script.messages = [init(), *parent[:-2], *early, *parent[-2:], *response(tokens=20), result()]
    code, events = run_cli(tmp_path)
    assert code == 0
    replies = [e["data"] for e in events if e["type"] == "assistant_message"]
    assert len(replies) == (3 if child else 2)
    assert replies[0]["usage"]["input_tokens"] == 15
    assert replies[0]["content"][1]["text"] == "after the call"
    assert replies[-1]["usage"]["input_tokens"] == 25
    assert len([e for e in events if e["type"] == "tool_returned"]) == 1
    if child:
        assert replies[1]["subagent_invocation_id"] == "eager"
        assert replies[1]["usage"]["input_tokens"] == 35
        child_returned = next(e["data"] for e in events if e["type"] == "subagent_returned")
        assert child_returned["subagent_reason"] == "converged"
    assert events[-1]["data"]["reason"] == "converged"


@pytest.mark.parametrize("recorded", [False, True])
def test_native_child_usage_is_kept_only_when_its_responses_are_opaque(script, tmp_path, recorded):
    call = {
        "type": "tool_use",
        "id": "opaque",
        "name": "Agent",
        "input": {
            "description": "Check",
            "prompt": "Say DONE",
            "subagent_type": "general-purpose",
        },
    }
    returned = {
        "type": "user",
        "tool_use_result": {
            "resolvedModel": MODEL["id"],
            "usage": {
                "input_tokens": 10,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 30,
                "output_tokens": 8,
                "output_tokens_details": {"thinking_tokens": 3},
            },
        },
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "opaque", "content": "DONE"}],
        },
    }
    script.messages = [init(), *response([call])]
    if recorded:
        script.messages += response(tokens=30, parent="opaque")
    # The live CLI notifies completion before delivering the foreground Agent
    # result that carries input/output usage. Do not finish on that notification.
    notification = {
        "type": "system",
        "subtype": "task_notification",
        "task_id": "native-task",
        "tool_use_id": "opaque",
        "status": "completed",
        "output_file": "/tmp/opaque",
        "summary": "DONE",
        "uuid": "notice",
        "session_id": "session",
        "usage": {"total_tokens": 68, "tool_uses": 0, "duration_ms": 1},
    }
    script.messages += [notification, returned, *response(tokens=20), result()]
    _, events = run_cli(tmp_path)
    assert len([e for e in events if e["type"] == "subagent_returned"]) == 1
    child = next(e["data"] for e in events if e["type"] == "subagent_returned")
    if recorded:
        assert "subagent_usage" not in child
    else:
        usage = child["subagent_usage"]
        assert usage["input_tokens"] == 60
        assert usage["output_tokens"] == 8
        assert usage["cache_read_input_tokens"] == 20
        assert usage["cache_creation_input_tokens"] == 30
        assert usage["reasoning_output_tokens"] == 3
        assert usage["cost_source"] == "computed" and usage["cost_usd"] > 0
