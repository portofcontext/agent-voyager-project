"""Commission -> OpenAI Agents SDK configuration.

- `model` `openai/<id>` runs on the SDK's native OpenAI Responses provider
  (`provider.base_url` redirects it). Any other origin routes through the SDK's
  LiteLLM extension as `litellm/<slug>`, which needs the `litellm` extra.
- `system_prompt` -> `Agent.instructions`; inline `skills` are appended to the
  instructions (every file of each skill, SKILL.md first), since the SDK has
  no skill loader.
- `prompt` -> the run input.
- The agent ships no built-ins, so every `enabled_builtin_*` list under
  `avp-openai-agents` must be empty (any name is a `commission_collision`).
- Inline `mcp_servers` -> `MCPServerStdio` / `MCPServerStreamableHttp`.
- `output_schema` -> a non-strict JSON output type.
"""

from __future__ import annotations

import dataclasses
import importlib.util
from typing import Any

from avp.commission import Commission, McpServerStdio, Skill
from avp.preflight import preflight
from avp.trajectory import ErrorCode

AGENT_NAME = "avp-openai-agents"


@dataclasses.dataclass
class RunPlan:
    origin: str
    sdk_model: str
    base_url: str | None
    prompt: str
    instructions: str | None


def from_commission(commission: Commission) -> RunPlan:
    origin, name = commission.model.split("/", 1)
    return RunPlan(
        origin=origin,
        sdk_model=name if origin == "openai" else f"litellm/{commission.model}",
        base_url=commission.provider.base_url if commission.provider else None,
        prompt=commission.prompt or "",
        instructions=_instructions(commission.system_prompt, commission.skills or []),
    )


def _instructions(system_prompt: str | None, skills: list[Skill]) -> str | None:
    parts = [system_prompt] if system_prompt else []
    for skill in skills:
        files = sorted(skill.files.items(), key=lambda kv: kv[0] != "SKILL.md")
        body = "\n\n".join(f"### {path}\n\n{text}" for path, text in files)
        parts.append(f"## Skill: {skill.name or skill.id}\n\n{body}")
    return "\n\n".join(parts) or None


def mcp_server(entry: Any, on_failure: Any) -> Any:
    """An unconnected SDK MCP server for one inline Commission entry.
    `on_failure` turns a failed tool call into the model-facing message."""
    from agents.mcp import MCPServerStdio, MCPServerStreamableHttp

    opts = {"failure_error_function": on_failure}

    if isinstance(entry, McpServerStdio):
        params: dict[str, Any] = {
            "command": entry.command[0],
            "args": entry.command[1:] + (entry.args or []),
        }
        if entry.env:
            params["env"] = entry.env
        return MCPServerStdio(params, name=entry.id, **opts)
    return MCPServerStreamableHttp(
        {"url": entry.url, "headers": entry.headers or {}}, name=entry.id, **opts
    )


def output_type(schema: dict[str, Any]) -> Any:
    from agents import AgentOutputSchemaBase

    class JsonOutput(AgentOutputSchemaBase):
        def is_plain_text(self) -> bool:
            return False

        def name(self) -> str:
            return "output"

        def json_schema(self) -> dict[str, Any]:
            return schema

        def is_strict_json_schema(self) -> bool:
            return False

        def validate_json(self, json_str: str) -> Any:
            import json

            return json.loads(json_str)

    return JsonOutput()


def fail_fast(commission: Commission, agent_version: str) -> tuple[ErrorCode, str] | None:
    """The spec's pre-turn Commission checks (`avp.preflight`), then the
    refusals specific to this harness: a provider or model it cannot reach."""
    if failure := preflight(
        commission,
        agent_name=AGENT_NAME,
        agent_version=agent_version,
        tools=[],
        subagents=[],
        skills=[],
        mcp_servers=[],
    ):
        return failure
    origin = commission.model.split("/", 1)[0]
    provider = commission.provider
    if provider is not None and provider.id != origin:
        return ErrorCode.unsupported_provider, f"cannot serve {origin} models via {provider.id!r}"
    if origin != "openai" and importlib.util.find_spec("litellm") is None:
        return (
            ErrorCode.unsupported_model,
            f"{commission.model}: non-OpenAI models need avp-openai-agents[litellm]",
        )
    return None
