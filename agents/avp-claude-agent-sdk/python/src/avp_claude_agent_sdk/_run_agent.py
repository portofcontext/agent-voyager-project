"""`run_avp_agent` -- Commission-driven entry point for AVPClaudeSDKClient.

See `_commission.py` for the Commission → ClaudeAgentOptions field-by-field
mapping table.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from claude_agent_sdk.types import ClaudeAgentOptions

from avp.commission import Commission
from avp.sink import EventSink, stdio_sink
from avp_claude_agent_sdk._client import AVPClaudeSDKClient


async def run_avp_agent(
    commission: Commission,
    agent_main: Callable[[AVPClaudeSDKClient], Awaitable[Any]],
    sink: EventSink = stdio_sink,
    options: ClaudeAgentOptions | None = None,
) -> None:
    """Run an AVP-instrumented agent session driven by a Commission.

    Constructs an `AVPClaudeSDKClient` from the Commission (model,
    system_prompt, MCP servers, skills), then calls `agent_main(client)` --
    the caller owns `query()` / `receive_response()`. Guarantees
    `agent_stopped` is emitted in a `finally` block regardless of how
    `agent_main` exits.

    Args:
        commission: Supervisor-provided run configuration.
        agent_main: Async callable that receives the ready client and drives
            the session (calls `query()`, iterates `receive_response()`, etc.).
        sink: AVP event sink. Defaults to stdio (NDJSON to stdout).
        options: Base `ClaudeAgentOptions` the Commission is merged onto.
            Lets callers control SDK-level concerns the Commission doesn't
            speak to (e.g. `setting_sources` / `strict_mcp_config` for an
            isolated, deterministic run).
    """
    async with AVPClaudeSDKClient(options=options, sink=sink, commission=commission) as client:
        await agent_main(client)
