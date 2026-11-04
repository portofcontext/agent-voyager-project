"""Commission values to native model, MCP, and output configuration."""

import json
import os
from typing import Any

from agents import AgentOutputSchemaBase, OpenAIProvider
from agents.mcp import MCPServerStdio, MCPServerStreamableHttp
from agents.mcp.server import MCPServerStreamableHttpParams

from avp.commission import Commission, EnvSecret, McpServerStdio, ProxySecret


class MissingSecret(Exception):
    """The launch environment does not contain the requested credential."""


class OutputInvalid(Exception):
    """Native output did not match the commissioned schema."""


def secret(value: EnvSecret) -> str:
    try:
        return os.environ[value.env]
    except KeyError:
        raise MissingSecret(f"the agent's environment has no {value.env}") from None


def model(commission: Commission):
    spec = commission.model
    if isinstance(spec.credential, ProxySecret):
        key = "avp-proxy-stand-in"
    elif isinstance(spec.credential, EnvSecret):
        key = secret(spec.credential)
    else:
        name = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[spec.provider]
        key = os.environ.get(name)
        if not key:
            raise MissingSecret(f"the agent's environment has no {name}")
    if spec.provider == "openai":
        return OpenAIProvider(
            api_key=key, base_url=spec.base_url, use_responses=True, use_responses_websocket=False
        ).get_model(spec.id)
    from agents.extensions.models.litellm_model import LitellmModel

    return LitellmModel(model=f"anthropic/{spec.id}", api_key=key, base_url=spec.base_url)


def instructions(commission: Commission) -> str | None:
    parts = [commission.system_prompt] if commission.system_prompt is not None else []
    for skill in commission.skills or []:
        text = "\n\n".join(
            f"### {path}\n\n{body}"
            for path, body in sorted(skill.files.items(), key=lambda item: item[0] != "SKILL.md")
        )
        parts.append(f"## Skill: {skill.name}\n\n{text}")
    return "\n\n".join(parts) or None


def mcp_server(entry, results):
    def on_result(context):
        if call_id := getattr(context.run_context, "tool_call_id", None):
            results[call_id] = {
                "is_error": bool(context.is_error),
                "structured_content": dict(context.structured_content)
                if context.structured_content is not None
                else None,
            }

    def on_failure(context, error):
        if call_id := getattr(context, "tool_call_id", None):
            results[call_id] = {"is_error": True}
        return f"Error: {error}"

    options: dict[str, Any] = {
        "name": entry.id,
        "cache_tools_list": True,
        "require_approval": "never",
        "failure_error_function": on_failure,
        "custom_data_extractor": on_result,
    }
    if isinstance(entry, McpServerStdio):
        params: Any = {
            "command": entry.command[0],
            "args": entry.command[1:],
            "env": {
                name: value if isinstance(value, str) else secret(value)
                for name, value in (entry.env or {}).items()
            },
        }
        return MCPServerStdio(params, **options)
    params = MCPServerStreamableHttpParams(
        url=entry.url,
        headers={
            name: value if isinstance(value, str) else secret(value)
            for name, value in (entry.headers or {}).items()
            if not isinstance(value, ProxySecret)
        },
    )
    return MCPServerStreamableHttp(params, **options)


def output_type(schema):
    if schema is None:
        return None
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(schema)

    class JsonOutput(AgentOutputSchemaBase):
        def is_plain_text(self):
            return False

        def name(self):
            return "output"

        def json_schema(self):
            return schema

        def is_strict_json_schema(self):
            return False

        def validate_json(self, json_str):
            try:
                value = json.loads(json_str)
                validator.validate(value)
                return value
            except Exception as exc:
                raise OutputInvalid(str(exc)) from exc

    return JsonOutput()
