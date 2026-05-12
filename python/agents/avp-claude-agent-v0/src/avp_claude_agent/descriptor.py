"""Agent Descriptor for avp-claude-agent.

The Descriptor enumerates everything triggerable without supervisor
configuration: SDK preset tools, runtime-bundled subagents, and
runtime-bundled skills. Surfaced in two places that MUST agree:

  - `avp-claude-agent describe` prints `descriptor()` as JSON to stdout.
  - The `agent_described` event the translator emits between
    `run_requested` and `agent_started` carries the same payload.

Scope: SDK defaults only. Filesystem-discovered skills (under
`~/.claude/skills/` and `<cwd>/.claude/skills/`) and filesystem
subagents (under `.claude/agents/`) are environment-discovered, not
runtime-bundled: they appear on `agent_started` (the merged-view
event) and `skill_loaded`, not here. Same for MCP server tool lists,
which are handshake-discovered and reported on `mcp_server_connected`.
"""

from __future__ import annotations

from typing import Any

from avp import AgentDescriptor
from avp_claude_agent.translator import (
    CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS,
    CLAUDE_CODE_PRESET_TOOLS,
)

# What this agent can do that varies between AVP agents. Used by
# Commission-aware tooling to gate features.
#
# - `skills:progressive`: skill bodies inject lazily on the SDK's own
#   schedule, not eagerly at startup. The translator does not emit
#   `skill_loaded` for SDK-managed skills.
# - `thinking`: extended-thinking blocks parsed and emitted as
#   `reasoning_emitted`.
# - `filesystem-discovery-available`: the Claude Agent SDK *can* load
#   skills / subagents from `~/.claude/skills/` and `.claude/agents/`
#   per its own `setting_sources` default. The translator does not
#   override that default — overriding it cascades into the SDK's
#   tool-definition loading and `permission_mode` resolution in ways
#   that aren't ours to redesign. Supervisors who want strict
#   no-discovery configure the SDK directly via
#   `extra_sdk_options={"setting_sources": [], ...}` alongside a
#   compatible `permission_mode`. This capability is an informational
#   disclosure so consumers know discovery is part of the runtime
#   surface unless the supervisor disables it.
_CAPABILITIES = (
    "skills:progressive",
    "thinking",
    "filesystem-discovery-available",
)


def descriptor() -> AgentDescriptor:
    """Build the AgentDescriptor for this agent build.

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

    return AgentDescriptor.model_validate(
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


__all__ = ["descriptor"]
