"""Descriptor helper for agents built on the avp-anthropic SDK.

The Anthropic Messages API is a raw HTTP client: no agent loop, no
built-in tools. Agents that wrap this SDK supply their own tool
catalog, subagents, and skills. This helper produces an
`AgentDescriptor` populated with whatever the agent author passes in
plus the constants the SDK does bring (hosted tool kinds the driver
knows how to parse, the `thinking` capability the driver emits as
`reasoning_emitted`).

Use it from your agent's `describe` entry point and from the
`agent_described` event your agent emits between `run_requested` and
`agent_started`. Both surfaces MUST agree per
`spec/v0.1/agent-descriptor.md` so pre-flight introspection matches the
on-wire trajectory.
"""

from __future__ import annotations

from typing import Any

from avp.descriptor import AgentDescriptor
from avp_anthropic.driver import ANTHROPIC_HOSTED_TOOL_KINDS

# Capabilities the avp-anthropic driver brings regardless of which agent
# wraps it. The driver parses extended-thinking blocks and re-emits them
# as `reasoning_emitted`; new driver-level capabilities go here.
_SDK_CAPABILITIES: tuple[str, ...] = ("thinking",)


def build_descriptor(
    *,
    agent_name: str,
    agent_version: str,
    default_model: str | None = None,
    supported_models: list[str] | None = None,
    built_in_tools: list[dict[str, Any]] | None = None,
    built_in_subagents: list[dict[str, Any]] | None = None,
    built_in_skills: list[dict[str, Any]] | None = None,
    capabilities: list[str] | None = None,
    include_hosted_tools: bool = True,
) -> AgentDescriptor:
    """Build an `AgentDescriptor` for an agent that uses the avp-anthropic SDK.

    `agent_name` / `agent_version` identify the AGENT, not the SDK; the
    Anthropic API itself has no agent identity.

    `built_in_tools` is the tool catalog the agent ships (e.g., a
    sandboxed bash + read_file + write_file the agent wires as
    `agent_builtin_tools` when constructing `AVPAgent`). Pass MCP-shaped
    entries (`name`, `description`, `inputSchema`) plus the AVP
    extension `avp.dispatch_target` per
    `spec/v0.1/agent-descriptor.md` §4. Either `inputSchema` (camelCase)
    or `input_schema` (Anthropic API form) is accepted at the boundary.

    `include_hosted_tools` (default True) appends the Anthropic API's
    hosted server-side tools (web_search, code_execution,
    bash_code_execution) the driver can parse. Set False if your agent
    never opts them in.

    `supported_models` defaults to `["claude-*"]` since the driver only
    speaks the Anthropic Messages API.
    """
    tools: list[dict[str, Any]] = []
    if built_in_tools:
        tools.extend(_canonicalize_tools(built_in_tools))
    if include_hosted_tools:
        for hosted_name in ANTHROPIC_HOSTED_TOOL_KINDS:
            tools.append({"name": hosted_name, "avp.dispatch_target": "local"})

    caps = list(_SDK_CAPABILITIES)
    if capabilities:
        for cap in capabilities:
            if cap not in caps:
                caps.append(cap)

    return AgentDescriptor.model_validate(
        {
            "agent_name": agent_name,
            "agent_version": agent_version,
            "avp_spec_version": "0.1",
            "default_model": default_model,
            "supported_models": supported_models or ["claude-*"],
            "built_in_tools": tools or None,
            "built_in_subagents": built_in_subagents,
            "built_in_skills": built_in_skills,
            "capabilities": caps,
        }
    )


def _canonicalize_tools(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize tool entries to MCP camelCase (`inputSchema`) for the
    Descriptor's wire shape. Accept either spelling at the boundary."""
    out: list[dict[str, Any]] = []
    for raw in entries:
        entry: dict[str, Any] = {"name": raw["name"]}
        if "description" in raw:
            entry["description"] = raw["description"]
        if "inputSchema" in raw:
            entry["inputSchema"] = raw["inputSchema"]
        elif "input_schema" in raw:
            entry["inputSchema"] = raw["input_schema"]
        entry["avp.dispatch_target"] = raw.get("avp.dispatch_target", "local")
        for k, v in raw.items():
            if k not in (
                "name",
                "description",
                "inputSchema",
                "input_schema",
                "avp.dispatch_target",
            ):
                entry[k] = v
        out.append(entry)
    return out


__all__ = ["build_descriptor"]
