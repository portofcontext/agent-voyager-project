"""Opt-in native Codex/MCP seam with a local scripted Responses endpoint.

AVP_TEST_CODEX=1 uv run --no-sync pytest agents/avp-codex/python/tests/test_native.py
No paid model call. Uses the SDK-bundled Codex CLI and requires localhost sockets.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import threading
from pathlib import Path

import pytest
from test_agent import run_cli

from avp_codex import agent
from avp_codex.translate import notification_params

pytestmark = pytest.mark.skipif(
    os.environ.get("AVP_TEST_CODEX") != "1", reason="native Codex integration is opt-in"
)
ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    "operation", ["mcp", "mcp_parallel", "shell_error", "shell_poll", "http_retry", "partial_retry"]
)
def test_native_roundtrip(tmp_path, monkeypatch, operation):
    requests = []
    observed = []

    class ObservedSDK(agent.AsyncCodexClient):
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
            if index == 1:
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
            provider={"id": "openai", "base_url": f"http://127.0.0.1:{server.server_port}/v1"},
            mcp_servers=[
                {
                    "id": "avptest",
                    "type": "stdio",
                    "command": ["uv", "run", str(ROOT / "testing/mcp/avp_test_mcp.py")],
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
    assert len(requests) == (3 if operation in ("shell_poll", "http_retry") else 2)
    assert events[-1]["data"]["avp.reason"] == "converged"
    returned = next(
        e["data"]["avp.tool_result"] for e in events if e["type"] == "avp.tool_returned"
    )
    assert returned["is_error"] is (operation == "shell_error")
    if operation in ("mcp", "mcp_parallel", "http_retry"):
        assert "AVP-MCP-ROUNDTRIP" in json.dumps(returned["content"])
    assert [
        e["data"]["avp.usage"]["input_tokens"]
        for e in events
        if e["type"] == "avp.assistant_message"
    ] == ([100, 200, 300] if operation == "shell_poll" else [100, 200])
    invoked = [e["data"] for e in events if e["type"] == "avp.tool_invoked"]
    returned_ids = [
        e["data"]["avp.tool_result"]["tool_use_id"]
        for e in events
        if e["type"] == "avp.tool_returned"
    ]
    assert sorted(returned_ids) == (
        ["call_1", "call_2"] if operation in ("mcp_parallel", "shell_poll") else ["call_1"]
    )
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
    assert usage_events[-1]["last"]["inputTokens"] == (300 if operation == "shell_poll" else 200)
    assert usage_events[-1]["total"]["inputTokens"] == (600 if operation == "shell_poll" else 300)
    # No host skill catalog can leak into the model's instructions.
    assert "<skills_instructions>" not in json.dumps(requests[0])
    assert any(item["type"] == "function_call_output" for item in requests[-1]["input"])
