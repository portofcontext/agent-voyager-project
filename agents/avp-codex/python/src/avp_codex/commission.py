"""Commission to Codex configuration, following the SDK's run plan."""

import json
import os

from avp.commission import Commission, EnvSecret, McpServerStdio, ProxySecret
from avp.utils.run_plan import RunPlan
from avp_codex.descriptor import AGENT_NAME, ENVIRONMENT_TOOLS, RESOURCE_TOOLS, SHELL_TOOLS

STAND_IN_KEY = "avp-proxy-stand-in"


class MissingSecret(Exception):
    """An env Secret reference names a missing environment variable."""


def env_secret(secret: EnvSecret) -> str:
    try:
        return os.environ[secret.env]
    except KeyError:
        raise MissingSecret(f"the agent's environment has no {secret.env}") from None


def refusal(commission: Commission, plan: RunPlan) -> str | None:
    if commission.model.provider != "openai":
        return f"{AGENT_NAME} runs models at openai through the Responses API"
    allowed = {tool.name for tool in plan.started.tools or []}
    settings = (commission.agents or {}).get(AGENT_NAME)
    if (
        settings
        and settings.enabled_tools is not None
        and commission.model.id not in {"gpt-5-mini", "gpt-5.5"}
    ):
        return "Codex tool filtering is verified only for gpt-5-mini and gpt-5.5"
    if allowed & SHELL_TOOLS and not allowed >= SHELL_TOOLS:
        return "Codex requires exec_command and write_stdin together"
    if (
        allowed & ENVIRONMENT_TOOLS
        and "apply_patch" not in allowed
        and commission.model.id != "gpt-5-mini"
    ):
        return "Codex environment access also requires allowing apply_patch for this model"
    if commission.mcp_servers:
        if not allowed >= RESOURCE_TOOLS:
            return "Codex MCP servers require all three MCP resource tools to be allowed"
        if commission.model.id != "gpt-5-mini" and "tool_search" not in allowed:
            return "Codex MCP servers require tool_search to be allowed for this model"
    return None


def configuration(commission: Commission, plan: RunPlan) -> tuple[tuple[str, ...], dict[str, str]]:
    model = commission.model
    if isinstance(model.credential, ProxySecret):
        key = STAND_IN_KEY
    elif isinstance(model.credential, EnvSecret):
        key = env_secret(model.credential)
    else:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise MissingSecret("the agent's environment has no OPENAI_API_KEY")
    allowed = {tool.name for tool in plan.started.tools or []}
    servers = {}
    for server in commission.mcp_servers or []:
        entry = {"default_tools_approval_mode": "approve"}
        if isinstance(server, McpServerStdio):
            entry.update(
                command=server.command[0],
                args=server.command[1:],
                env={
                    name: value if isinstance(value, str) else env_secret(value)
                    for name, value in (server.env or {}).items()
                },
            )
        else:
            entry.update(
                url=server.url,
                http_headers={
                    name: value
                    for name, value in (server.headers or {}).items()
                    if isinstance(value, str)
                },
                env_http_headers={
                    name: value.env
                    for name, value in (server.headers or {}).items()
                    if isinstance(value, EnvSecret)
                },
            )
            for value in (server.headers or {}).values():
                if isinstance(value, EnvSecret):
                    env_secret(value)

        servers[server.id] = entry
    config = {
        "model_provider": "avp",
        "model_providers.avp": {
            "name": "AVP",
            "base_url": model.base_url
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1",
            "env_key": "AVP_CODEX_API_KEY",
            "wire_api": "responses",
            "requires_openai_auth": False,
            "supports_websockets": False,
        },
        "mcp_servers": servers,
        "features.multi_agent": False,
        "features.goals": False,
        "features.apps": False,
        "features.plugins": False,
        "features.skill_search": False,
        "features.sleep_tool": False,
        "features.tool_suggest": False,
        "web_search": "disabled",
        "features.shell_tool": bool(allowed & SHELL_TOOLS),
        "features.unified_exec": True,
        "features.view_image": "view_image" in allowed,
        "features.stable_environment_tools": False,
        "tools.experimental_request_user_input.enabled": False,
        "tools.update_plan.enabled": False,
        "check_for_update_on_startup": False,
        "analytics.enabled": False,
        "feedback.enabled": False,
    }
    return tuple(f"{name}={toml(value)}" for name, value in config.items()), {
        "AVP_CODEX_API_KEY": key
    }


def skill_instructions(commission: Commission) -> str | None:
    parts = []
    for skill in commission.skills or []:
        body = "\n\n".join(
            f"### {path}\n\n{text}"
            for path, text in sorted(skill.files.items(), key=lambda item: item[0] != "SKILL.md")
        )
        parts.append(f"## Skill: {skill.name}\n\n{body}")
    return "\n\n".join(parts) or None


def toml(value) -> str:
    if isinstance(value, dict):
        return (
            "{"
            + ", ".join(f"{json.dumps(key)} = {toml(item)}" for key, item in value.items())
            + "}"
        )
    if isinstance(value, list):
        return "[" + ", ".join(toml(item) for item in value) + "]"
    return json.dumps(value)
