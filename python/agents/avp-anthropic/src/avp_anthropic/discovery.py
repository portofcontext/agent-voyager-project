"""Environment discovery for Commission authoring (Anthropic agent).

Symmetric with `avp_claude_agent.discovery.discover_environment` but
narrower: the avp-anthropic agent drives the Anthropic Messages API
directly; there's no Claude Code CLI subprocess and no filesystem
discovery layer (no `~/.claude/skills/`, no `.claude/agents/`). The
runtime-knowable surface for a Commission author is just the agent's own
shell built-ins and the Anthropic-API hosted tools the agent knows
how to parse.

What this module CAN'T discover:

  - **MCP-server tool lists.** Same caveat as the CASDK agent: tools
    from a Commission-declared `mcp_servers[]` entry are only knowable
    after the Anthropic API runs the MCP handshake at request time.

  - **Anthropic-side custom tools the user opts in to.** The user
    passes their own `tools=[...]` to `messages.create()`; we don't
    know about those at Commission-author time.
"""

from __future__ import annotations

from dataclasses import dataclass

from avp_anthropic.driver import ANTHROPIC_HOSTED_TOOL_KINDS
from avp_anthropic.shell_tools import SHELL_TOOL_NAMES


@dataclass(frozen=True)
class Environment:
    """Snapshot of what's available at Commission-author time for the
    avp-anthropic agent.

    `shell_tools` are the agent's own in-process tools (bash,
    read_file, write_file). `anthropic_hosted_tools` are the API-side
    tool kinds the agent can parse from response blocks.
    """

    shell_tools: tuple[str, ...]
    anthropic_hosted_tools: tuple[str, ...]


def discover_environment() -> Environment:
    """Return what the avp-anthropic agent knows about at Commission-author
    time.

    No arguments because there's no filesystem walk involved — the
    surface is purely the agent's compiled-in constants. Symmetric API
    shape with `avp_claude_agent.discover_environment` so a supervisor
    can write one helper that handles both agents.
    """
    return Environment(
        shell_tools=SHELL_TOOL_NAMES,
        anthropic_hosted_tools=ANTHROPIC_HOSTED_TOOL_KINDS,
    )
