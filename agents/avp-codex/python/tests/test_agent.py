"""CLI to Recorder seam, with native app-server notifications scripted."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from avp.agent_cli import main
from avp.trajectory import parse_event
from avp_codex import agent
from avp_codex.commission import CODEX_VERSION


def notification(method, **params):
    return {"method": method, "params": {"threadId": "thread", "turnId": "turn", **params}}


def raw(item):
    return notification("rawResponseItem/completed", item=item)


def completed(tokens=10):
    return notification(
        "rawResponse/completed",
        usage={
            "inputTokens": tokens,
            "outputTokens": 2,
            "cachedInputTokens": 3,
            "reasoningOutputTokens": 1,
        },
    )


def text_item(text="DONE"):
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    }


def stopped(status="completed"):
    return notification("turn/completed", turn={"status": status})


@pytest.fixture
def script(monkeypatch):
    class Server:
        events = []
        calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def __init__(self, home, cwd, config):
            self.config = config

        async def send(self, message):
            pass

        async def request(self, method, params):
            self.calls.append((method, params))
            return {
                "initialize": {},
                "skills/list": {"data": [{"skills": [{"path": "/host/secret/SKILL.md"}]}]},
                "thread/start": {"thread": {"id": "thread", "cliVersion": CODEX_VERSION}},
                "mcpServerStatus/list": {
                    "data": [
                        {
                            "name": "echo",
                            "runtimeStatus": "connected",
                            "tools": {
                                "Echo": {"name": "Echo", "inputSchema": {"type": "object"}},
                            },
                        }
                    ]
                },
                "turn/start": {"turn": {"id": "turn"}},
            }[method]

        async def notification(self):
            if not self.events:
                raise RuntimeError("unexpected EOF")
            return self.events.pop(0)

    monkeypatch.setattr(agent, "AppServer", Server)
    return Server


def run_cli(tmp_path: Path, *, raises=False, **fields):
    commission = {
        "schema_version": "0.1",
        "run_id": "codex-test",
        "model": "openai/gpt-5-mini",
        "prompt": "Say DONE",
    }
    commission.update(fields)
    out = tmp_path / "trajectory.jsonl"
    argv = ["run", "--commission", json.dumps(commission), "--out", str(out)]
    if raises:
        with pytest.raises((ValueError, RuntimeError)):
            main(run=agent.run, describe=agent.describe, argv=argv)
        code = 1
    else:
        code = main(run=agent.run, describe=agent.describe, argv=argv)
    events = [json.loads(line) for line in out.read_text().splitlines()]
    for event in events:
        parse_event(event)
    return code, events


def test_roundtrip_usage_and_failure_status(script, tmp_path):
    call = {
        "type": "function_call",
        "namespace": "mcp__echo",
        "name": "Echo",
        "call_id": "call",
        "arguments": '{"text":"hello"}',
    }
    script.events = [
        raw({"type": "message", "role": "user", "content": []}),
        raw(call),
        completed(),
        notification(
            "item/completed", item={"type": "mcpToolCall", "id": "call", "status": "failed"}
        ),
        raw(
            {
                "type": "function_call_output",
                "call_id": "call",
                "output": [{"type": "input_text", "text": "failed"}],
            }
        ),
        notification("thread/tokenUsage/updated", tokenUsage={"total": {"inputTokens": 999}}),
        raw(text_item()),
        completed(20),
        stopped(),
    ]
    code, events = run_cli(
        tmp_path, mcp_servers=[{"id": "echo", "type": "stdio", "command": ["echo"]}]
    )
    assert code == 0
    assert [e["type"] for e in events] == [
        "avp." + t
        for t in [
            "run_requested",
            "agent_described",
            "agent_started",
            "assistant_message",
            "tool_invoked",
            "tool_returned",
            "assistant_message",
            "agent_stopped",
        ]
    ]
    assert [
        e["data"]["avp.usage"]["input_tokens"]
        for e in events
        if e["type"] == "avp.assistant_message"
    ] == [10, 20]
    assert events[4]["data"]["avp.tool.dispatch_target"] == "mcp_server"
    assert events[5]["data"]["avp.tool_result"]["is_error"] is True
    assert events[-1]["data"]["avp.output"] == "DONE"
    thread_params = dict(script.calls)["thread/start"]
    assert thread_params["config"]["skills.config"] == [
        {"path": "/host/secret/SKILL.md", "enabled": False}
    ]


@pytest.mark.parametrize(
    "events",
    [
        [raw(text_item()), stopped()],
        [stopped("failed")],
        [raw({"type": "future_output"}), stopped()],
        [raw({"type": "function_call_output", "call_id": "missing", "output": "bad"}), stopped()],
        [
            raw({"type": "function_call", "name": "bad", "call_id": "c", "arguments": "[]"}),
            completed(),
            stopped(),
        ],
    ],
)
def test_incomplete_or_untranslatable_stream_never_converges(script, tmp_path, events):
    script.events = events
    _, trajectory = run_cli(
        tmp_path, raises=events[0].get("params", {}).get("turn", {}).get("status") != "failed"
    )
    assert trajectory[-1]["data"]["avp.reason"] == "error"
    assert any(e["type"] == "avp.error_occurred" for e in trajectory)


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({"enabled_builtin_tools": {"avp-codex": []}}, "commission_collision"),
        ({"enabled_builtin_tools": {"other": []}}, "commission_collision"),
        ({"model": "anthropic/claude-haiku-4-5"}, "unsupported_model"),
        ({"provider": {"id": "anthropic"}}, "unsupported_provider"),
    ],
)
def test_unsupported_commissions_fail_before_native_start(script, tmp_path, fields, expected):
    _, events = run_cli(tmp_path, **fields)
    assert script.calls == []
    assert events[-2]["data"]["avp.error.code"] == expected
    assert events[-1]["data"]["avp.reason"] == "error"


def test_instructions_schema_and_interruption(script, tmp_path):
    script.events = [stopped("interrupted")]
    _, events = run_cli(
        tmp_path,
        system_prompt="Be brief",
        skills=[
            {
                "id": "greet",
                "files": {"SKILL.md": "Say hi", "extra.txt": "support"},
            }
        ],
        output_schema={"type": "object"},
    )
    calls = dict(script.calls)
    assert calls["thread/start"]["baseInstructions"] == "Be brief"
    assert "support" in calls["thread/start"]["developerInstructions"]
    assert calls["turn/start"]["outputSchema"] == {"type": "object"}
    assert events[-1]["data"]["avp.reason"] == "interrupted"


@pytest.mark.parametrize(
    "info, expected",
    [
        ("unauthorized", "auth_error"),
        ("usageLimitExceeded", "rate_limit"),
        ("contextWindowExceeded", "context_limit"),
        ({"responseStreamConnectionFailed": {"httpStatusCode": 401}}, "auth_error"),
    ],
)
def test_provider_failure_is_an_error_not_an_assistant_turn(script, tmp_path, info, expected):
    script.events = [
        notification(
            "error", error={"message": "provider failed", "codexErrorInfo": info}, willRetry=False
        ),
        stopped("failed"),
    ]
    _, events = run_cli(tmp_path)
    assert not any(e["type"] == "avp.assistant_message" for e in events)
    assert events[-2]["data"]["avp.error.code"] == expected
    assert events[-1]["data"]["avp.reason"] == "error"


def test_retry_reroute_and_early_result(script, tmp_path):
    script.events = [
        notification("error", error={"message": "retry"}, willRetry=True),
        raw(
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call",
                "arguments": '{"cmd":"pwd"}',
            }
        ),
        raw({"type": "function_call_output", "call_id": "call", "output": "workspace"}),
        completed(),
        notification("model/rerouted", toModel="gpt-5"),
        raw(text_item()),
        completed(),
        stopped(),
    ]
    _, events = run_cli(tmp_path)
    assert events[-1]["data"]["avp.reason"] == "converged"
    assert events[-2]["data"]["avp.response.model"] == "openai/gpt-5"
    assert events[-2]["data"]["avp.request.model"] == "openai/gpt-5-mini"
    assert not any(e["type"] == "avp.error_occurred" for e in events)


def test_shutdown_failure_cannot_follow_converged(script, tmp_path):
    async def fail_exit(self, *args):
        raise RuntimeError("native shutdown failed")

    script.__aexit__ = fail_exit
    script.events = [raw(text_item()), completed(), stopped()]
    _, events = run_cli(tmp_path, raises=True)
    assert events[-1]["data"]["avp.reason"] == "error"
    assert events[-2]["data"]["avp.error.message"] == "native shutdown failed"
    assert sum(e["type"] == "avp.agent_stopped" for e in events) == 1
