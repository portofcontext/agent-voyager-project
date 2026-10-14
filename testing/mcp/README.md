# Shared MCP test server

`avp_test_mcp.py` is a dependency-free, deterministic stdio MCP fixture shared
across AVP's conformance and adapter tests. It implements initialization, ping,
tool listing, and two tools: `Avptest_Echo` and `Avptest_Add`. It is a small test
fixture, not a general MCP server or an HTTP transport implementation.

```bash
python3 testing/mcp/avp_test_mcp.py
```

Only Python's standard library is needed. There is no package installation,
network access, or persistent state. Stdout contains only JSON-RPC responses.
The conformance harness and Python tests select their own interpreter; Rust
tests use `python3` on PATH or `AVP_TEST_PYTHON` when supplied. Real adapter SDKs
exercise the MCP handshake, discovery, and tool dispatch against this fixture.
