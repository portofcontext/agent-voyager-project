"""Translators from claude-agent-sdk types to AVP wire-shape models.

Two distinct views fall out of the SDK:

- The **static descriptor** is what the agent can state about itself
  pre-flight: identity, package version, AVP spec version, default model.
  It's the payload of `agent_described`.
- The **runtime-merged view** comes from the first
  `SystemMessage(subtype="init")` the SDK emits. It carries the actual
  tool catalog (CLI built-ins + MCP-namespaced names), live subagent /
  skill lists, and the resolved model. Combined with `get_mcp_status()`,
  it populates `agent_started`.

Per AVP v0.1: `agent_started.data["avp.tools"]` is the single bag of
usable tools (local + MCP-surfaced from connected servers); MCP-surfaced
entries carry `avp.mcp_server_id`. `agent_started.data["avp.mcp_servers"]`
records every attempted dial with its terminal `status` —
`connected` / `failed` / `needs-auth` / `pending` / `disabled`.

The init message is the authoritative source for the run's tool surface:
CLI built-ins are never reported by `get_mcp_status()`, and even when
MCP servers are non-`connected`, the init message reliably enumerates
the tools each server contributes when it IS connected.
"""

import re
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import (
    ContentBlock,
    ServerToolResultBlock,
    ServerToolUseBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    McpStatusResponse,
    SystemPromptFile,
    SystemPromptPreset,
)

from avp.content import AVPContentBlock
from avp.content import ServerToolResultBlock as AVPServerToolResultBlock
from avp.content import ServerToolUseBlock as AVPServerToolUseBlock
from avp.content import TextBlock as AVPTextBlock
from avp.content import ThinkingBlock as AVPThinkingBlock
from avp.content import ToolUseBlock as AVPToolUseBlock
from avp.descriptor import (
    AgentDescriptor,
    McpServerDecl,
    SkillDecl,
    SubagentDecl,
    ToolDecl,
)
from avp.trajectory import Usage

_AGENT_NAME = "avp-claude-agent-sdk"


# ---------------------------------------------------------------------------
# SDK → AVP translation helpers
# ---------------------------------------------------------------------------


def translate_content_blocks(blocks: list[ContentBlock]) -> list[AVPContentBlock]:
    """SDK content blocks → AVP content blocks. Drops unknown subtypes
    silently (honest-silent beats fabricated). `ToolResultBlock` is not
    translated here -- it surfaces as a `tool_returned` event, not as
    inline content.

    `ServerToolResultBlock` doesn't carry `name` (only its paired
    `ServerToolUseBlock` does); a single in-order pass tracks the most
    recent server-tool name per `tool_use_id` and back-fills it.
    """
    out: list[AVPContentBlock] = []
    server_tool_names: dict[str, str] = {}
    for block in blocks or []:
        if isinstance(block, TextBlock):
            out.append(AVPTextBlock(text=block.text))
        elif isinstance(block, ThinkingBlock):
            out.append(AVPThinkingBlock(thinking=block.thinking, signature=block.signature))
        elif isinstance(block, ToolUseBlock):
            out.append(AVPToolUseBlock(id=block.id, name=block.name, input=block.input))
        elif isinstance(block, ServerToolUseBlock):
            server_tool_names[block.id] = block.name
            out.append(AVPServerToolUseBlock(id=block.id, name=block.name, input=block.input))
        elif isinstance(block, ServerToolResultBlock):
            out.append(
                AVPServerToolResultBlock(
                    tool_use_id=block.tool_use_id,
                    name=server_tool_names.get(block.tool_use_id, ""),
                    content=block.content,
                )
            )
    return out


def translate_usage(usage: dict[str, Any]) -> Usage:
    """Project the SDK's `AssistantMessage.usage` dict onto AVP `Usage`.

    The SDK reports the API call's response totals (duplicated on every
    chunk of one `message_id`), so overwriting on each chunk converges
    to the inference's true totals by the time the turn drains.
    """
    return Usage(
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_input_tokens=int(usage.get("cache_read_input_tokens") or 0) or None,
        cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens") or 0) or None,
    )


def get_dispatch_target(tool_name: str) -> Literal["mcp_server", "local"]:
    """Wire discriminator for `tool_invoked`. The Claude Agent SDK
    namespaces MCP tools as `mcp__<server>__<tool>`; everything else is
    a CLI built-in, server tool, or local hook."""
    return "mcp_server" if tool_name.startswith("mcp__") else "local"


def translate_agent_descriptor(
    options: ClaudeAgentOptions,
    init_data: dict[str, Any] | None,
    status: McpStatusResponse,
    *,
    prompt: str | None = None,
) -> AgentDescriptor:
    """Build the full pre-Commission descriptor for `agent_described`.

    `init_data` comes from a probe-session `SystemMessage(subtype="init")`;
    `status` from the probe's `get_mcp_status()`. When `init_data` is
    `None` (probe unavailable / failed), `tools` / `subagents` / `skills`
    are absent and the descriptor still validates -- the prelude stays
    spec-conformant.

    `prompt` is the autonomous-style prompt passed to `connect()` when the
    agent is driven that way; for interactive `query()`-driven runs it
    stays `None`. `system_prompt` is resolved from `options.system_prompt`
    (literal string, file, or preset).
    """
    return AgentDescriptor(
        agent_name=_AGENT_NAME,
        agent_version=_pkg_version(_AGENT_NAME),
        spec_version="0.1",
        default_model=(request_model_from_init(init_data, options) if init_data else options.model),
        system_prompt=resolve_system_prompt(options.system_prompt),
        prompt=prompt,
        tools=tools_from_init(init_data, status) if init_data else None,
        subagents=subagents_from_init(init_data) if init_data else None,
        skills=skills_from_init(init_data) if init_data else None,
        mcp_servers=mcp_servers_from_status(status),
    )


# ---------------------------------------------------------------------------
# Runtime-merged view (emitted on init SystemMessage)
# ---------------------------------------------------------------------------


def _normalize_mcp_prefix(server_name: str) -> str:
    """Mirror the SDK's tool-naming sanitizer: in `mcp__<prefix>__<tool>`,
    `<prefix>` is the server's display name with every non-alphanumeric
    char (dots, spaces, hyphens, ...) replaced by `_`. Used to map a
    sanitized prefix back to its original `McpServerDecl.id`."""
    return re.sub(r"[^A-Za-z0-9_]", "_", server_name)


def tools_from_init(init_data: dict[str, Any], status: McpStatusResponse) -> list[ToolDecl] | None:
    """Full tool catalog from the `init` SystemMessage.

    `init.tools` is a flat list of names that includes both CLI
    built-ins (`Task`, `Bash`, `Edit`, ...) and MCP-namespaced handles
    (`mcp__<sanitized-server>__<tool>`, where the SDK sanitizes the
    server's display name via `_normalize_mcp_prefix`). Per AVP v0.1 §4:
    all tools land in one bag; MCP-surfaced entries carry
    `avp.mcp_server_id` pointing at the un-sanitized `McpServerDecl.id`
    in `mcp_servers[]`. Lookups go through a sanitized-prefix → id map
    built from `status.mcpServers`.
    """
    names = init_data.get("tools") or []
    prefix_to_id = {
        _normalize_mcp_prefix(s["name"]): s["name"] for s in status.get("mcpServers", [])
    }
    decls: list[ToolDecl] = []
    for name in names:
        if name.startswith("mcp__"):
            parts = name.split("__", 2)
            prefix = parts[1] if len(parts) >= 3 else None
            server_id = prefix_to_id.get(prefix) if prefix else None
            decls.append(ToolDecl.model_validate({"name": name, "avp.mcp_server_id": server_id}))
        else:
            decls.append(ToolDecl(name=name))
    return decls or None


def subagents_from_init(init_data: dict[str, Any]) -> list[SubagentDecl] | None:
    """Subagent names from `init.agents`. SDK reports names only, no
    descriptions; `SubagentDecl.description` stays None."""
    names = init_data.get("agents") or []
    return [SubagentDecl(name=n) for n in names] or None


def skills_from_init(init_data: dict[str, Any]) -> list[SkillDecl] | None:
    """Skill names from `init.skills`."""
    names = init_data.get("skills") or []
    return [SkillDecl(name=n) for n in names] or None


def request_model_from_init(init_data: dict[str, Any], options: ClaudeAgentOptions) -> str | None:
    """Resolved model the run will actually use. `init.model` is the
    server-side resolved value (e.g. `claude-opus-4-7[1m]`); fall back
    to `options.model` if absent."""
    return init_data.get("model") or options.model


def mcp_servers_from_status(status: McpStatusResponse) -> list[McpServerDecl] | None:
    """One `McpServerDecl` per server in the SDK's status, regardless of
    state.

    Per AVP v0.1 §2.1: `agent_started.data["avp.mcp_servers"]` records
    every attempted dial with its terminal `status` — only `"connected"`
    servers contribute tools to `tools[]`, but `"failed"` / `"needs-auth"`
    / `"pending"` / `"disabled"` servers stay on the wire so consumers
    see what was attempted and how it ended.

    `id` is the server's display name (the dict key the user authored,
    which also matches the SDK's `mcp__<id>__<tool>` namespacing) so
    tools cross-reference back to their server's `id`.
    """
    # from rich import print

    # print("MCP STATUS")
    # print(status)
    decls: list[McpServerDecl] = []
    for server in status.get("mcpServers", []):
        decls.append(McpServerDecl(id=server["name"], status=server.get("status")))
    return decls or None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def resolve_system_prompt(
    system_prompt: str | SystemPromptPreset | SystemPromptFile | None,
) -> str | None:
    """Resolve a SystemPrompt option to the literal text the model sees.

    `str` is verbatim; `SystemPromptFile` is best-effort read from disk
    (None on OSError); `SystemPromptPreset` returns None (the preset
    name isn't the literal prompt).
    """
    if system_prompt is None or isinstance(system_prompt, str):
        return system_prompt
    if system_prompt["type"] == "file":
        try:
            return Path(system_prompt["path"]).read_text()
        except OSError:
            return None
    return None
