#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["arcade-mcp-server>=1.17,<2"]
# ///
"""Tiny deterministic MCP server shared across the AVP test suites.

A stable, self-contained stdio MCP server any agent or SDK can spawn to exercise
the real MCP connection and dispatch path, replacing the machine-specific
`gtmagent` one-off. Lives at the repo root (`testing/mcp/`) so every package can
reach it. Built on `arcade-mcp-server` (`MCPApp` + `@app.tool`), the same
framework our teammates' example servers use and have verified works with Goose.
The dependency is declared inline (PEP 723), so `uv run` bootstraps it into an
ephemeral environment; the server runs anywhere `uv` does with no project
install. See `README.md` alongside this file.

    uv run testing/mcp/avp_test_mcp.py          # stdio (default; how tests spawn it)
    uv run testing/mcp/avp_test_mcp.py http     # HTTP streaming

Tools are intentionally trivial and pure so assertions are deterministic.
"""

import sys
from os import getenv
from typing import Annotated, Literal, cast

from arcade_mcp_server import MCPApp

app = MCPApp(name="avptest", version="0.1.0", log_level="WARNING")


@app.tool
def echo(text: Annotated[str, "The text to echo back verbatim"]) -> str:
    """Return the given text unchanged. Deterministic; used to assert an MCP round-trip."""
    return text


@app.tool
def add(
    a: Annotated[int, "First addend"],
    b: Annotated[int, "Second addend"],
) -> int:
    """Return the sum a + b. A second tool so the served descriptor carries more than one."""
    return a + b


def main() -> None:
    transport = cast(
        Literal["stdio", "http"],
        sys.argv[1] if len(sys.argv) > 1 else getenv("AVP_TEST_MCP_TRANSPORT", "stdio"),
    )
    app.run(transport=transport)


if __name__ == "__main__":
    main()
