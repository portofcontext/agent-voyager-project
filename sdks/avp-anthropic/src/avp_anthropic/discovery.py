"""Environment discovery for Commission authoring against the avp-anthropic SDK.

The avp-anthropic SDK is a raw API client: no agent loop, no built-in
tools. The only SDK-side surface a Commission author cares about at
authoring time is the set of Anthropic-API hosted server-side tools the
driver knows how to parse (web_search, code_execution,
bash_code_execution). Agents built on top of the SDK contribute their
own tool catalog; pass it in via `agent_built_in_tools` so this helper
returns one Environment a supervisor can render.

What this module CAN'T discover:

  - **MCP-server tool lists.** Tools from a Commission-declared
    `mcp_servers[]` entry are only knowable after the Anthropic API
    runs the MCP handshake at request time.

  - **Filesystem-discovered skills.** The raw Anthropic API has no
    notion of a `~/.claude/skills/` directory. An agent author who
    wires that in is responsible for surfacing it here.
"""

from __future__ import annotations

from dataclasses import dataclass

from avp_anthropic.driver import ANTHROPIC_HOSTED_TOOL_KINDS


@dataclass(frozen=True)
class Environment:
    """Snapshot of what's available at Commission-author time for an
    agent built on the avp-anthropic SDK.

    `anthropic_hosted_tools` are the API-side tool kinds the driver can
    parse from response blocks. `agent_built_in_tools` is whatever the
    wrapping agent supplied; empty by default since the raw SDK ships
    no tools.
    """

    agent_built_in_tools: tuple[str, ...]
    anthropic_hosted_tools: tuple[str, ...]


def discover_environment(
    *,
    agent_built_in_tools: tuple[str, ...] | None = None,
) -> Environment:
    """Return what the avp-anthropic SDK knows about at Commission-author
    time, augmented with the wrapping agent's own tool names.

    Pure constants; no I/O. Symmetric in shape with
    `avp_claude_agent.discover_environment` so a supervisor can write
    one helper that handles both adapters.
    """
    return Environment(
        agent_built_in_tools=tuple(agent_built_in_tools or ()),
        anthropic_hosted_tools=ANTHROPIC_HOSTED_TOOL_KINDS,
    )
