# Shared MCP test server

`avp_test_mcp.py` is a tiny, deterministic stdio [MCP](https://modelcontextprotocol.io)
server for the repo's test suites. It is the stable, self-contained fixture any
AVP agent or SDK can point an `mcp_server` at to exercise the real MCP connect
and dispatch path, instead of depending on a server that only exists on one
machine.

It is built on [`arcade-mcp-server`](https://pypi.org/project/arcade-mcp-server/)
(`MCPApp` + `@app.tool`) The
dependency is declared inline (PEP 723), so `uv run` bootstraps it into an
ephemeral environment; nothing to install first.

## Running it

```bash
uv run testing/mcp/avp_test_mcp.py          # stdio (default; how tests spawn it)
uv run testing/mcp/avp_test_mcp.py http     # HTTP streaming
```

Requires `uv` on PATH. Logs go to stderr; stdout is reserved for JSON-RPC.
