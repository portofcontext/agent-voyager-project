"""CLI to Recorder seam, with official SDK notifications scripted."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai_codex.generated.notification_registry import NOTIFICATION_MODELS
from openai_codex.generated.v2_all import AskForApproval, TurnStartResponse
from openai_codex.models import Notification, UnknownNotification

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
    return notification(
        "turn/completed", turn={"id": "turn", "items": [], "itemsView": "full", "status": status}
    )


@pytest.fixture
def script(monkeypatch):
    class Server:
        events = []
        calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def __init__(self, config):
            self.config = config

        async def initialize(self):
            pass

        def unregister_turn_notifications(self, turn_id):
            assert turn_id == "turn"

        async def thread_start(self, params):
            self.calls.append(("thread/start", params))
            return SimpleNamespace(
                thread=SimpleNamespace(id="thread", cli_version=CODEX_VERSION),
                approval_policy=AskForApproval.model_validate("never"),
            )

        async def turn_start(self, thread, input_items, *, params):
            self.calls.append(("turn/start", params))
            return TurnStartResponse.model_validate(
                {"turn": {"id": "turn", "items": [], "itemsView": "full", "status": "inProgress"}}
            )

        async def request(self, method, params, *, response_model):
            self.calls.append((method, params))
            data = {
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
                            "tools": {
                                "Echo": {"name": "Echo", "inputSchema": {"type": "object"}},
                            },
                        }
                    ]
                },
            }[method]
            return response_model.model_validate(data)

        async def next_turn_notification(self, turn_id):
            if not self.events:
                raise RuntimeError("unexpected EOF")
            event = self.events.pop(0)
            method, params = event["method"], event["params"]
            model = NOTIFICATION_MODELS.get(method)
            payload = model.model_validate(params) if model else UnknownNotification(params)
            return Notification(method, payload)

    monkeypatch.setattr(agent, "AsyncCodexClient", Server)
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
            "item/completed",
            completedAtMs=1,
            item={
                "type": "mcpToolCall",
                "id": "call",
                "status": "failed",
                "server": "echo",
                "tool": "Echo",
                "arguments": {"text": "hello"},
            },
        ),
        raw(
            {
                "type": "function_call_output",
                "call_id": "call",
                "output": [{"type": "input_text", "text": "failed"}],
            }
        ),
        notification(
            "thread/tokenUsage/updated",
            tokenUsage={
                key: {
                    "inputTokens": tokens,
                    "outputTokens": 2,
                    "totalTokens": tokens + 2,
                    "cachedInputTokens": 3,
                    "reasoningOutputTokens": 1,
                }
                for key, tokens in [("last", 10), ("total", 999)]
            },
        ),
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
        ({"enabled_builtin_tools": {"avp-codex": ["exec_command"]}}, "commission_collision"),
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
        notification(
            "model/rerouted",
            fromModel="gpt-5-mini",
            toModel="gpt-5",
            reason="highRiskCyberActivity",
        ),
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


@pytest.mark.parametrize(
    "method",
    [
        "item/completed",
        "turn/completed",
        "error",
        "model/rerouted",
        "thread/tokenUsage/updated",
    ],
)
def test_sdk_validation_fallback_is_not_silently_accepted(method):
    from openai_codex.client import CodexClient

    from avp_codex.translate import notification_params

    # This exercises the SDK's actual fallback on malformed known payloads.
    event = CodexClient()._coerce_notification(method, {"threadId": "thread"})
    assert isinstance(event.payload, UnknownNotification)
    with pytest.raises(ValueError, match="could not validate"):
        notification_params(event)


@pytest.mark.parametrize(
    "events",
    [
        [
            raw(text_item("partial")),
            notification("error", error={"message": "retry"}, willRetry=True),
        ],
        [
            notification(
                "item/completed",
                completedAtMs=1,
                item={"id": "compact", "type": "contextCompaction"},
            )
        ],
        [notification("thread/compacted")],
    ],
)
def test_unaccountable_retry_and_compaction_fail_visibly(script, tmp_path, events):
    script.events = [*events, raw(text_item()), completed(), stopped()]
    _, trajectory = run_cli(tmp_path, raises=True)
    assert trajectory[-1]["data"]["avp.reason"] == "error"
    assert not any(e["type"] == "avp.assistant_message" for e in trajectory)


@pytest.mark.parametrize(
    "allowed",
    [
        [],
        ["request_user_input"],
        ["apply_patch", "view_image"],
        ["apply_patch", "exec_command", "write_stdin"],
    ],
)
def test_selected_tools_reach_sdk_and_trajectory(script, tmp_path, allowed):
    script.events = [raw(text_item()), completed(), stopped()]
    _, events = run_cli(tmp_path, enabled_builtin_tools={"avp-codex": allowed})
    started = next(e["data"] for e in events if e["type"] == "avp.agent_started")
    assert {t["name"] for t in started["avp.tools"]} == set(allowed)
    assert events[-1]["data"]["avp.reason"] == "converged"
    params = dict(script.calls)["thread/start"]
    assert (params.get("environments") == []) is (
        not set(allowed) & {"apply_patch", "view_image", "exec_command"}
    )


@pytest.mark.parametrize(
    "allowed, mcp, model, message",
    [
        (["write_stdin", "apply_patch"], [], "openai/gpt-5-mini", "together"),
        (["exec_command", "write_stdin"], [], "openai/gpt-5.5", "apply_patch"),
        (
            [],
            [{"id": "echo", "type": "stdio", "command": ["echo"]}],
            "openai/gpt-5-mini",
            "MCP servers",
        ),
    ],
)
def test_unrepresentable_tool_selection_fails_before_sdk(
    script, tmp_path, allowed, mcp, model, message
):
    _, events = run_cli(
        tmp_path, model=model, enabled_builtin_tools={"avp-codex": allowed}, mcp_servers=mcp
    )
    assert script.calls == []
    assert events[-2]["data"]["avp.error.code"] == "commission_collision"
    assert message in events[-2]["data"]["avp.error.message"]


@pytest.mark.parametrize(
    "model, mcp, message",
    [
        ("openai/gpt-6.1-sol", [], "model catalogs"),
        ("openai/gpt-5.5", [{"id": "echo", "type": "stdio", "command": ["echo"]}], "tool search"),
    ],
)
def test_model_added_tools_cannot_bypass_allowlist(script, tmp_path, model, mcp, message):
    _, events = run_cli(
        tmp_path, model=model, mcp_servers=mcp, enabled_builtin_tools={"avp-codex": []}
    )
    assert script.calls == []
    assert message in events[-2]["data"]["avp.error.message"]
