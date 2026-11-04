"""Commission -> Pydantic AI configuration.

- `model` -> the Pydantic AI model for `model.provider`, at `model.base_url`
  when present. A `proxy` credential gets a stand-in key, which the proxy
  replaces; an `env` credential is read from the agent's environment; without
  one, the provider's client finds its own.
- `system_prompt` and `skills` -> the run's instructions. Pydantic AI has no
  skill loader, so each skill's files follow the system prompt, SKILL.md first.
- `mcp_servers` -> `MCPToolset`s over FastMCP's stdio and Streamable HTTP
  transports. A header with a `proxy` secret is left out, for the proxy to add.
  A tool error the server reports reaches the model as a failed tool result.
- `output_schema` -> a `StructuredDict` output type.
"""

import functools
import importlib
import inspect
import os
from typing import Any

from fastmcp.client.transports import StdioTransport, StreamableHttpTransport, http
from pydantic_ai import StructuredDict
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model, infer_model

from avp.commission import Commission, EnvSecret, McpServer, McpServerStdio, ProxySecret, Skill
from avp_pydantic_ai.descriptor import AGENT_NAME, PROVIDERS

STAND_IN_KEY = "avp-proxy-stand-in"
"""The API key sent for a `proxy` credential. The proxy replaces it."""


class MissingSecret(Exception):
    """An `env` Secret reference names a variable the agent's environment lacks."""


def refusal(commission: Commission) -> str | None:
    """Why the agent cannot run the Commission's model, or None."""
    provider = commission.model.provider
    if provider not in PROVIDERS:
        return f"{AGENT_NAME} cannot call {provider!r}; it runs models at {', '.join(PROVIDERS)}"
    return None


def env_secret(secret: EnvSecret) -> str:
    try:
        return os.environ[secret.env]
    except KeyError:
        raise MissingSecret(f"the agent's environment has no {secret.env}") from None


def model(commission: Commission) -> Model:
    """The Pydantic AI model for the Commission. Raises `MissingSecret`."""
    spec = commission.model
    credential = spec.credential
    if isinstance(credential, ProxySecret):
        api_key = STAND_IN_KEY
    elif isinstance(credential, EnvSecret):
        api_key = env_secret(credential)
    else:
        api_key = None
    module, name = PROVIDERS[spec.provider].split(":")
    provider_class = getattr(importlib.import_module(module), name)
    provider = provider_class(api_key=api_key, base_url=spec.base_url)
    return infer_model(f"{spec.provider}:{spec.id}", provider_factory=lambda _: provider)


def instructions(commission: Commission) -> str | None:
    parts = [commission.system_prompt] if commission.system_prompt else []
    parts += [_skill_text(skill) for skill in commission.skills or []]
    return "\n\n".join(parts) or None


def _skill_text(skill: Skill) -> str:
    files = sorted(skill.files.items(), key=lambda item: item[0] != "SKILL.md")
    body = "\n\n".join(f"### {path}\n\n{text}" for path, text in files)
    return f"## Skill: {skill.name}\n\n{body}"


# The MCP SDK caps one SSE event at 1 MiB, and FastMCP's HTTP transport doesn't
# expose the setting. A gateway's `tools/list` (hundreds of tool schemas) is one
# event well past that, so raise the cap, keeping it bounded.
MAX_SSE_EVENT_BYTES = 64 * 1024 * 1024


def raise_sse_event_limit() -> bool:
    """Make FastMCP's streamable HTTP client accept SSE events up to
    `MAX_SSE_EVENT_BYTES`. A no-op (False) on an SDK without the limit."""
    client = http.streamable_http_client
    if isinstance(client, functools.partial):
        return True
    if "max_sse_event_size" not in inspect.signature(client).parameters:
        return False
    http.streamable_http_client = functools.partial(  # ty: ignore[invalid-assignment]
        client, max_sse_event_size=MAX_SSE_EVENT_BYTES
    )
    return True


def mcp_toolset(server: McpServer) -> MCPToolset:
    """An unconnected toolset for one of the Commission's MCP servers. Raises
    `MissingSecret`."""
    if isinstance(server, McpServerStdio):
        env = {
            key: value if isinstance(value, str) else env_secret(value)
            for key, value in (server.env or {}).items()
        }
        transport: Any = StdioTransport(server.command[0], server.command[1:], env=env or None)
    else:
        headers = {
            key: value if isinstance(value, str) else env_secret(value)
            for key, value in (server.headers or {}).items()
            if not isinstance(value, ProxySecret)
        }
        raise_sse_event_limit()
        transport = StreamableHttpTransport(server.url, headers=headers)
    return MCPToolset(transport, id=server.id, tool_error_behavior="failed")


def output_type(schema: dict[str, Any] | None) -> Any:
    if schema is None:
        return str
    return StructuredDict(schema)
