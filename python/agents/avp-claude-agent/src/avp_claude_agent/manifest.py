"""Agent manifest for avp-claude-agent.

The manifest enumerates everything triggerable without supervisor
configuration: SDK preset tools, runtime-bundled subagents, and
runtime-bundled skills. Surfaced in two places that MUST agree:

  - `avp-claude-agent describe` prints `manifest()` as JSON to stdout.
  - The `agent_described` event the translator emits between
    `run_requested` and `agent_started` carries the same payload.

Scope: SDK defaults only. Filesystem-discovered skills (under
`~/.claude/skills/` and `<cwd>/.claude/skills/`) and filesystem
subagents (under `.claude/agents/`) are environment-discovered, not
runtime-bundled — they appear on `agent_started` (the merged-view
event) and `skill_loaded`, not here. Same for MCP server tool lists,
which are handshake-discovered and reported on `mcp_server_connected`.
"""

from __future__ import annotations

from typing import Any

from avp import AgentManifest
from avp_claude_agent.translator import (
    CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS,
    CLAUDE_CODE_PRESET_TOOLS,
)

# What this agent can do that varies between AVP agents. Used by
# Commission-aware tooling to gate features (e.g., "skip this Commission if the
# agent doesn't support subagents-with-frontmatter").
#
# - `mcp`: SDK forwards Commission.mcp_servers and surfaces live tool lists
#   on `mcp_server_connected.avp.mcp.tools[]` after handshake.
# - `subagents`: SDK's Agent tool dispatches Commission.subagents (plus the
#   built-in `general-purpose`) as full nested trajectories.
# - `skills`: SKILL.md descriptors in Commission.skills are surfaced as
#   `skill_loaded` events.
# - `thinking`: extended-thinking blocks parsed and emitted as
#   `reasoning_emitted`.
# - `filesystem-skills`: SDK auto-discovers SKILL.md under
#   `~/.claude/skills/` and project `.claude/skills/`. The manifest
#   itself doesn't enumerate them (env-dependent), but consumers can
#   gate on the capability flag.
# - `filesystem-subagents`: same pattern under `.claude/agents/`.
_CAPABILITIES = (
    "mcp",
    "subagents",
    "skills",
    # The Claude Agent SDK uses progressive disclosure: skill bodies are
    # pulled into context only when the model decides it needs them, not
    # eagerly at startup. The SDK doesn't currently expose a hook for that
    # moment, so the translator does NOT emit `skill_loaded` at startup —
    # the registration view (`agent_started.data.skills[]`) is the audit
    # trail; engagement is opaque for this agent.
    "skills:progressive",
    "thinking",
    "filesystem-skills",
    "filesystem-subagents",
)


def manifest() -> AgentManifest:
    """Build the AgentManifest for this agent build.

    The function is pure (no I/O, no env reads, no filesystem walks) —
    same input always yields the same output for a given installed
    version of `avp-claude-agent`. That's the contract that lets
    `describe` (called pre-flight, no Commission) and `agent_described`
    (emitted at run-time, with Commission) produce identical payloads.

    Built-in tool descriptions are deliberately NOT shipped here. The
    Claude Agent SDK does not expose its tool catalog programmatically;
    the canonical descriptions live in the Claude Code CLI binary and
    Anthropic's docs. Shipping a hardcoded prose table here would drift
    the moment Anthropic ships a new tool or renames an existing one.
    Honest-null beats authored-prose-that-rots — name +
    `avp.dispatch_target` only, consumers cross-reference docs.
    """
    from avp_claude_agent import __version__

    built_in_tools: list[dict[str, Any]] = [
        {"name": name, "avp.dispatch_target": "local"} for name in CLAUDE_CODE_PRESET_TOOLS
    ]
    built_in_subagents: list[dict[str, Any]] = [
        {"name": name, "avp.agent_type": "general-purpose"}
        if name == "general-purpose"
        else {"name": name}
        for name in CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS
    ]

    return AgentManifest.model_validate(
        {
            "agent_name": "avp-claude-agent",
            "agent_version": __version__,
            "avp_spec_version": "0.1",
            # The SDK doesn't compile in a default model — Commission or the
            # SDK's own resolution chain selects. Honest-null.
            "default_model": None,
            # The Claude Agent SDK shells out to the `claude` CLI which only
            # speaks to Anthropic models. Glob covers all current and future
            # Claude variants; supervisors authoring with `model: "gpt-4"` get
            # a clean error_occurred(unsupported_model) at startup instead of
            # an opaque CLI failure on the first turn.
            "supported_models": ["claude-*"],
            "built_in_tools": built_in_tools,
            "built_in_subagents": built_in_subagents or None,
            # SDK does not bundle skills programmatically; SKILL.md files are
            # filesystem-discovered. See translator.py comment for details.
            "built_in_skills": None,
            "capabilities": list(_CAPABILITIES),
        }
    )


__all__ = ["manifest"]
