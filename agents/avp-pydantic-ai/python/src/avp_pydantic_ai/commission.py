"""Commission -> Pydantic AI configuration.

- `model` `<origin>/<id>` -> Pydantic AI's `<origin>:<id>` model for the
  origins whose provider SDK this package ships (`openai` on the Responses
  API, `anthropic`, `google`); `provider.base_url` redirects it. Any other
  origin, or a `provider.id` that differs from the origin, fails fast.
- `system_prompt` -> `Agent.instructions`; inline `skills` are appended to the
  instructions (every file of each skill, SKILL.md first), since Pydantic AI
  has no skill loader.
- `prompt` -> the run's user prompt.
- The agent ships no built-ins, so every `enabled_builtin_*` list under
  `avp-pydantic-ai` must be empty (any name is a `commission_collision`).
- Inline `mcp_servers` -> `MCPToolset`s over FastMCP stdio / streamable HTTP
  transports. A tool error the server reports reaches the model as a failed
  tool result rather than spending a retry.
- `output_schema` -> a `StructuredDict` output type.
"""

from __future__ import annotations

from typing import Any

from avp.commission import Commission, McpServerStdio, Skill
from avp.preflight import preflight
from avp.trajectory import ErrorCode

AGENT_NAME = "avp-pydantic-ai"
# Model origins whose provider SDK ships with this package, and the provider
# class each one builds when `provider.base_url` redirects it.
ORIGINS = {
    "openai": "pydantic_ai.providers.openai:OpenAIProvider",
    "anthropic": "pydantic_ai.providers.anthropic:AnthropicProvider",
    "google": "pydantic_ai.providers.google:GoogleProvider",
}


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
    if origin not in ORIGINS:
        return (
            ErrorCode.unsupported_model,
            f"{commission.model}: {AGENT_NAME} serves {', '.join(ORIGINS)} models",
        )
    return None


def model(commission: Commission) -> Any:
    """The Pydantic AI model for the Commission."""
    from pydantic_ai.models import infer_model

    origin, name = commission.model.split("/", 1)
    base_url = commission.provider.base_url if commission.provider else None
    if not base_url:
        return infer_model(f"{origin}:{name}")
    module, cls = ORIGINS[origin].split(":")
    provider = getattr(__import__(module, fromlist=[cls]), cls)(base_url=base_url)
    return infer_model(f"{origin}:{name}", provider_factory=lambda _: provider)


def instructions(commission: Commission) -> str | None:
    parts = [commission.system_prompt] if commission.system_prompt else []
    for skill in commission.skills or []:
        parts.append(_skill_text(skill))
    return "\n\n".join(parts) or None


def _skill_text(skill: Skill) -> str:
    files = sorted(skill.files.items(), key=lambda kv: kv[0] != "SKILL.md")
    body = "\n\n".join(f"### {path}\n\n{text}" for path, text in files)
    return f"## Skill: {skill.name or skill.id}\n\n{body}"


# The MCP SDK (2.x) caps one SSE event at 1 MiB, and FastMCP's HTTP transport
# doesn't expose the setting. A gateway's `tools/list` (hundreds of tool
# schemas) is one event well past that, so raise the cap, keeping it bounded.
MAX_SSE_EVENT_BYTES = 64 * 1024 * 1024


def raise_sse_event_limit() -> bool:
    """Make FastMCP's streamable HTTP client accept SSE events up to
    `MAX_SSE_EVENT_BYTES`. A no-op (False) on an SDK without the limit."""
    import functools
    import inspect

    from fastmcp.client.transports import http

    client = http.streamable_http_client
    if isinstance(client, functools.partial):
        return True
    if "max_sse_event_size" not in inspect.signature(client).parameters:
        return False
    http.streamable_http_client = functools.partial(client, max_sse_event_size=MAX_SSE_EVENT_BYTES)
    return True


def mcp_toolset(entry: Any) -> Any:
    """An unconnected toolset for one inline Commission entry."""
    from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
    from pydantic_ai.mcp import MCPToolset

    if isinstance(entry, McpServerStdio):
        transport: Any = StdioTransport(
            entry.command[0], entry.command[1:] + (entry.args or []), env=entry.env
        )
    else:
        raise_sse_event_limit()
        transport = StreamableHttpTransport(entry.url, headers=entry.headers or {})
    return MCPToolset(transport, id=entry.id, tool_error_behavior="failed")


def output_type(schema: dict[str, Any] | None) -> Any:
    if schema is None:
        return str
    from pydantic_ai import StructuredDict

    return StructuredDict(schema)
