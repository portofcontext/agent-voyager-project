"""Capture the pinned Claude Code profile against a local model endpoint."""

import asyncio
import http.server
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, SystemMessage

OUT = Path(__file__).resolve().parents[1] / "src/avp_claude_agent_sdk/catalog.json"
CLI = os.environ.get("AVP_CLAUDE_CLI", "claude")
VERSION = "2.1.303"


async def capture():
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if data.get("tools"):
                requests.append(data)
            body = b'{"type":"error","error":{"type":"invalid_request_error","message":"AVP catalog capture"}}'
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as home:
            options = ClaudeAgentOptions(
                cli_path=CLI,
                cwd=workspace,
                model="claude-haiku-4-5",
                setting_sources=[],
                strict_mcp_config=True,
                permission_mode="bypassPermissions",
                env={
                    "ANTHROPIC_API_KEY": "avp-capture",
                    "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    "CLAUDE_CONFIG_DIR": home,
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "DISABLE_AUTOUPDATER": "1",
                    "CLAUDE_CODE_USE_BEDROCK": "0",
                    "CLAUDE_CODE_USE_VERTEX": "0",
                    "CLAUDE_CODE_USE_FOUNDRY": "0",
                },
            )
            init = None
            async with ClaudeSDKClient(options) as client:
                info = await client.get_server_info()
                assert info is not None
                await client.query("Reply hi")
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        init = message.data
            assert init is not None and requests
            assert info is not None
            commands = {c["name"]: c for c in info["commands"] if c.get("builtin")}
            return {
                "claude": VERSION,
                "tools": [
                    {
                        "name": t["name"],
                        "description": t.get("description"),
                        "inputSchema": t.get("input_schema", {"type": "object"}),
                    }
                    for t in requests[0]["tools"]
                ],
                "skills": [
                    {"name": name, "description": commands[name]["description"]}
                    for name in init.get("skills", [])
                ],
                "subagents": [{"name": name} for name in init.get("agents", [])],
            }
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__ == "__main__":
    assert subprocess.check_output([CLI, "--version"], text=True).split()[0] == VERSION
    OUT.write_text(json.dumps(asyncio.run(asyncio.wait_for(capture(), 45)), indent=2) + "\n")
    print(f"wrote {OUT}")
