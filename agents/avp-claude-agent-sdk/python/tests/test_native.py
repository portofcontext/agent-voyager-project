"""The real pinned Claude CLI against a local Anthropic endpoint and stdio MCP."""

import http.server
import json
import os
import sys
import threading
from pathlib import Path

import assertions as atif
import pytest
from test_agent import MODEL, run_cli

pytestmark = pytest.mark.skipif(
    os.environ.get("AVP_TEST_CLAUDE") != "1", reason="native Claude integration is opt-in"
)
ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def endpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    requests = []
    headers = []
    calls = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            headers.append(dict(self.headers))
            index = len(requests)
            blocks = calls.pop(0) if calls else [{"type": "text", "text": "DONE"}]
            message = {
                "id": f"message-{index}",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": index * 10,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 3,
                    "cache_creation_input_tokens": 2,
                },
            }
            events: list[dict] = [{"type": "message_start", "message": message}]
            for i, block in enumerate(blocks):
                events.append(
                    {
                        "type": "content_block_start",
                        "index": i,
                        "content_block": {**block, "input": {}}
                        if block["type"] == "tool_use"
                        else {**block, "text": ""},
                    }
                )
                delta = (
                    {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
                    if block["type"] == "tool_use"
                    else {"type": "text_delta", "text": block["text"]}
                )
                events += [
                    {"type": "content_block_delta", "index": i, "delta": delta},
                    {"type": "content_block_stop", "index": i},
                ]
            events += [
                {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": "tool_use"
                        if any(b["type"] == "tool_use" for b in blocks)
                        else "end_turn",
                        "stop_sequence": None,
                    },
                    "usage": {"output_tokens": 4},
                },
                {"type": "message_stop"},
            ]
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            for e in events:
                self.wfile.write(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode())
                self.wfile.flush()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield (f"http://127.0.0.1:{server.server_port}", requests, headers, calls)
    server.shutdown()
    server.server_close()
    worker.join()


@pytest.mark.parametrize("operation", ["text", "shell", "mcp", "mcp_error"])
def test_native_round_trip(endpoint, tmp_path, operation):
    url, requests, headers, calls = endpoint
    fields = {}
    if operation == "shell":
        calls.append(
            [
                {
                    "type": "tool_use",
                    "id": "call",
                    "name": "Bash",
                    "input": {"command": "printf BOUNDARY"},
                }
            ]
        )
    if operation.startswith("mcp"):
        fields["mcp_servers"] = [
            {
                "id": "fixture",
                "type": "stdio",
                "command": [sys.executable, str(ROOT / "testing/mcp/avp_test_mcp.py")],
            }
        ]
        name = "Avptest_Fail" if operation == "mcp_error" else "Avptest_Echo"
        arguments = (
            {"message": "EXPECTED", "mode": "result"}
            if operation == "mcp_error"
            else {"text": "BOUNDARY"}
        )
        calls.append(
            [
                {
                    "type": "tool_use",
                    "id": "call",
                    "name": f"mcp__fixture__{name}",
                    "input": arguments,
                }
            ]
        )
    _, events = run_cli(
        tmp_path, model={**MODEL, "base_url": url, "credential": {"proxy": "anthropic"}}, **fields
    )
    assert {
        "reason": atif.meta(events).get("stop_reason"),
        "output": atif.output(events),
    } == {"reason": "converged", "output": "DONE"}
    responses = atif.responses(events)
    assert [e["metrics"]["prompt_tokens"] for e in responses] == (
        [15] if operation == "text" else [15, 25]
    )
    assert all(h.get("x-api-key") == "avp-proxy-stand-in" for h in headers)
    if operation != "text":
        result = atif.results(events)[0]
        assert result["source_call_id"] == "call"
        assert atif.meta(result).get("is_error", False) == (operation == "mcp_error")
        assert ("EXPECTED" if operation == "mcp_error" else "BOUNDARY") in str(result["content"])
    assert len(requests) == len(responses)


def test_native_gateway_bearer_auth_is_launcher_owned(endpoint, tmp_path, monkeypatch):
    url, _, headers, _ = endpoint
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "avp-gateway-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _, events = run_cli(tmp_path, model={**MODEL, "base_url": url})
    assert atif.meta(events)["stop_reason"] == "converged"
    assert (
        headers[0].get("authorization", headers[0].get("Authorization"))
        == "Bearer avp-gateway-token"
    )
