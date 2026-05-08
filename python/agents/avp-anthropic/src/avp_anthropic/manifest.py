"""Agent manifest for avp-anthropic.

The manifest enumerates everything triggerable without supervisor
configuration: SDK preset tools, runtime-bundled subagents, and
runtime-bundled skills. Surfaced in two places that MUST agree:

  - `avp-anthropic describe` prints `manifest()` as JSON to stdout.
  - The `agent_described` event the agent emits between
    `run_requested` and `agent_started` carries the same payload.

Scope: SDK defaults only. Supervisor-declared surfaces (Commission.tools,
Commission.subagents, Commission.skills) and environment-discovered surfaces
(filesystem skills, MCP server tool lists) are NOT included here —
they appear on `agent_started` and `mcp_server_connected` respectively.
"""

from __future__ import annotations

from typing import Any

from avp import AgentManifest
from avp_anthropic.shell_tools import SHELL_TOOL_SCHEMAS

# What this agent can do that varies between AVP agents. Used by
# Commission-aware tooling to gate features (e.g., "skip this Commission if the
# agent doesn't support thinking blocks").
#
# - `mcp`: forwards MCP server descriptors to Anthropic's API connector.
#   HTTP-only; stdio MCP servers in Commission are skipped with a warning.
# - `subagents`: AnthropicSubagentDriver dispatches subagents declared in
#   Commission.subagents.
# - `skills`: SKILL.md descriptors in Commission.skills are surfaced as
#   `skill_loaded` events; injection into prompt context is the
#   supervisor's job.
# - `thinking`: Anthropic extended-thinking blocks parsed and emitted
#   as `reasoning_emitted` events.
_CAPABILITIES = ("mcp", "subagents", "skills", "thinking")


def manifest() -> AgentManifest:
    """Build the AgentManifest for this agent build.

    The function is pure (no I/O, no env reads) — same input always
    yields the same output for a given installed version of
    `avp-anthropic`. That's the contract that lets `describe` (called
    pre-flight, no Commission) and `agent_described` (emitted at run-time,
    with Commission) produce identical payloads.
    """
    from avp_anthropic import __version__

    built_in_tools: list[dict[str, Any]] = []
    for schema in SHELL_TOOL_SCHEMAS:
        entry: dict[str, Any] = {
            "name": schema["name"],
            "avp.dispatch_target": "local",
        }
        if "description" in schema:
            entry["description"] = schema["description"]
        # SHELL_TOOL_SCHEMAS uses snake_case `input_schema` (Anthropic API
        # form); the manifest carries MCP camelCase `inputSchema`.
        if "input_schema" in schema:
            entry["inputSchema"] = schema["input_schema"]
        built_in_tools.append(entry)

    return AgentManifest.model_validate(
        {
            "agent_name": "avp-anthropic",
            "agent_version": __version__,
            "avp_spec_version": "0.1",
            # The Anthropic agent has no compiled-in default model — Commission or
            # `--model` flag selects. Leaving null is honest; downstream
            # auditors won't infer a fake default.
            "default_model": None,
            "built_in_tools": built_in_tools,
            # No runtime-bundled subagents or skills. The Anthropic driver only
            # surfaces what Commission declares.
            "built_in_subagents": None,
            "built_in_skills": None,
            "capabilities": list(_CAPABILITIES),
        }
    )


__all__ = ["manifest"]
