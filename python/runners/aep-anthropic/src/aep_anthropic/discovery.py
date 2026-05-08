"""Environment discovery for Config authoring (Anthropic runner).

Symmetric with `aep_claude_agent.discovery.discover_environment` but
narrower: the aep-anthropic runner drives the Anthropic Messages API
directly; there's no Claude Code CLI subprocess and no filesystem
discovery layer (no `~/.claude/skills/`, no `.claude/agents/`). The
runtime-knowable surface for a Config author is just the runner's own
shell built-ins and the Anthropic-API hosted tools the runner knows
how to parse.

What this module CAN'T discover:

  - **MCP-server tool lists.** Same caveat as the CASDK runner: tools
    from a Config-declared `mcp_servers[]` entry are only knowable
    after the Anthropic API runs the MCP handshake at request time.

  - **Anthropic-side custom tools the user opts in to.** The user
    passes their own `tools=[...]` to `messages.create()`; we don't
    know about those at Config-author time.
"""

from __future__ import annotations

from dataclasses import dataclass

from aep_anthropic.driver import ANTHROPIC_HOSTED_TOOL_KINDS
from aep_anthropic.shell_tools import SHELL_TOOL_NAMES


@dataclass(frozen=True)
class Environment:
    """Snapshot of what's available at Config-author time for the
    aep-anthropic runner.

    `shell_tools` are the runner's own in-process tools (bash,
    read_file, write_file). `anthropic_hosted_tools` are the API-side
    tool kinds the runner can parse from response blocks.
    """

    shell_tools: tuple[str, ...]
    anthropic_hosted_tools: tuple[str, ...]


def discover_environment() -> Environment:
    """Return what the aep-anthropic runner knows about at Config-author
    time.

    No arguments because there's no filesystem walk involved — the
    surface is purely the runner's compiled-in constants. Symmetric API
    shape with `aep_claude_agent.discover_environment` so a supervisor
    can write one helper that handles both runners.
    """
    return Environment(
        shell_tools=SHELL_TOOL_NAMES,
        anthropic_hosted_tools=ANTHROPIC_HOSTED_TOOL_KINDS,
    )
