"""`run_avp_agent` -- Commission-driven entry point for AVPClaudeSDKClient.

See `_commission.py` for the Commission → ClaudeAgentOptions field-by-field
mapping table.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from avp.agent.sink import EventSink, stdio_sink
from avp.commission import Commission
from avp_claude_agent_sdk._client import AVPClaudeSDKClient


async def run_avp_agent(
    commission: Commission,
    agent_main: Callable[[AVPClaudeSDKClient], Awaitable[Any]],
    sink: EventSink = stdio_sink,
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
    """
    options = _commission_to_options(commission)
    async with AVPClaudeSDKClient(options=options, sink=sink) as client:
        await agent_main(client)


# def _commission_to_options(commission: Commission):  # type: ignore[return]
#     """Translate Commission fields to ClaudeAgentOptions.

#     See the module docstring for the full field-by-field mapping. Inline
#     `mcp_servers` and `skills` are mapped directly (no resolver). Fields
#     without a clean SDK equivalent (`enabled_builtin_mcp_servers`,
#     `enabled_builtin_subagents`) are left as TODOs.
#     """
#     from claude_agent_sdk.types import ClaudeAgentOptions

#     output_format: dict[str, Any] | None = None
#     if commission.output_schema is not None:
#         output_format = {"type": "json_schema", "schema": commission.output_schema}

#     # TODO: enabled_builtin_mcp_servers -- no clean SDK knob; defer.
#     # TODO: enabled_builtin_subagents -- no SDK allowlist knob; defer.
#     # TODO: Skill.files inline content -- write to temp dir + add via add_dirs.

#     skills = _map_skills(commission)
#     return ClaudeAgentOptions(
#         model=commission.model,
#         system_prompt=commission.system_prompt,
#         tools=commission.enabled_builtin_tools,
#         mcp_servers=_map_mcp_servers(commission),
#         skills=skills or None,
#         output_format=output_format,
#     )
