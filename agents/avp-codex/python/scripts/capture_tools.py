"""Capture the pinned Codex profile's built-in definitions from local model requests.

Run from this project: `uv run python scripts/capture_tools.py`. No API credits.
"""

import asyncio
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from avp_codex import agent, descriptor

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1] / "src/avp_codex/tools.json"


def capture(model: str) -> dict:
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                b'{"error":{"message":"AVP tool capture","type":"invalid_request_error"}}'
            )

    async def discard(event):
        pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    previous_cwd, previous_home = Path.cwd(), os.environ.get("CODEX_HOME")
    try:
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as workspace:
            os.environ["CODEX_HOME"] = home
            os.chdir(workspace)
            received: dict[str, Any] = {
                "avp_version": "0.1",
                "run_id": "capture",
                "prompt": "hi",
                "model": {
                    "provider": "openai",
                    "id": model,
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "credential": {"proxy": "capture"},
                },
                "mcp_servers": [
                    {
                        "id": "fixture",
                        "type": "stdio",
                        "command": [sys.executable, str(ROOT / "testing/mcp/avp_test_mcp.py")],
                    }
                ],
            }
            asyncio.run(asyncio.wait_for(agent.run(received, discard), 60))
    finally:
        os.chdir(previous_cwd)
        if previous_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous_home
        server.shutdown()
        server.server_close()
        worker.join()
    definitions = {}
    for tool in requests[0]["tools"]:
        name = tool.get("name", tool["type"])
        if name not in descriptor.BUILTIN_TOOLS:
            continue
        description = tool["description"]
        if name == "tool_search":
            # Its source list is run-specific, rather than part of the built-in definition.
            description = description.split("\n\nYou have access")[0]
        definitions[name] = {"description": description, "inputSchema": tool.get("parameters")}

    return definitions


if __name__ == "__main__":
    models = {model: capture(model) for model in ("gpt-5-mini", "gpt-5.5")}
    OUT.write_text(json.dumps({"codex": agent.CODEX_VERSION, "models": models}, indent=2) + "\n")
    print(f"wrote {OUT}")
