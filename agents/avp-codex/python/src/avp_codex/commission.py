"""Commission mapping for the pinned, noninteractive Codex profile."""

from __future__ import annotations

import json

from avp.commission import Commission, McpServerStdio
from avp.preflight import preflight
from avp.trajectory import ErrorCode

AGENT_NAME = "avp-codex"
CODEX_VERSION = "0.162.1"
# Available native surface for the pinned runtime. Model metadata determines
# whether apply_patch is exposed; shell execution uses the unified exec pair.
BUILTIN_TOOLS = [
    "exec_command",
    "write_stdin",
    "apply_patch",
    "view_image",
    "request_user_input",
    "list_mcp_resources",
    "list_mcp_resource_templates",
    "read_mcp_resource",
]

SHELL_TOOLS = {"exec_command", "write_stdin"}
ENVIRONMENT_TOOLS = SHELL_TOOLS | {"apply_patch", "view_image"}
RESOURCE_TOOLS = {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"}


def selected_tools(cm: Commission) -> list[str]:
    allow = (cm.enabled_builtin_tools or {}).get(AGENT_NAME)
    return [name for name in BUILTIN_TOOLS if allow is None or name in allow]


def uses_environment(cm: Commission) -> bool:
    return bool(set(selected_tools(cm)) & ENVIRONMENT_TOOLS)


def fail_fast(cm: Commission, version: str):
    if failure := preflight(
        cm,
        agent_name=AGENT_NAME,
        agent_version=version,
        tools=BUILTIN_TOOLS,
        skills=[],
        subagents=[],
        mcp_servers=[],
    ):
        return failure
    if cm.model.split("/", 1)[0] != "openai":
        return ErrorCode.unsupported_model, "Codex profile requires an openai/model slug"
    if cm.provider and cm.provider.id != "openai":
        return (
            ErrorCode.unsupported_provider,
            "Codex profile requires the OpenAI Responses protocol",
        )
    allowed = set(selected_tools(cm))
    filtered = (cm.enabled_builtin_tools or {}).get(AGENT_NAME) is not None
    if filtered and cm.model not in {"openai/gpt-5-mini", "openai/gpt-5.5"}:
        return (
            ErrorCode.commission_collision,
            "Codex tool filtering is verified only for openai/gpt-5-mini and openai/gpt-5.5; "
            "other model catalogs can add tools without independent disable switches",
        )
    if filtered and cm.model == "openai/gpt-5.5" and cm.mcp_servers:
        return (
            ErrorCode.commission_collision,
            "Codex gpt-5.5 adds native tool search for MCP servers; "
            "filtered MCP runs currently require openai/gpt-5-mini",
        )
    if allowed & SHELL_TOOLS and not allowed >= SHELL_TOOLS:
        return (
            ErrorCode.commission_collision,
            "Codex requires exec_command and write_stdin together",
        )
    if (
        allowed & ENVIRONMENT_TOOLS
        and "apply_patch" not in allowed
        and cm.model != "openai/gpt-5-mini"
    ):
        return (
            ErrorCode.commission_collision,
            "Codex environment tools require allowing model-dependent apply_patch; "
            "omit all environment tools to disable environment access",
        )
    if cm.mcp_servers and not allowed >= RESOURCE_TOOLS:
        return (
            ErrorCode.commission_collision,
            "Codex exposes list_mcp_resources, list_mcp_resource_templates, and read_mcp_resource "
            "when Commission MCP servers are configured; include all three in the allow-list",
        )
    return None


def config(cm: Commission) -> dict:
    allowed = set(selected_tools(cm))
    servers = {}
    for entry in cm.mcp_servers or []:
        server = {"default_tools_approval_mode": "approve"}
        if isinstance(entry, McpServerStdio):
            server.update(
                command=entry.command[0],
                args=entry.command[1:] + (entry.args or []),
                env=entry.env or {},
            )
        else:
            server.update(url=entry.url, http_headers=entry.headers or {})
        servers[entry.id] = server
    return {
        "model_provider": "avp",
        "model_providers.avp": {
            "name": "AVP",
            "base_url": (cm.provider.base_url if cm.provider else None)
            or "https://api.openai.com/v1",
            "env_key": "OPENAI_API_KEY",
            "wire_api": "responses",
            "supports_websockets": False,
        },
        "mcp_servers": servers,
        "features.multi_agent": False,
        "features.goals": False,
        "features.apps": False,
        "features.plugins": False,
        "features.web_search": False,
        "web_search": "disabled",
        "features.shell_tool": bool(allowed & SHELL_TOOLS),
        "features.unified_exec": True,
        "features.view_image": "view_image" in allowed,
        "features.stable_environment_tools": False,
        "tools.experimental_request_user_input.enabled": "request_user_input" in allowed,
        "tools.update_plan.enabled": False,
    }


def skill_instructions(cm: Commission) -> str | None:
    parts = []
    for skill in cm.skills or []:
        files = sorted(skill.files.items(), key=lambda item: item[0] != "SKILL.md")
        body = "\n\n".join(f"### {path}\n\n{text}" for path, text in files)
        parts.append(f"## Skill: {skill.name or skill.id}\n\n{body}")
    return "\n\n".join(parts) or None


def config_overrides(cm: Commission) -> tuple[str, ...]:
    """Encode Commission config for CodexConfig's native TOML overrides."""
    return tuple(f"{key}={_toml(value)}" for key, value in config(cm).items())


def _toml(value) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(k)} = {_toml(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    if value is None:
        raise ValueError("TOML config cannot contain null")
    return json.dumps(value)
