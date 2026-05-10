"""Agent manifest for avp-anthropic.

The manifest enumerates everything triggerable without supervisor
configuration: SDK preset tools and runtime-bundled subagents/skills.
Surfaced in two places that MUST agree:

  - `avp-anthropic describe` prints `manifest()` as JSON to stdout.
  - The `agent_described` event the agent emits between
    `run_requested` and `agent_started` carries the same payload.

Scope: SDK defaults only. Supervisor-managed assets
(Commission.{mcp_servers,skills,subagents} refs) and environment-discovered
surfaces (filesystem skills, MCP server tool lists) are NOT included here —
they appear on `managed_ref_resolved`, `mcp_server_connected`, etc.
"""

from __future__ import annotations

from typing import Any

from avp import AgentManifest
from avp_anthropic.shell_tools import SHELL_TOOL_SCHEMAS

# What this agent can do that varies between AVP agents. Used by
# Commission-aware tooling to gate features (e.g., "skip this Commission if the
# agent doesn't support thinking blocks").
#
# - `thinking`: Anthropic extended-thinking blocks parsed and emitted
#   as `reasoning_emitted` events.
_CAPABILITIES = ("thinking",)


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
            # The driver speaks to the Anthropic Messages API only — no
            # OpenAI / Gemini / etc. Glob covers all current and future
            # Claude variants; supervisors authoring with a non-Claude model
            # get error_occurred(unsupported_model) at startup before the
            # first API call.
            "supported_models": ["claude-*"],
            "built_in_tools": built_in_tools,
            # No runtime-bundled subagents or skills. The Anthropic driver only
            # surfaces what Commission declares.
            "built_in_subagents": None,
            "built_in_skills": None,
            "capabilities": list(_CAPABILITIES),
        }
    )


__all__ = ["manifest"]
