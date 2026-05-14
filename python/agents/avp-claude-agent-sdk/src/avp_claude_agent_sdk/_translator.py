"""Translators from claude-agent-sdk types to AVP wire-shape models."""

from importlib.metadata import version as _pkg_version
from pathlib import Path

from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    SystemPromptFile,
    SystemPromptPreset,
)

from avp.descriptor import (
    AgentDescriptor,
    McpServerDecl,
    SkillDecl,
    SubagentDecl,
    ToolDecl,
)

_AGENT_NAME = "avp-claude-agent-sdk"


def descriptor_from_options(
    prompt: str | None,
    options: ClaudeAgentOptions,
) -> AgentDescriptor:
    """Build an AgentDescriptor reflecting a `query()` invocation surface.

    For the library-invocation path there's no Commission, so the descriptor
    is the only wire view of what's triggerable: identity, the literal
    system / user prompts, and the declared tools / MCP servers / subagents
    / skills carried on the options.
    """
    return AgentDescriptor(
        agent_name=_AGENT_NAME,
        agent_version=_pkg_version(_AGENT_NAME),
        avp_spec_version="0.1",
        default_model=options.model,
        system_prompt=_resolve_system_prompt(options.system_prompt),
        prompt=prompt,
        tools=_tools(options),
        mcp_servers=_mcp_servers(options),
        subagents=_subagents(options),
        skills=_skills(options),
    )


def _resolve_system_prompt(
    system_prompt: str | SystemPromptPreset | SystemPromptFile | None,
) -> str | None:
    """Resolve a SystemPrompt option to the literal text the model will see.

    `str` is verbatim, `SystemPromptFile` is best-effort read from disk
    (None on OSError), `SystemPromptPreset` returns None (the preset name
    isn't the literal prompt).
    """
    if system_prompt is None or isinstance(system_prompt, str):
        return system_prompt
    if system_prompt["type"] == "file":
        try:
            return Path(system_prompt["path"]).read_text()
        except OSError:
            return None
    return None


def _tools(options: ClaudeAgentOptions) -> list[ToolDecl] | None:
    """Project explicit tool names. `ToolsPreset` defers to CLI discovery."""
    tools = options.tools
    if not isinstance(tools, list) or not tools:
        return None
    return [ToolDecl(name=name) for name in tools]


def _mcp_servers(options: ClaudeAgentOptions) -> list[McpServerDecl] | None:
    """Project dict-form `mcp_servers` to identity-only descriptor entries.

    Path/str forms reference an external CLI config file; not read here.
    """
    servers = options.mcp_servers
    if not isinstance(servers, dict) or not servers:
        return None
    return [McpServerDecl(id=server_id) for server_id in servers]


def _subagents(options: ClaudeAgentOptions) -> list[SubagentDecl] | None:
    """Project `options.agents` (`AgentDefinition` per name) to SubagentDecl."""
    agents = options.agents
    if not agents:
        return None
    return [
        SubagentDecl(name=name, description=defn["description"]) for name, defn in agents.items()
    ]


def _skills(options: ClaudeAgentOptions) -> list[SkillDecl] | None:
    """Project the explicit-list form of `options.skills`. `"all"` is left
    to runtime CLI discovery and isn't enumerable up-front."""
    skills = options.skills
    if not isinstance(skills, list) or not skills:
        return None
    return [SkillDecl(name=name) for name in skills]
