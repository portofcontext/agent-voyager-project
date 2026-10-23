"""Opt-in native Codex/MCP boundary with a local scripted Responses endpoint.

AVP_TEST_CODEX=1 uv run --no-sync pytest agents/avp-codex/python/tests/test_native.py
No paid model call. Uses the SDK-bundled Codex CLI and requires localhost sockets.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import sys
import threading
from pathlib import Path

import pytest
from test_agent import run_cli

from avp.launch import directory_env
from avp_codex import agent
from avp_codex.translate import notification_params

pytestmark = pytest.mark.skipif(
    os.environ.get("AVP_TEST_CODEX") != "1", reason="native Codex integration is opt-in"
)
ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def native_context(tmp_path, monkeypatch):
    # This test is the launcher: the adapter must not replace or clean up state.
    for name, value in directory_env(tmp_path / "runtime", tmp_path).items():
        Path(value).mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(name, value)
    (Path(os.environ["CODEX_HOME"]) / "config.toml").write_text(
        'sandbox_mode = "danger-full-access"\n'
    )


@pytest.mark.parametrize(
    "operation",
    [
        "mcp",
        "mcp_search",
        "mcp_parallel",
        "mcp_fail",
        "shell_error",
        "shell_poll",
        "http_retry",
        "partial_retry",
    ],
)
def test_native_roundtrip(tmp_path, monkeypatch, operation):
    requests = []
    observed = []

    class ObservedSDK(agent.AsyncCodexClient):
        async def thread_start(self, params):
            started = await super().thread_start(params)
            assert started.sandbox.model_dump(mode="json")["type"] == "dangerFullAccess"
            return started

        async def next_turn_notification(self, turn_id):
            event = await super().next_turn_notification(turn_id)
            observed.append((event.method, notification_params(event)))
            return event

    monkeypatch.setattr(agent, "AsyncCodexClient", ObservedSDK)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            index = len(requests)
            if operation == "http_retry":
                if index == 1:
                    self.send_error(503, "scripted transient failure")
                    return
                index -= 1
            if operation == "mcp_search" and index == 1:
                item = {
                    "type": "tool_search_call",
                    "id": "tsc_1",
                    "call_id": "search_1",
                    "status": "completed",
                    "execution": "client",
                    "arguments": {"query": "avptest echo", "limit": 5},
                }
            elif index == 1 or (operation == "mcp_search" and index == 2):
                if operation == "mcp_search":
                    outputs = [i for i in body["input"] if i["type"] == "tool_search_output"]
                    assert outputs and "Avptest_Echo" in json.dumps(outputs)
                item = {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "namespace": "mcp__avptest",
                    "name": "Avptest_Echo",
                    "arguments": '{"text":"AVP-MCP-ROUNDTRIP"}',
                }
                if operation in ("shell_error", "shell_poll"):
                    item = {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "exec_command",
                        "arguments": json.dumps(
                            {"cmd": "exit 7"}
                            if operation == "shell_error"
                            else {"cmd": "sleep 2; printf done", "yield_time_ms": 1000}
                        ),
                    }
            elif operation == "shell_poll" and index == 2:
                outputs = [i for i in body["input"] if i["type"] == "function_call_output"]
                session = re.search(r"Process running with session ID (\d+)", json.dumps(outputs))
                assert session, outputs
                item = {
                    "type": "function_call",
                    "id": "fc_2",
                    "call_id": "call_2",
                    "name": "write_stdin",
                    "arguments": json.dumps(
                        {
                            "session_id": int(session[1]),
                            "chars": "",
                            "yield_time_ms": 1000,
                        }
                    ),
                }
            else:
                item = {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "AVP-MCP-ROUNDTRIP"}],
                }
            items = [item]
            if operation == "mcp_parallel" and index == 1:
                items.append({**item, "id": "fc_2", "call_id": "call_2"})
            if operation == "mcp_fail" and index == 1:
                # A success, an isError result, and a JSON-RPC error in one response.
                items.extend(
                    {
                        **item,
                        "id": f"fc_{n}",
                        "call_id": f"call_{n}",
                        "name": "Avptest_Fail",
                        "arguments": json.dumps({"message": f"AVP-FAIL-{mode}", "mode": mode}),
                    }
                    for n, mode in ((2, "result"), (3, "protocol"))
                )
            response = {
                "id": f"resp_{index}",
                "object": "response",
                "status": "completed",
                "model": body["model"],
                "output": items,
                "usage": {
                    "input_tokens": 100 * index,
                    "output_tokens": 5,
                    "total_tokens": 100 * index + 5,
                },
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            events = [
                {
                    "type": "response.created",
                    "response": {**response, "status": "in_progress", "output": []},
                }
            ]
            for offset, output in enumerate(items):
                events.extend(
                    [
                        {
                            "type": "response.output_item.added",
                            "output_index": offset,
                            "item": output,
                        },
                        {
                            "type": "response.output_item.done",
                            "output_index": offset,
                            "item": output,
                        },
                    ]
                )
            if operation != "partial_retry" or index != 1:
                events.append({"type": "response.completed", "response": response})
            for event in events:
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("OPENAI_API_KEY", "local-scripted-key")
    monkeypatch.setenv("AVP_WORKSPACE", str(tmp_path))
    try:
        code, events = run_cli(
            tmp_path,
            raises=operation == "partial_retry",
            model="openai/gpt-5.5" if operation == "mcp_search" else "openai/gpt-5-mini",
            provider={"id": "openai", "base_url": f"http://127.0.0.1:{server.server_port}/v1"},
            mcp_servers=[
                {
                    "id": "avptest",
                    "type": "stdio",
                    "command": [sys.executable, str(ROOT / "testing/mcp/avp_test_mcp.py")],
                }
            ],
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    if operation == "partial_retry":
        assert events[-1]["data"]["avp.reason"] == "error"
        assert any("partial response" in e["data"].get("avp.error.message", "") for e in events)
        return
    assert code == 0
    assert len(requests) == (3 if operation in ("shell_poll", "http_retry", "mcp_search") else 2)
    assert events[-1]["data"]["avp.reason"] == "converged"
    returned = next(
        e["data"]["avp.tool_result"]
        for e in events
        if e["type"] == "avp.tool_returned"
        and e["data"]["avp.tool_result"]["tool_use_id"] == "call_1"
    )
    assert returned["is_error"] is (operation == "shell_error")
    if operation in ("mcp", "mcp_search", "mcp_parallel", "mcp_fail", "http_retry"):
        assert "AVP-MCP-ROUNDTRIP" in json.dumps(returned["content"])
    assert [
        e["data"]["avp.usage"]["input_tokens"]
        for e in events
        if e["type"] == "avp.assistant_message"
    ] == ([100, 200, 300] if operation in ("shell_poll", "mcp_search") else [100, 200])
    invoked = [e["data"] for e in events if e["type"] == "avp.tool_invoked"]
    returned_ids = [
        e["data"]["avp.tool_result"]["tool_use_id"]
        for e in events
        if e["type"] == "avp.tool_returned"
    ]
    assert sorted(returned_ids) == (
        ["call_1", "call_2", "call_3"]
        if operation == "mcp_fail"
        else ["call_1", "call_2"]
        if operation in ("mcp_parallel", "shell_poll")
        else ["call_1", "search_1"]
        if operation == "mcp_search"
        else ["call_1"]
    )
    if operation == "mcp_search":
        assert [e["avp.tool.name"] for e in invoked] == ["tool_search", "mcp__avptest.Avptest_Echo"]
        search = next(
            e["data"]["avp.tool_result"]
            for e in events
            if e["type"] == "avp.tool_returned"
            and e["data"]["avp.tool_result"]["tool_use_id"] == "search_1"
        )
        assert search["is_error"] is False
        assert "Avptest_Echo" in json.dumps(search["structured_content"])
    if operation == "mcp_fail":
        results = {
            e["data"]["avp.tool_result"]["tool_use_id"]: e["data"]["avp.tool_result"]
            for e in events
            if e["type"] == "avp.tool_returned"
        }
        assert sorted(results) == ["call_1", "call_2", "call_3"]
        assert results["call_1"]["is_error"] is False
        assert "AVP-MCP-ROUNDTRIP" in json.dumps(results["call_1"]["content"])
        for call, mode in (("call_2", "result"), ("call_3", "protocol")):
            assert results[call]["is_error"] is True, results[call]
            text = json.dumps(results[call]["content"])
            assert f"AVP-FAIL-{mode}" in text
            assert (
                "AVP-MCP-ROUNDTRIP" not in text
                and "AVP-FAIL-" + ("protocol" if mode == "result" else "result") not in text
            )
        messages = [e for e in events if e["type"] == "avp.assistant_message"]
        assert len([b for b in messages[0]["data"]["avp.content"] if b["type"] == "tool_use"]) == 3
    if operation == "mcp_parallel":
        messages = [e for e in events if e["type"] == "avp.assistant_message"]
        assert len([b for b in messages[0]["data"]["avp.content"] if b["type"] == "tool_use"]) == 2
    if operation == "shell_poll":
        assert [e["avp.tool.name"] for e in invoked] == ["exec_command", "write_stdin"]
        assert invoked[0]["avp.tool.input"] == {
            "cmd": "sleep 2; printf done",
            "yield_time_ms": 1000,
        }
        assert invoked[1]["avp.tool.input"]["chars"] == ""
        assert isinstance(invoked[1]["avp.tool.input"]["session_id"], int)
        # Typed command items normalize execution and omit the original function
        # name/JSON arguments. Raw items preserve distinct exec and poll calls.
        commands = [
            d["item"]
            for m, d in observed
            if m == "item/completed" and d["item"]["type"] == "commandExecution"
        ]
        assert commands
        assert all("name" not in i and "arguments" not in i for i in commands)
    usage_events = [d["tokenUsage"] for m, d in observed if m == "thread/tokenUsage/updated"]
    assert usage_events[-1]["last"]["inputTokens"] == (
        300 if operation in ("shell_poll", "mcp_search") else 200
    )
    assert usage_events[-1]["total"]["inputTokens"] == (
        600 if operation in ("shell_poll", "mcp_search") else 300
    )
    # No host skill catalog can leak into the model's instructions.
    assert "<skills_instructions>" not in json.dumps(requests[0])
    assert any(item["type"] == "function_call_output" for item in requests[-1]["input"])


@pytest.mark.parametrize(
    "model, allowed, with_mcp",
    [
        ("gpt-5-mini", [], False),
        ("gpt-5-mini", ["exec_command", "write_stdin"], False),
        ("gpt-5-mini", ["view_image"], False),
        ("gpt-5.5", [], False),
        ("gpt-5.5", ["request_user_input"], False),
        ("gpt-5.5", ["apply_patch"], False),
        ("gpt-5.5", ["apply_patch", "view_image"], False),
        ("gpt-5.5", ["apply_patch", "exec_command", "write_stdin"], False),
        (
            "gpt-5-mini",
            ["list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"],
            True,
        ),
    ],
)
def test_native_allowlist_filters_model_request(tmp_path, monkeypatch, model, allowed, with_mcp):
    # Exceed Codex's default optional startup grace: managed tools must still
    # be ready before the filtered run records its initial catalog.
    slow_mcp = tmp_path / "slow_mcp.py"
    slow_mcp.write_text(
        "import os, sys, time\ntime.sleep(1.5)\nos.execv(sys.executable, "
        + repr([sys.executable, str(ROOT / "testing/mcp/avp_test_mcp.py")])
        + ")\n"
    )
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            item = {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "DONE"}],
            }
            response = {
                "id": "resp_1",
                "object": "response",
                "status": "completed",
                "model": body["model"],
                "output": [item],
                "usage": {"input_tokens": 100, "output_tokens": 5, "total_tokens": 105},
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for event in [
                {
                    "type": "response.created",
                    "response": {**response, "status": "in_progress", "output": []},
                },
                {"type": "response.output_item.added", "output_index": 0, "item": item},
                {"type": "response.output_item.done", "output_index": 0, "item": item},
                {"type": "response.completed", "response": response},
            ]:
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("OPENAI_API_KEY", "local-scripted-key")
    monkeypatch.setenv("AVP_WORKSPACE", str(tmp_path))
    # Routed the way a launcher routes it, through the environment.
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    try:
        code, events = run_cli(
            tmp_path,
            model=f"openai/{model}",
            enabled_builtin_tools={"avp-codex": allowed},
            mcp_servers=[
                {
                    "id": "avptest",
                    "type": "stdio",
                    "command": [sys.executable, str(slow_mcp)],
                }
            ]
            if with_mcp
            else [],
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert code == 0
    assert events[-1]["data"]["avp.reason"] == "converged"
    assert len(requests) == 1
    # Check the actual model request, not just our declared AVP catalog.
    assert {t["name"] for t in requests[0]["tools"]} == (
        set(allowed) | ({"mcp__avptest"} if with_mcp else set())
    )
    started = next(e["data"] for e in events if e["type"] == "avp.agent_started")
    assert {t["name"] for t in started["avp.tools"] if not t.get("avp.mcp_server_id")} == set(
        allowed
    )
    if with_mcp:
        assert any(t.get("avp.mcp_server_id") == "avptest" for t in started["avp.tools"])
