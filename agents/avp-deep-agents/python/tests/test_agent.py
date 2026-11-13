"Native Deep Agents graphs and MCP clients feed the SDK Recorder."

import json
import subprocess
import sys
from pathlib import Path

import assertions as atif
import pytest
from conftest import reply
from langchain_core.messages import SystemMessage, ToolMessage
from pydantic import JsonValue

from avp.agent_cli import main
from avp_deep_agents import agent
from avp_deep_agents.descriptor import describe

MODEL: dict[str, JsonValue] = {"provider": "openai", "id": "gpt-4o-mini"}
FIXTURE = Path(__file__).resolve().parents[4] / "testing/mcp/avp_test_mcp.py"


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


def test_text_usage_and_commission_replaces_prompt(script, tmp_path):
    model = script(reply("DONE"))
    _, events = run_cli(
        tmp_path,
        system_prompt="SYSTEM",
        skills=[
            {
                "name": "greeting",
                "files": {
                    "SKILL.md": "---\nname: greeting\ndescription: Greeting\n---\nGREETING",
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
    system = next(m for m in model.requests[0] if isinstance(m, SystemMessage))
    assert system.text.startswith("SYSTEM\n\n## Skill: greeting")
    assert "SUPPORT" in system.text
    assert "filesystem" not in system.text.lower()
    message = atif.responses(events)[0]
    assert message["metrics"]["prompt_tokens"] == 1000
    assert message["metrics"]["cached_tokens"] == 400
    assert message["metrics"]["completion_tokens"] == 50
    assert atif.meta(message["metrics"])["reasoning_output_tokens"] == 10
    assert message["model_name"] == "gpt-4o-mini-2024-07-18"
    assert {
        "reason": atif.meta(events).get("stop_reason"),
        "output": atif.meta(events).get("output"),
    } == {"reason": "converged", "output": "DONE"}


@pytest.mark.parametrize(
    "fields",
    [
        {"agents": {"other": {}}},
        {"agents": {"avp-deep-agents": {"enabled_tools": ["missing"]}}},
        {"model": {"provider": "missing", "id": "model"}},
    ],
)
def test_invalid_commission_never_calls_model(script, tmp_path, fields):
    model = script()
    _, events = run_cli(tmp_path, **fields)
    assert (
        len(atif.responses(events)),
        len(atif.calls(events)),
        len(atif.errors(events)),
        atif.meta(events)["complete"],
    ) == (0, 0, 1, True)
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "invalid_commission"
    assert not model.requests


def test_filesystem_and_shell_run_in_the_launchers_workspace(script, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    model = script(
        reply("", ("write", "write_file", {"file_path": "/answer.txt", "content": "BOUNDARY"})),
        reply("", ("shell", "execute", {"command": "cat answer.txt"})),
        reply("DONE"),
    )
    _, events = run_cli(tmp_path)
    assert (tmp_path / "answer.txt").read_text() == "BOUNDARY"
    assert len(atif.responses(events)) == 3
    returned = atif.results(events)
    assert {r["source_call_id"] for r in returned} == {"write", "shell"}
    assert "BOUNDARY" in str(returned[-1]["content"])
    assert isinstance(model.requests[-1][-1], ToolMessage)
    assert atif.meta(events)["stop_reason"] == "converged"


def test_disabled_builtins_are_hidden_and_rejected(script, tmp_path):
    model = script(reply("", ("denied", "ls", {"path": "/"})), reply("DONE"))
    _, events = run_cli(
        tmp_path, agents={"avp-deep-agents": {"enabled_tools": [], "enabled_subagents": []}}
    )
    assert not events["agent"].get("tool_definitions")
    assert not any(model.tool_sets)
    returned = atif.results(events)[0]
    assert atif.meta(returned)["is_error"] is True
    assert "not enabled" in str(returned["content"])


@pytest.mark.parametrize("mode", ["parallel", "errors"])
def test_native_mcp_success_and_both_error_forms(script, tmp_path, mode):
    calls = [("one", "fixture_Avptest_Echo", {"text": "BOUNDARY"})]
    if mode == "parallel":
        calls.append(("two", "fixture_Avptest_Add", {"a": 2, "b": 3}))
    else:
        calls += [
            ("result", "fixture_Avptest_Fail", {"message": "BAD-RESULT", "mode": "result"}),
            ("protocol", "fixture_Avptest_Fail", {"message": "BAD-PROTOCOL", "mode": "protocol"}),
        ]
    script(reply("", *calls), reply("DONE"))
    _, events = run_cli(
        tmp_path,
        mcp_servers=[{"type": "stdio", "id": "fixture", "command": [sys.executable, str(FIXTURE)]}],
    )
    invoked = {item["tool_call_id"]: item for item in atif.calls(events)}
    returned = {item["source_call_id"]: item for item in atif.results(events)}
    assert set(invoked) == set(returned) == {call[0] for call in calls}
    assert all(atif.meta(item)["mcp_server_id"] == "fixture" for item in invoked.values())
    assert "BOUNDARY" in str(returned["one"]["content"])
    if mode == "errors":
        assert atif.meta(returned["result"])["is_error"] is True
        assert atif.meta(returned["protocol"])["is_error"] is True
    assert len(atif.responses(events)) == 2
    assert atif.meta(events)["stop_reason"] == "converged"


def test_native_general_purpose_subagent_has_its_own_frame(script, tmp_path):
    script(
        reply(
            "", ("child", "task", {"description": "Say CHILD", "subagent_type": "general-purpose"})
        ),
        reply("CHILD"),
        reply("DONE"),
    )
    _, events = run_cli(tmp_path)
    responses = atif.responses(events)
    assert len(responses) == 3
    assert len(atif.responses(events["subagent_trajectories"][0])) == 1
    assert len([s for s in events["steps"] if s["source"] == "agent"]) == 2
    assert len(atif.children(events)) == len(atif.children(events)) == 1
    ended = atif.children(events)[0]
    assert atif.meta(ended)["stop_reason"] == "converged"
    assert len(atif.responses(ended)) == 1
    assert atif.meta(events)["stop_reason"] == "converged"


def test_native_structured_output(script, tmp_path):
    script(reply('{"answer":42}'))
    _, events = run_cli(
        tmp_path,
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "integer"}},
            "required": ["answer"],
        },
    )
    assert {
        "reason": atif.meta(events).get("stop_reason"),
        "output": atif.meta(events).get("output"),
    } == {"reason": "converged", "output": {"answer": 42}}
    assert len(atif.responses(events)) == 1


def test_native_refusal(script, tmp_path):
    response = reply("")
    response.additional_kwargs["refusal"] = "Declined"
    script(response)
    _, events = run_cli(tmp_path)
    assert atif.responses(events)[0]["message"] == "Declined"
    assert atif.meta(atif.responses(events)[0])["message_metadata"][0]["annotations"]["refusal"]
    assert atif.meta(events)["stop_reason"] == "refused"


def test_missing_secret_is_an_auth_error(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_AVP_KEY", raising=False)
    _, events = run_cli(tmp_path, model={**MODEL, "credential": {"env": "MISSING_AVP_KEY"}})
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "auth_error"


def test_unreachable_mcp_stops_before_model(script, tmp_path):
    model = script()
    _, events = run_cli(
        tmp_path, mcp_servers=[{"id": "bad", "type": "stdio", "command": ["/nonexistent/mcp"]}]
    )
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "mcp_connect_failed"
    assert not model.requests


def test_ping_is_lazy_and_describe_lists_only_native_items(tmp_path):
    module = "import sys; from avp_deep_agents.cli import main; main(['ping']); assert 'deepagents' not in sys.modules"
    result = subprocess.run(
        [sys.executable, "-c", module], check=True, text=True, capture_output=True
    )
    assert json.loads(result.stdout)["type"] == "pong"
    descriptor = describe()
    assert {t.name for t in descriptor.tools or []} == {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
        "task",
    }
    assert [s.name for s in descriptor.subagents or []] == ["general-purpose"]


def test_subagent_tools_remain_scoped_when_parent_disables_them(script, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "child.txt").write_text("CHILD-TOOL")
    model = script(
        reply(
            "",
            (
                "child",
                "task",
                {"description": "Read child.txt", "subagent_type": "general-purpose"},
            ),
        ),
        reply("", ("read", "read_file", {"file_path": "/child.txt"})),
        reply("CHILD"),
        reply("DONE"),
    )
    _, events = run_cli(tmp_path, agents={"avp-deep-agents": {"enabled_tools": ["task"]}})
    started = events["agent"]
    assert [t["function"]["name"] for t in started["tool_definitions"]] == ["task"]
    assert "read_file" in {t["name"] for t in atif.effective(tmp_path)["subagents"][0]["tools"]}
    call = next(c for c in atif.calls(events) if c["tool_call_id"] == "read")
    result = next(c for c in atif.results(events) if c["source_call_id"] == "read")
    child = atif.children(events)[0]
    assert call in atif.calls(child) and result in atif.results(child)
    assert "CHILD-TOOL" in str(result["content"])
    assert "read_file" not in model.tool_sets[0] and "read_file" in model.tool_sets[1]


def test_invalid_subagent_type_never_opens_a_frame(script, tmp_path):
    script(
        reply("", ("unknown", "task", {"description": "Go", "subagent_type": "missing"})),
        reply("DONE"),
    )
    _, events = run_cli(tmp_path)
    assert not atif.children(events)
    assert len(atif.results(events)) == 1
    assert atif.meta(events)["stop_reason"] == "converged"


def test_bad_structured_output_fails_after_native_validation(script, tmp_path):
    script(reply('{"answer":"wrong"}'))
    _, events = run_cli(
        tmp_path,
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "integer"}},
            "required": ["answer"],
        },
    )
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "output_invalid"
    assert atif.meta(events)["stop_reason"] == "error"


def test_context_compaction_fails_visibly_before_internal_model_call(script, tmp_path, monkeypatch):
    import deepagents.middleware.summarization as native

    monkeypatch.chdir(tmp_path)
    defaults = native.compute_summarization_defaults

    def small_context(model):
        result = defaults(model)
        result["trigger"] = ("messages", 2)
        result["keep"] = ("messages", 1)
        return result

    monkeypatch.setattr(native, "compute_summarization_defaults", small_context)
    model = script(reply("", ("listed", "ls", {"path": "/"})), reply("UNEXPECTED"))
    with pytest.raises(ValueError, match="compaction"):
        run_cli(tmp_path)
    events = atif.load(tmp_path / "trajectory.json")
    assert len(model.requests) == 1
    assert "compaction" in atif.errors(events)[-1]["message"]
    assert atif.meta(events)["stop_reason"] == "error"


def test_provider_rate_limit_is_a_terminal_error(script, tmp_path):
    import httpx2 as httpx
    from anthropic import RateLimitError

    response = httpx.Response(
        429, request=httpx.Request("POST", "https://example.test/v1/messages")
    )
    script(
        RateLimitError(
            "quota exhausted", response=response, body={"error": {"type": "rate_limit_error"}}
        )
    )
    _, events = run_cli(tmp_path)
    assert not atif.responses(events)
    assert atif.meta(atif.errors(events)[-1])["error_code"] == "rate_limit"
    assert atif.meta(events)["stop_reason"] == "error"


@pytest.mark.parametrize(
    "provider,model_id",
    [("openai", "gpt-4o-mini"), ("anthropic", "claude-haiku-4-5"), ("google", "gemini-2.5-flash")],
)
def test_native_models_accept_proxy_and_env_credentials(provider, model_id, monkeypatch):
    from avp.commission import Commission
    from avp_deep_agents import commission as cm

    monkeypatch.setenv("AVP_TEST_KEY", "env-stand-in")
    for credential, expected in [
        ({"proxy": "vault-name"}, "avp-proxy-stand-in"),
        ({"env": "AVP_TEST_KEY"}, "env-stand-in"),
    ]:
        commission = Commission.model_validate(
            {
                "avp_version": "0.1",
                "run_id": "auth-test",
                "model": {
                    "provider": provider,
                    "id": model_id,
                    "credential": credential,
                    "base_url": "https://proxy.example.test/v1",
                },
                "prompt": "Go",
            }
        )
        native = cm.model(commission)
        field = {
            "openai": "openai_api_key",
            "anthropic": "anthropic_api_key",
            "google": "google_api_key",
        }[provider]
        assert getattr(native, field).get_secret_value() == expected
        if provider == "openai":
            assert native.openai_api_base == "https://proxy.example.test/v1"
            assert native.use_responses_api is True
        elif provider == "anthropic":
            assert native.anthropic_api_url == "https://proxy.example.test/v1"
        else:
            assert native.base_url == "https://proxy.example.test/v1"


def test_cancellation_closes_the_native_run_as_interrupted(script, tmp_path):
    import asyncio

    events = []

    async def scenario():
        entered = asyncio.Event()

        async def waiting(messages):
            entered.set()
            await asyncio.Future()

        script(waiting)

        async def sink(event):
            events.append(event.trajectory.to_json_dict())

        task = asyncio.create_task(
            agent.run(
                {"avp_version": "0.1", "run_id": "cancel", "model": MODEL, "prompt": "Wait"}, sink
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    events = events[-1]
    assert atif.meta(events)["stop_reason"] == "interrupted"
    assert atif.meta(events)["complete"]
