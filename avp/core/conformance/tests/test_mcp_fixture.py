"""The MCP fixture boots with no site-packages, cache, or pre-existing home."""

import json
import subprocess
import sys
from pathlib import Path

from avp.launch import local_environment

FIXTURE = Path(__file__).resolve().parents[4] / "testing/mcp/avp_test_mcp.py"


def test_cold_stdio_fixture_needs_only_stdlib():
    messages = [
        {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"method": "notifications/initialized"},
        {"id": 2, "method": "tools/list"},
        {
            "id": 3,
            "method": "tools/call",
            "params": {"name": "Avptest_Echo", "arguments": {"text": "hello\n世界"}},
        },
        {
            "id": 4,
            "method": "tools/call",
            "params": {"name": "Avptest_Add", "arguments": {"a": 2, "b": 3}},
        },
        {
            "id": 5,
            "method": "tools/call",
            "params": {"name": "Avptest_Add", "arguments": {"a": True, "b": 3}},
        },
        {"id": 6, "method": "missing"},
        {"id": 7, "method": "ping"},
        {
            "id": 8,
            "method": "tools/call",
            "params": {"name": "Avptest_Fail", "arguments": {"message": "boom", "mode": "result"}},
        },
        {
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "Avptest_Fail",
                "arguments": {"message": "boom", "mode": "protocol"},
            },
        },
    ]
    with local_environment({}) as env:
        result = subprocess.run(
            [sys.executable, "-S", str(FIXTURE)],
            input="\n".join(json.dumps({"jsonrpc": "2.0", **m}) for m in messages) + "\n",
            env=env,
            cwd=env["AVP_WORKSPACE"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert [r["id"] for r in replies] == list(range(1, 10))
    assert replies[0]["result"]["protocolVersion"] == "2025-11-25"
    assert {t["name"] for t in replies[1]["result"]["tools"]} == {
        "Avptest_Echo",
        "Avptest_Add",
        "Avptest_Fail",
    }
    assert replies[2]["result"]["content"] == [{"type": "text", "text": "hello\n世界"}]
    assert replies[3]["result"]["content"] == [{"type": "text", "text": "sum: 5"}]
    assert replies[4]["error"]["code"] == -32602
    assert replies[5]["error"]["code"] == -32601
    assert replies[6]["result"] == {}
    assert replies[7]["result"] == {"content": [{"type": "text", "text": "boom"}], "isError": True}
    assert replies[8]["error"] == {"code": -32000, "message": "boom"}
    assert result.stderr == ""
