"""Commission -> Deep Agents configuration.

- `model` `<origin>/<id>` -> `init_chat_model("<provider>:<id>")` with Deep
  Agents' provider profile applied (OpenAI runs on the Responses API), for the
  origins whose LangChain integration this package ships (`openai`,
  `anthropic`, and `google` as `google_genai`); `provider.base_url` redirects
  it. Any other origin, or a `provider.id` that differs from the origin, fails
  fast.
- `system_prompt` -> `create_deep_agent(system_prompt=...)`; `prompt` -> the
  run's first user message; `output_schema` -> `response_format`.
- Inline `skills` -> Deep Agents' own skills mechanism: each skill's files
  are written under a private directory mounted at `SKILLS_ROUTE`, which the
  agent's `SkillsMiddleware` indexes into the system prompt and the model
  reads with `read_file`.
- Inline `mcp_servers` -> `langchain-mcp-adapters` sessions; their tools join
  the agent's tools as `mcp__<server>__<tool>`.
- `enabled_builtin_tools` / `enabled_builtin_subagents` under `avp-deep-agents`
  hide built-ins from the model and reject calls to them, the way Deep Agents'
  own `HarnessProfile.excluded_tools` does, in the main agent and in the
  general-purpose subagent.
- Files land in the workspace: the backend is a `LocalShellBackend` rooted
  at the working directory (virtual paths, so `/notes.txt` is
  `<cwd>/notes.txt`), which also provides `execute`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from avp.commission import Commission, McpServerStdio
from avp.preflight import preflight
from avp.trajectory import ErrorCode

AGENT_NAME = "avp-deep-agents"
# Model origins with a pinned LangChain chat-model integration, and the
# `init_chat_model` provider each maps to.
ORIGINS = {"openai": "openai", "anthropic": "anthropic", "google": "google_genai"}
TASK_TOOL = "task"
SKILLS_ROUTE = "/.avp-skills/"


def fail_fast(
    commission: Commission, agent_version: str, tools: Iterable[str], subagents: Iterable[str]
) -> tuple[ErrorCode, str] | None:
    """The spec's pre-turn Commission checks (`avp.preflight`), then the
    refusals specific to this harness: a provider or model it cannot reach."""
    if failure := preflight(
        commission,
        agent_name=AGENT_NAME,
        agent_version=agent_version,
        tools=tools,
        subagents=subagents,
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
            f"{commission.model}: avp-deep-agents serves {', '.join(ORIGINS)} models",
        )
    return None


def allowed(commission: Commission, field: str, offered: Iterable[str]) -> list[str]:
    """The built-ins an `enabled_builtin_*` allow-list leaves exposed."""
    allow = (getattr(commission, field) or {}).get(AGENT_NAME)
    return [name for name in offered if allow is None or name in allow]


def chat_model(commission: Commission) -> Any:
    from deepagents.profiles.provider import apply_provider_profile
    from langchain.chat_models import init_chat_model

    origin, name = commission.model.split("/", 1)
    spec = f"{ORIGINS[origin]}:{name}"
    kwargs: dict[str, Any] = {}
    if commission.provider and commission.provider.base_url:
        kwargs["base_url"] = commission.provider.base_url
    return init_chat_model(spec, **apply_provider_profile(spec, kwargs))


def backend(skills_dir: Path | None) -> Any:
    """The workspace backend, plus the skills mount when there are skills."""
    from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend

    workspace = LocalShellBackend(root_dir=os.getcwd(), virtual_mode=True, inherit_env=True)
    if skills_dir is None:
        return workspace
    return CompositeBackend(
        default=workspace,
        routes={SKILLS_ROUTE: FilesystemBackend(root_dir=skills_dir, virtual_mode=True)},
    )


def write_skills(commission: Commission, root: Path) -> None:
    """Lay each inline skill out as `<root>/<name>/<files>`; Deep Agents
    requires a skill's directory to be named after it."""
    for skill in commission.skills or []:
        base = root / (skill.name or skill.id)
        for rel, text in skill.files.items():
            path = (base / rel).resolve()
            if not path.is_relative_to(base.resolve()):
                raise ValueError(f"skill {skill.id}: file path {rel!r} escapes the skill directory")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)


def mcp_connection(entry: Any) -> dict[str, Any]:
    if isinstance(entry, McpServerStdio):
        conn: dict[str, Any] = {
            "transport": "stdio",
            "command": entry.command[0],
            "args": entry.command[1:] + (entry.args or []),
        }
        if entry.env:
            conn["env"] = entry.env
        return conn
    return {"transport": "streamable_http", "url": entry.url, "headers": entry.headers or {}}


def mcp_tool_name(server: str, tool: str) -> str:
    """`mcp__<server>__<tool>`, the name AVP's other adapters give MCP tools."""
    return f"mcp__{_clean(server)}__{_clean(tool)}"


def _clean(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def allow_list(hidden: frozenset[str]) -> Any:
    """Middleware hiding `hidden` built-ins from the model and rejecting calls
    that name them anyway, as a `ToolMessage` error."""
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.messages import ToolMessage

    class BuiltinAllowList(AgentMiddleware):
        def _visible(self, request: Any) -> Any:
            tools = [t for t in request.tools if _tool_name(t) not in hidden]
            return request.override(tools=tools)

        def _rejection(self, request: Any) -> ToolMessage | None:
            name = request.tool_call["name"]
            if name not in hidden:
                return None
            return ToolMessage(
                content=f"Error: {name} is not enabled for this run.",
                tool_call_id=request.tool_call["id"] or "",
                name=name,
                status="error",
            )

        def wrap_model_call(self, request: Any, handler: Any) -> Any:
            return handler(self._visible(request))

        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            return await handler(self._visible(request))

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            return self._rejection(request) or handler(request)

        async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
            return self._rejection(request) or await handler(request)

    return BuiltinAllowList()


def _tool_name(tool: Any) -> str | None:
    return tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)


def build_agent(
    model: Any,
    *,
    backend: Any,
    tools: list[Any] | None = None,
    hidden: frozenset[str] = frozenset(),
    skills: bool = False,
    system_prompt: str | None = None,
    response_format: dict[str, Any] | None = None,
) -> Any:
    """`create_deep_agent` with this adapter's configuration. `describe` builds
    the same agent around a placeholder model to read off what it ships."""
    from deepagents import create_deep_agent
    from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT

    middleware, subagents = [], None
    if hidden:
        middleware.append(allow_list(hidden))
        # The default general-purpose subagent builds its own tool stack, so
        # hand Deep Agents the same spec carrying the allow-list.
        subagents = [{**GENERAL_PURPOSE_SUBAGENT, "middleware": [allow_list(hidden)]}]
    return create_deep_agent(
        model=model,
        tools=tools or None,
        system_prompt=system_prompt,
        middleware=middleware,
        subagents=subagents,
        skills=[SKILLS_ROUTE] if skills else None,
        backend=backend,
        response_format=response_format,
        name=AGENT_NAME,
    )


def tool_node_tools(graph: Any) -> dict[str, Any]:
    """The tools the agent can dispatch, by name, read off its graph."""
    node = graph.nodes.get("tools")
    return dict(node.bound.tools_by_name) if node is not None else {}
