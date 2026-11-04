"""The tools in the pinned Codex profile, captured from model requests."""

import json
from functools import cache
from importlib.metadata import version
from importlib.resources import files
from typing import Any

from avp.descriptor import AgentDescriptor, ModelPattern, Tool

AGENT_NAME = "avp-codex"
BUILTIN_TOOLS = (
    "exec_command",
    "write_stdin",
    "apply_patch",
    "view_image",
    "list_mcp_resources",
    "list_mcp_resource_templates",
    "read_mcp_resource",
    "tool_search",
)
SHELL_TOOLS = {"exec_command", "write_stdin"}
ENVIRONMENT_TOOLS = SHELL_TOOLS | {"apply_patch", "view_image"}
RESOURCE_TOOLS = {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"}
DESCRIBE_MODEL = "gpt-5.5"


@cache
def catalog() -> dict:
    return json.loads(files("avp_codex").joinpath("tools.json").read_text())


def tools(names: list[str], model: str = DESCRIBE_MODEL) -> list[Tool]:
    definitions = catalog()["models"]
    selected = definitions.get(model, definitions[DESCRIBE_MODEL])
    result = []
    for name in names:
        entry: dict[str, Any] | None = selected.get(name) or definitions[DESCRIBE_MODEL].get(name)
        if entry is None:
            raise ValueError(f"the pinned Codex catalog has no definition for {name!r}")
        schema = entry.get("inputSchema")
        if schema is None:
            # The spec requires an object schema when the native tool has none.
            schema = {"type": "object"}

        result.append(Tool(name=name, description=entry["description"], inputSchema=schema))
    return result


def describe() -> AgentDescriptor:
    return AgentDescriptor(
        avp_version="0.1",
        agent_name=AGENT_NAME,
        agent_version=version(AGENT_NAME),
        supported_models=[ModelPattern(provider="openai", id="*")],
        tools=tools(list(BUILTIN_TOOLS)),
    )
