"""Commission values to the native Deep Agents graph."""

import os
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from deepagents.profiles.provider import apply_provider_profile
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ProviderStrategy
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, ToolMessage

from avp.commission import Commission, EnvSecret, McpServerStdio, ProxySecret

AGENT_NAME = "avp-deep-agents"
PROVIDERS = {"openai": "openai", "anthropic": "anthropic", "google": "google_genai"}


class MissingSecret(Exception):
    """A requested environment credential is not available."""


def secret(value: EnvSecret) -> str:
    try:
        return os.environ[value.env]
    except KeyError:
        raise MissingSecret(f"the agent's environment has no {value.env}") from None


def model(commission: Commission):
    spec = commission.model
    options: dict[str, Any] = {}
    if isinstance(spec.credential, ProxySecret):
        options["api_key"] = "avp-proxy-stand-in"
    elif isinstance(spec.credential, EnvSecret):
        options["api_key"] = secret(spec.credential)
    if spec.base_url:
        options["base_url"] = spec.base_url
    if spec.provider == "google":
        options["max_retries"] = 3
    identifier = f"{PROVIDERS[spec.provider]}:{spec.id}"
    return init_chat_model(identifier, **apply_provider_profile(identifier, options))


def instructions(commission: Commission):
    parts = [commission.system_prompt] if commission.system_prompt is not None else []
    for skill in commission.skills or []:
        text = "\n\n".join(
            f"### {path}\n\n{body}"
            for path, body in sorted(skill.files.items(), key=lambda item: item[0] != "SKILL.md")
        )
        parts.append(f"## Skill: {skill.name}\n\n{text}")
    return "\n\n".join(parts) or None


def connection(entry):
    if isinstance(entry, McpServerStdio):
        return {
            "transport": "stdio",
            "command": entry.command[0],
            "args": entry.command[1:],
            "env": {
                k: v if isinstance(v, str) else secret(v) for k, v in (entry.env or {}).items()
            },
        }
    return {
        "transport": "streamable_http",
        "url": entry.url,
        "headers": {
            k: v if isinstance(v, str) else secret(v)
            for k, v in (entry.headers or {}).items()
            if not isinstance(v, ProxySecret)
        },
    }


class RunSettings(AgentMiddleware):
    """Apply the run plan after native tool-adding middleware has run."""

    def __init__(self, hidden: set[str], override: str | None = None):
        self.hidden = hidden
        self.override = override

    def request(self, request):
        changes = {
            "tools": [
                t
                for t in request.tools
                if (t["name"] if isinstance(t, dict) else t.name) not in self.hidden
            ]
        }
        if self.override is not None:
            changes["system_message"] = SystemMessage(content=self.override)
        return request.override(**changes)

    def wrap_model_call(self, request, handler):
        return handler(self.request(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self.request(request))

    def rejection(self, request):
        if request.tool_call["name"] in self.hidden:
            return ToolMessage(
                content=f"{request.tool_call['name']} is not enabled for this run",
                tool_call_id=request.tool_call["id"],
                status="error",
            )

    def wrap_tool_call(self, request, handler):
        return self.rejection(request) or handler(request)

    async def awrap_tool_call(self, request, handler):
        return self.rejection(request) or await handler(request)


def backend():
    return LocalShellBackend(root_dir=Path.cwd(), virtual_mode=True, inherit_env=True)


def build(
    model,
    backend,
    *,
    tools=None,
    hidden=None,
    instructions=None,
    replace_prompt=False,
    response_schema=None,
):
    return create_deep_agent(
        model=model,
        backend=backend,
        tools=tools or [],
        system_prompt=instructions,
        middleware=[RunSettings(hidden or set(), instructions if replace_prompt else None)],
        response_format=ProviderStrategy(response_schema) if response_schema is not None else None,
        name=AGENT_NAME,
    )
