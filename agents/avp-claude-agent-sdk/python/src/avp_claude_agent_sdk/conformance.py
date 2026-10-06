"""Agent entrypoint for avp-claude-agent-sdk (`ping` / `describe` / `run`).

The command line is the binding's stock `avp.agent_cli`; this module supplies
the two agent-specific pieces. Heavy imports stay inside them so `ping` never
loads the Claude Agent SDK.
"""

from __future__ import annotations

import os

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.sink import EventSink


def describe() -> AgentDescriptor:
    """The pre-flight AgentDescriptor (no model turn). Boots a transient probe
    session to discover the live tool / skill / MCP surface; on any probe
    failure it degrades to identity + default_model and still validates."""
    import asyncio

    from claude_agent_sdk.types import ClaudeAgentOptions

    from avp_claude_agent_sdk._client import _probe_describe
    from avp_claude_agent_sdk._translator import translate_agent_descriptor

    options = ClaudeAgentOptions(setting_sources=[], strict_mcp_config=True)
    init_data, status = asyncio.run(_probe_describe(options))
    return translate_agent_descriptor(options, init_data, status)


async def run(commission: Commission, sink: EventSink) -> None:
    """Run the Claude Agent SDK against the Commission."""
    from claude_agent_sdk.types import ClaudeAgentOptions

    from avp_claude_agent_sdk import AVPClaudeSDKClient, run_avp_agent

    # Isolate the run for determinism: don't inherit the host's settings or
    # filesystem MCP config, so the tool surface is governed only by the
    # Commission (not the operator's ~/.claude). Run in the supervisor-provided
    # workspace when set. `bypassPermissions` is required headless: in the
    # default mode Edit/Bash hit a permission prompt with no approver. AVP owns
    # confinement (the sandbox), so auto-executing tools here is the right posture.
    options = ClaudeAgentOptions(
        setting_sources=[],
        strict_mcp_config=True,
        cwd=os.environ.get("AVP_WORKSPACE"),
        permission_mode="bypassPermissions",
    )

    async def agent_main(client: AVPClaudeSDKClient) -> None:
        # The prompt flows from the Commission via `apply_prompt`; the literal
        # passed here is only a fallback when the Commission omits a prompt.
        await client.query("")
        async for _ in client.receive_response():
            pass

    await run_avp_agent(commission, agent_main, sink=sink, options=options)


def main(argv: list[str] | None = None) -> int:
    from avp.agent_cli import main as agent_main

    return agent_main(
        run=run, describe=describe, prog="avp-claude-agent-sdk-conformance", argv=argv
    )


if __name__ == "__main__":
    raise SystemExit(main())
