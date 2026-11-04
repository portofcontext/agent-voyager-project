"""Commission and run plan to Claude's native options."""

import os
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import SystemPromptPreset

from avp.commission import Commission, EnvSecret, McpServerStdio, ProxySecret
from avp.utils.run_plan import RunPlan


class MissingSecret(Exception):
    """A named environment secret is unavailable."""


def secret(value: EnvSecret) -> str:
    try:
        return os.environ[value.env]
    except KeyError:
        raise MissingSecret(f"the agent's environment has no {value.env}") from None


def options(commission: Commission, plan: RunPlan) -> ClaudeAgentOptions:
    env = {
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
        "ENABLE_TOOL_SEARCH": "false",
        "CLAUDE_CODE_USE_BEDROCK": "0",
        "CLAUDE_CODE_USE_VERTEX": "0",
        "CLAUDE_CODE_USE_FOUNDRY": "0",
    }
    credential = commission.model.credential
    if credential is not None:
        env.update(
            ANTHROPIC_API_KEY="avp-proxy-stand-in"
            if isinstance(credential, ProxySecret)
            else secret(credential),
            ANTHROPIC_AUTH_TOKEN="",
            CLAUDE_CODE_OAUTH_TOKEN="",
        )
    if commission.model.base_url:
        env["ANTHROPIC_BASE_URL"] = commission.model.base_url
    servers: dict[str, Any] = {}
    for server in commission.mcp_servers or []:
        if isinstance(server, McpServerStdio):
            servers[server.id] = {
                "command": server.command[0],
                "args": server.command[1:],
                "env": {
                    k: v if isinstance(v, str) else secret(v) for k, v in (server.env or {}).items()
                },
            }
        else:
            servers[server.id] = {
                "type": "http",
                "url": server.url,
                "headers": {
                    k: v if isinstance(v, str) else secret(v)
                    for k, v in (server.headers or {}).items()
                    if not isinstance(v, ProxySecret)
                },
            }
    instructions = []
    for skill in commission.skills or []:
        body = "\n\n".join(
            f"### {p}\n\n{v}"
            for p, v in sorted(skill.files.items(), key=lambda item: item[0] != "SKILL.md")
        )
        instructions.append(f"## Skill: {skill.name}\n\n{body}")
    appended = "\n\n".join(instructions)
    prompt: Any = commission.system_prompt
    if prompt is not None:
        prompt = "\n\n".join(part for part in [prompt, appended] if part)
    else:
        prompt = SystemPromptPreset(type="preset", preset="claude_code", append=appended)
    disallowed = list(plan.turned_off.tools) + [
        f"Agent({name})" for name in plan.turned_off.subagents
    ]
    return ClaudeAgentOptions(
        cli_path=os.environ.get("AVP_CLAUDE_CLI", "claude"),
        model=commission.model.id,
        cwd=str(Path.cwd()),
        system_prompt=prompt,
        tools=[t.name for t in plan.started.tools or []],
        disallowed_tools=disallowed,
        skills=[s.name for s in plan.started.skills or [] if s.source is None],
        mcp_servers=servers,
        strict_mcp_config=True,
        setting_sources=[],
        permission_mode="bypassPermissions",
        include_partial_messages=True,
        output_format={"type": "json_schema", "schema": commission.output_schema}
        if commission.output_schema is not None
        else None,
        env=env,
        extra_args={"name": commission.run_id},
    )
