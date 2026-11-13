"""The bundled Codex runtime against local Responses and MCP servers; no API credits."""

import asyncio
import http.server
import json
import os
import re
import ssl
import subprocess
import sys
import threading
from pathlib import Path

import assertions as atif
import pytest
from test_agent import MODEL, run_cli

from avp_codex import agent

pytestmark = pytest.mark.skipif(
    os.environ.get("AVP_TEST_CODEX") != "1", reason="native Codex integration is opt-in"
)
ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def launcher(tmp_path, monkeypatch):
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text('sandbox_mode = "danger-full-access"\n')
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.chdir(tmp_path)

    class BoundedClient(agent.AsyncCodexClient):
        async def next_turn_notification(self, turn_id):
            return await asyncio.wait_for(super().next_turn_notification(turn_id), 20)

    monkeypatch.setattr(agent, "AsyncCodexClient", BoundedClient)


@pytest.fixture
def model_endpoint():
    running = []

    def start(script, *, certificate=None, key=None):
        requests = []
        headers = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args) -> None:
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(request)
                headers.append(dict(self.headers))
                index = len(requests)
                items = script(request, index)
                response = {
                    "id": f"response-{index}",
                    "object": "response",
                    "model": request["model"],
                    "status": "completed",
                    "output": items,
                    "usage": {
                        "input_tokens": index * 100,
                        "output_tokens": 5,
                        "total_tokens": index * 100 + 5,
                    },
                }
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                events: list[dict] = [
                    {
                        "type": "response.created",
                        "response": {**response, "status": "in_progress", "output": []},
                    }
                ]
                for position, item in enumerate(items):
                    events += [
                        {
                            "type": "response.output_item.added",
                            "output_index": position,
                            "item": item,
                        },
                        {
                            "type": "response.output_item.done",
                            "output_index": position,
                            "item": item,
                        },
                    ]
                events.append({"type": "response.completed", "response": response})
                for e in events:
                    self.wfile.write(("data: " + json.dumps(e) + "\n\n").encode())
                    self.wfile.flush()

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        scheme = "http"
        if certificate:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(certificate, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            scheme = "https"
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        running.append((server, worker))
        return (f"{scheme}://127.0.0.1:{server.server_port}/v1", requests, headers)

    yield start
    for server, worker in running:
        server.shutdown()
        server.server_close()
        worker.join()


def message(value="DONE"):
    return {
        "id": "answer",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": value}],
    }


def function(name, arguments, call_id="call"):
    return {
        "id": call_id,
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(arguments),
    }


@pytest.mark.parametrize(
    "operation", ["mcp", "parallel", "tool_error", "shell_poll", "tool_search"]
)
def test_native_tool_round_trips_keep_response_boundaries(model_endpoint, tmp_path, operation):

    def script(request, index):
        if operation == "tool_search" and index == 1:
            return [
                {
                    "id": "search-item",
                    "type": "tool_search_call",
                    "call_id": "search",
                    "status": "completed",
                    "execution": "client",
                    "arguments": {"query": "fixture echo", "limit": 5},
                }
            ]
        tool_turn = 2 if operation == "tool_search" else 1
        if index == tool_turn:
            if operation == "shell_poll":
                return [
                    function("exec_command", {"cmd": "sleep 2; printf done", "yield_time_ms": 1000})
                ]
            call = {**function("Avptest_Echo", {"text": "BOUNDARY"}), "namespace": "mcp__fixture"}
            if operation == "parallel":
                return [call, {**call, "id": "second", "call_id": "second"}]
            if operation == "tool_error":
                return [
                    call,
                    {
                        **function(
                            "Avptest_Fail", {"message": "EXPECTED", "mode": "result"}, "failed"
                        ),
                        "namespace": "mcp__fixture",
                    },
                ]
            return [call]
        if operation == "shell_poll" and index == 2:
            outputs = json.dumps(
                [item for item in request["input"] if item["type"] == "function_call_output"]
            )
            session = re.search("Process running with session ID (\\d+)", outputs)
            assert session, outputs
            return [
                function(
                    "write_stdin",
                    {"session_id": int(session[1]), "chars": "", "yield_time_ms": 1000},
                    "poll",
                )
            ]
        return [message()]

    url, requests, headers = model_endpoint(script)
    model = {
        **MODEL,
        "id": "gpt-5.5" if operation == "tool_search" else MODEL["id"],
        "base_url": url,
        "credential": {"proxy": "openai"},
    }
    code, events = run_cli(
        tmp_path,
        model=model,
        mcp_servers=[
            {
                "id": "fixture",
                "type": "stdio",
                "command": [sys.executable, str(ROOT / "testing/mcp/avp_test_mcp.py")],
            }
        ],
    )
    assert code == 0
    assert {
        "reason": atif.meta(events).get("stop_reason"),
        "output": atif.output(events),
    } == {"reason": "converged", "output": "DONE"}
    messages = atif.responses(events)
    assert [item["metrics"]["prompt_tokens"] for item in messages] == (
        [100, 200, 300] if operation in {"shell_poll", "tool_search"} else [100, 200]
    )
    invoked = atif.calls(events)
    returned = {e["source_call_id"]: e for e in atif.results(events)}
    assert {item["tool_call_id"] for item in invoked} == set(returned)
    if operation == "shell_poll":
        assert [item["function_name"] for item in invoked] == ["exec_command", "write_stdin"]
        assert "done" in str(returned["poll"]["content"])
    else:
        assert "BOUNDARY" in str(returned["call"]["content"])
        assert (
            atif.mcp_server(
                tmp_path, next(item for item in invoked if item["tool_call_id"] == "call")
            )
            == "fixture"
        )
    if operation == "tool_error":
        assert atif.meta(returned["failed"])["is_error"] is True
        assert atif.meta(returned["call"])["is_error"] is False
    if operation == "tool_search":
        assert "Avptest_Echo" in str(atif.meta(returned["search"])["structured_content"])
    assert all(
        header.get("authorization", header.get("Authorization")) == "Bearer avp-proxy-stand-in"
        for header in headers
    )
    assert "<skills_instructions>" not in json.dumps(requests[0])


@pytest.mark.parametrize(
    "model,allowed",
    [
        ("gpt-5-mini", []),
        ("gpt-5-mini", ["exec_command", "write_stdin"]),
        ("gpt-5-mini", ["view_image"]),
        ("gpt-5.5", []),
        ("gpt-5.5", ["apply_patch"]),
        ("gpt-5.5", ["apply_patch", "exec_command", "write_stdin"]),
    ],
)
def test_native_enabled_tools_match_the_model_request(model_endpoint, tmp_path, model, allowed):
    url, requests, _ = model_endpoint(lambda request, index: [message()])
    _, events = run_cli(
        tmp_path,
        model={
            "provider": "openai",
            "id": model,
            "base_url": url,
            "credential": {"proxy": "openai"},
        },
        agents={"avp-codex": {"enabled_tools": allowed}},
    )
    assert atif.meta(events)["stop_reason"] == "converged"
    assert len(requests) == 1
    assert {tool["name"] for tool in requests[0]["tools"]} == set(allowed)
    assert {
        tool["function"]["name"] for tool in events["agent"].get("tool_definitions", [])
    } == set(allowed)


def test_native_http_client_trusts_the_launcher_ca(model_endpoint, tmp_path, monkeypatch):
    cert = tmp_path / "ca.pem"
    ca_key = tmp_path / "ca-key.pem"
    key = tmp_path / "leaf-key.pem"
    leaf = tmp_path / "leaf.pem"
    csr = tmp_path / "leaf.csr"
    extensions = tmp_path / "extensions.cnf"
    extensions.write_text(
        "basicConstraints=critical,CA:FALSE\nsubjectAltName=DNS:localhost,IP:127.0.0.1\n"
    )
    commands = [
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(ca_key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=AVP Test CA",
        ],
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(csr),
            "-subj",
            "/CN=localhost",
        ],
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr),
            "-CA",
            str(cert),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(leaf),
            "-days",
            "1",
            "-extfile",
            str(extensions),
        ],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True)
    monkeypatch.setenv("SSL_CERT_FILE", str(cert))
    url, requests, _ = model_endpoint(lambda request, index: [message()], certificate=leaf, key=key)
    _, events = run_cli(
        tmp_path, model={**MODEL, "base_url": url, "credential": {"proxy": "openai"}}
    )
    assert atif.meta(events)["stop_reason"] == "converged"
    assert len(requests) == 1
