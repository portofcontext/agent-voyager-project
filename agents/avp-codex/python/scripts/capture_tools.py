"""Regenerate src/avp_codex/tools.json from the pinned Codex CLI.

Codex defines its built-in tools in the binary and sends them only on the
model request. This runs the adapter once per verified model against a local
stand-in for the Responses API, records the `tools` on the first request,
refuses it (400), and writes each built-in's description and input schema.
Run after updating the openai-codex dependency pin:

    uv run python agents/avp-codex/python/scripts/capture_tools.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from avp.commission import Commission
from avp_codex import agent
from avp_codex import commission as cm

MODELS = ["gpt-5-mini", "gpt-5.5"]
OUT = Path(__file__).resolve().parents[1] / "src" / "avp_codex" / "tools.json"
# Codex sends its MCP resource tools only when an MCP server is configured.
TEST_MCP = Path(__file__).resolve().parents[4] / "testing" / "mcp" / "avp_test_mcp.py"


def capture(model: str) -> list[dict]:
    requests: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            requests.append(json.loads(body or b"{}"))
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"avp probe","type":"invalid_request_error"}}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    async def discard(event) -> None:
        pass

    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
        os.environ.update(
            OPENAI_BASE_URL=f"http://127.0.0.1:{server.server_address[1]}/v1",
            OPENAI_API_KEY="probe",
            CODEX_HOME=home,
        )
        os.chdir(cwd)
        commission = Commission.model_validate(
            {
                "schema_version": "0.1",
                "run_id": "capture-tools",
                "model": f"openai/{model}",
                "prompt": "hi",
                "mcp_servers": [
                    {"type": "stdio", "id": "fixture", "command": [sys.executable, str(TEST_MCP)]}
                ],
            }
        )
        asyncio.run(asyncio.wait_for(agent.run(commission, discard), 120))
    server.shutdown()
    return next((r["tools"] for r in requests if r.get("tools")), [])


def main() -> None:
    catalog: dict[str, dict[str, dict]] = {}
    for model in MODELS:
        # Only built-ins: the fixture server's own tools arrive as an MCP namespace.
        sent = {t["name"]: t for t in capture(model) if t.get("name") in cm.BUILTIN_TOOLS}
        missing = sorted(set(cm.BUILTIN_TOOLS) - set(sent) - {"apply_patch"})
        if missing:
            raise SystemExit(f"{model}: Codex sent no definition for {missing}")
        # Function tools carry a JSON Schema; freeform tools (apply_patch)
        # take grammar-constrained text and have none.
        catalog[model] = {
            name: {"description": t.get("description"), "inputSchema": t.get("parameters")}
            for name, t in sorted(sent.items())
        }
    OUT.write_text(json.dumps({"codex": cm.CODEX_VERSION, "models": catalog}, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
