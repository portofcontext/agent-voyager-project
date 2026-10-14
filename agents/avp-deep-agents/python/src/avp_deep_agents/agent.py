"""The adapter: a Deep Agents run, recorded through `AvpCallbackHandler`.

Deep Agents owns the loop (`create_deep_agent(...).ainvoke`). The adapter maps
the Commission onto it, dials the Commission's MCP servers, and attaches the
callback handler, which reports each model call, tool call, and `task`
subagent to the Recorder. LangChain and Deep Agents are imported inside
`describe` / `run` so `ping` stays light.

The descriptor mirrors what this configuration of Deep Agents ships: the
filesystem tools and `execute` of its workspace backend, and the `task` tool
with its default `general-purpose` subagent. It is read off an agent built
the same way, so it tracks the pinned package rather than a hand-kept list.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

from avp.commission import Commission
from avp.descriptor import AgentDescriptor, McpServerDecl, SkillDecl, SubagentDecl, ToolDecl
from avp.pricing import load_default_prices
from avp.recorder import Recorder
from avp.sink import EventSink
from avp.trajectory import ErrorCode, StopReason
from avp_deep_agents import commission as cm
from avp_deep_agents import translate

AGENT_VERSION = version(cm.AGENT_NAME)
# A stdio server that hasn't answered `initialize` by then is reported failed.
MCP_CONNECT_TIMEOUT_S = 60


@functools.cache
def describe() -> AgentDescriptor:
    """What the agent ships with, before any Commission."""
    from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    placeholder = GenericFakeChatModel(messages=iter(()))
    graph = cm.build_agent(placeholder, backend=cm.backend(None))
    return AgentDescriptor(
        agent_name=cm.AGENT_NAME,
        agent_version=AGENT_VERSION,
        spec_version="0.1",
        tools=[_decl(tool) for tool in cm.tool_node_tools(graph).values()],
        subagents=[
            SubagentDecl(
                name=GENERAL_PURPOSE_SUBAGENT["name"],
                description=GENERAL_PURPOSE_SUBAGENT["description"],
            )
        ],
    )


def _decl(tool: Any, server: str | None = None) -> ToolDecl:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    return ToolDecl(
        name=tool.name,
        description=tool.description,
        inputSchema=convert_to_openai_tool(tool)["function"].get("parameters"),
        mcp_server_id=server,
    )


async def _dial(
    commission: Commission, rec: Recorder, stack: contextlib.AsyncExitStack
) -> tuple[list[Any], list[McpServerDecl], dict[str, str]]:
    """Open a session to each inline MCP server and load its tools; a server
    that fails is reported and left out of the run. Returns the tools, the
    server decls, and each tool's server."""
    from langchain_mcp_adapters.sessions import create_session
    from langchain_mcp_adapters.tools import load_mcp_tools

    tools: list[Any] = []
    decls: list[McpServerDecl] = []
    owners: dict[str, str] = {}
    for entry in commission.mcp_servers or []:
        server = contextlib.AsyncExitStack()
        try:
            async with asyncio.timeout(MCP_CONNECT_TIMEOUT_S):
                session = await server.enter_async_context(create_session(cm.mcp_connection(entry)))
                await session.initialize()
                listed = await load_mcp_tools(session, server_name=entry.id)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await server.aclose()
            await rec.error(ErrorCode.mcp_connect_failed, f"{entry.id}: {_reason(exc)}")
            decls.append(McpServerDecl(id=entry.id, status="failed"))
            continue
        stack.push_async_callback(server.aclose)
        decls.append(McpServerDecl(id=entry.id, status="connected"))
        for tool in listed:
            tool.name = cm.mcp_tool_name(entry.id, tool.name)
            owners[tool.name] = entry.id
            tools.append(tool)
    return tools, decls, owners


def _reason(exc: BaseException) -> str:
    """The innermost cause of a connect failure (MCP's task groups wrap it)."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return str(exc) or type(exc).__name__


async def run(commission: Commission, sink: EventSink) -> None:
    prices = load_default_prices()
    origin = commission.model.split("/", 1)[0]
    rec = Recorder(sink, run_id=commission.run_id, provider=origin, prices=prices)
    descriptor = describe()
    await rec.prelude(commission, descriptor)
    builtin_tools = [t.name for t in descriptor.tools or []]
    builtin_subagents = [s.name for s in descriptor.subagents or []]
    if failure := cm.fail_fast(commission, AGENT_VERSION, builtin_tools, builtin_subagents):
        await rec.error(*failure)
        await rec.stop(StopReason.error)
        return

    from avp_deep_agents.callbacks import AvpCallbackHandler

    tools_on = cm.allowed(commission, "enabled_builtin_tools", builtin_tools)
    subagents_on = cm.allowed(commission, "enabled_builtin_subagents", builtin_subagents)
    if cm.TASK_TOOL not in tools_on or not subagents_on:
        tools_on = [t for t in tools_on if t != cm.TASK_TOOL]
        subagents_on = []
    hidden = frozenset(builtin_tools) - set(tools_on)
    prompt = commission.prompt or ""
    async with contextlib.AsyncExitStack() as stack:
        try:
            mcp_tools, mcp_decls, owners = await _dial(commission, rec, stack)
            skills_dir = None
            if commission.skills:
                skills_dir = Path(stack.enter_context(tempfile.TemporaryDirectory()))
                cm.write_skills(commission, skills_dir)
            graph = cm.build_agent(
                cm.chat_model(commission),
                backend=cm.backend(skills_dir),
                tools=mcp_tools,
                hidden=hidden,
                skills=skills_dir is not None,
                system_prompt=commission.system_prompt,
                response_format=commission.output_schema,
            )
            await rec.start(
                request_model=commission.model,
                prompt=prompt,
                system_prompt=commission.system_prompt,
                tools=[
                    _decl(tool, owners.get(name))
                    for name, tool in cm.tool_node_tools(graph).items()
                    if name not in hidden
                ],
                mcp_servers=mcp_decls or None,
                skills=[
                    SkillDecl(name=s.name or s.id, description=s.description)
                    for s in commission.skills or []
                ]
                or None,
                subagents=[s for s in descriptor.subagents or [] if s.name in subagents_on],
                thread_id=commission.thread_id,
                tags=commission.tags,
            )
            handler = AvpCallbackHandler(rec, request_model=commission.model, prices=prices)
            result = await graph.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                {"callbacks": [handler]},
            )
            final = result["messages"][-1] if result.get("messages") else None
            if final is not None and final.type == "ai" and translate.is_refusal(final):
                await rec.stop(StopReason.refused, final.text)
            else:
                structured = result.get("structured_response")
                output = structured if structured is not None else (final.text if final else None)
                await rec.stop(StopReason.converged, output)
        except asyncio.CancelledError:
            await rec.stop(StopReason.interrupted)
            raise
        except Exception as exc:
            code = translate.error_code(exc)
            await rec.error(code, str(exc) or type(exc).__name__)
            await rec.stop(StopReason.error)
            if code is ErrorCode.agent_crash:
                raise
