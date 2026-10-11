"""Opt-in native Codex/MCP seam with a local scripted Responses endpoint.

AVP_TEST_CODEX=1 uv run --no-sync pytest agents/avp-codex/python/tests/test_native.py
No paid model call. Requires the pinned Codex CLI and localhost sockets.
"""

from __future__ import annotations

import http.server
import json
import os
import threading
from pathlib import Path

import pytest
from test_agent import run_cli

pytestmark = pytest.mark.skipif(
    os.environ.get("AVP_TEST_CODEX") != "1", reason="native Codex integration is opt-in"
)
ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("operation", ["mcp", "shell_error"])
def test_native_roundtrip(tmp_path, monkeypatch, operation):
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            index = len(requests)
            if index == 1:
                item = {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "namespace": "mcp__avptest",
                    "name": "Avptest_Echo",
                    "arguments": '{"text":"AVP-MCP-ROUNDTRIP"}',
                }
                if operation == "shell_error":
                    item = {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "exec_command",
                        "arguments": '{"cmd":"exit 7"}',
                    }
            else:
                item = {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "AVP-MCP-ROUNDTRIP"}],
                }
            response = {
                "id": f"resp_{index}",
                "object": "response",
                "status": "completed",
                "model": body["model"],
                "output": [item],
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
                },
                {"type": "response.output_item.added", "output_index": 0, "item": item},
                {"type": "response.output_item.done", "output_index": 0, "item": item},
                {"type": "response.completed", "response": response},
            ]
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
    assert code == 0
    assert len(requests) == 2
    assert events[-1]["data"]["avp.reason"] == "converged"
    returned = next(
        e["data"]["avp.tool_result"] for e in events if e["type"] == "avp.tool_returned"
    )
    assert returned["is_error"] is (operation == "shell_error")
    if operation == "mcp":
        assert "AVP-MCP-ROUNDTRIP" in json.dumps(returned["content"])
    assert [
        e["data"]["avp.usage"]["input_tokens"]
        for e in events
        if e["type"] == "avp.assistant_message"
    ] == [100, 200]
    # No host skill catalog can leak into the model's instructions.
    assert "<skills_instructions>" not in json.dumps(requests[0])
    assert any(item["type"] == "function_call_output" for item in requests[1]["input"])
