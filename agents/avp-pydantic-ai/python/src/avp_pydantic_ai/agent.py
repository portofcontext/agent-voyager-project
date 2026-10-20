"""The adapter: Pydantic AI's run graph in, Recorder calls out.

Pydantic AI owns the loop (`Agent.iter`). After each graph node the adapter
reads what the node added to the run's message history: each `ModelResponse`
is one complete turn, and each tool return or retry prompt in the following
`ModelRequest` is the result of the call it answers.

Pydantic AI is a framework: its agents ship with no tools, skills, or
subagents, so neither does this one (the descriptor mirrors the harness). Tools
come from the Commission's `mcp_servers`. Pydantic AI is imported inside `run`
so `ping` stays light.
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import AsyncExitStack
from importlib.metadata import version
from typing import Any

from avp.commission import Commission
from avp.descriptor import AgentDescriptor, McpServerDecl, SkillDecl, ToolDecl
from avp.pricing import load_default_prices
from avp.recorder import Recorder
from avp.sink import EventSink
from avp.trajectory import ErrorCode, StopReason
from avp_pydantic_ai import commission as cm
from avp_pydantic_ai import translate

AGENT_VERSION = version(cm.AGENT_NAME)


def describe() -> AgentDescriptor:
    """What the agent ships with, before any Commission."""
    return AgentDescriptor(
        agent_name=cm.AGENT_NAME,
        agent_version=AGENT_VERSION,
        spec_version="0.1",
    )


def model(commission: Commission) -> Any:
    """The Pydantic AI model for the run. Tests replace this to script it."""
    return cm.model(commission)


async def _dial(
    commission: Commission, rec: Recorder, stack: AsyncExitStack
) -> tuple[list, list[McpServerDecl], list[ToolDecl]]:
    """Connect each inline MCP server for the length of the run; a server that
    fails is reported and left out."""
    toolsets, decls, tool_decls = [], [], []
    for entry in commission.mcp_servers or []:
        toolset = cm.mcp_toolset(entry)
        try:
            await stack.enter_async_context(toolset)
            listed = await toolset.list_tools()
        except Exception as exc:
            await rec.error(ErrorCode.mcp_connect_failed, f"{entry.id}: {exc}")
            decls.append(McpServerDecl(id=entry.id, status="failed"))
            continue
        toolsets.append(toolset)
        decls.append(McpServerDecl(id=entry.id, status="connected"))
        tool_decls += [
            ToolDecl(
                name=t.name,
                description=t.description,
                inputSchema=_input_schema(t),
                mcp_server_id=entry.id,
            )
            for t in listed
        ]
    return toolsets, decls, tool_decls


class _History:
    """Reports the messages a run adds to its history, in order."""

    def __init__(self, rec: Recorder, request_model: str) -> None:
        self.rec = rec
        self.request_model = request_model
        self.seen = 0
        self.started = time.monotonic()
        self.finish: str | None = None

    async def report(self, messages: list[Any]) -> None:
        from pydantic_ai import ModelResponse

        for message in messages[self.seen :]:
            if isinstance(message, ModelResponse):
                self.finish = message.finish_reason
                await self.rec.assistant(
                    translate.content(message.parts),
                    translate.usage(message.usage),
                    model=message.model_name,
                    request_model=self.request_model,
                    finish_reasons=translate.finish_reasons(message),
                    duration_ms=int((time.monotonic() - self.started) * 1000),
                )
            else:
                for call_id, output, is_error in translate.tool_results(message.parts):
                    await self.rec.tool_result(call_id, output, is_error=is_error)
        self.seen = len(messages)


async def run(commission: Commission, sink: EventSink) -> None:
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    origin = commission.model.split("/", 1)[0]
    rec = Recorder(sink, run_id=commission.run_id, provider=origin, prices=load_default_prices())
    await rec.prelude(commission, describe())
    if failure := cm.fail_fast(commission, AGENT_VERSION):
        await rec.error(*failure)
        await rec.stop(StopReason.error)
        return

    from pydantic_ai import Agent

    prompt = commission.prompt or ""
    instructions = cm.instructions(commission)
    history = _History(rec, commission.model)
    async with AsyncExitStack() as stack:
        try:
            toolsets, mcp_decls, mcp_tool_decls = await _dial(commission, rec, stack)
            await rec.start(
                request_model=commission.model,
                prompt=prompt,
                system_prompt=instructions,
                tools=mcp_tool_decls,
                mcp_servers=mcp_decls or None,
                skills=[
                    SkillDecl(name=s.name or s.id, description=s.description)
                    for s in commission.skills or []
                ]
                or None,
                thread_id=commission.thread_id,
                tags=commission.tags,
            )
            agent = Agent(
                model(commission),
                name=cm.AGENT_NAME,
                instructions=instructions,
                output_type=cm.output_type(commission.output_schema),
                toolsets=toolsets,
            )
            async with agent.iter(prompt) as agent_run:
                async for node in agent_run:
                    await history.report(agent_run.ctx.state.message_history)
                    if Agent.is_model_request_node(node):
                        history.started = time.monotonic()
                await history.report(agent_run.ctx.state.message_history)
                output = agent_run.result.output if agent_run.result else None
            if history.finish == "content_filter":
                await rec.stop(StopReason.refused, output)
            else:
                await rec.stop(StopReason.converged, output)
        except asyncio.CancelledError:
            await rec.stop(StopReason.interrupted)
            raise
        except Exception as exc:
            if history.finish == "content_filter":
                await rec.stop(StopReason.refused, str(exc) or None)
                return
            code = translate.error_code(exc)
            await rec.error(code, str(exc) or type(exc).__name__)
            await rec.stop(StopReason.error)
            if code is ErrorCode.agent_crash:
                raise


def _input_schema(tool: Any) -> Any:
    """A listed MCP tool's input schema: `input_schema` in MCP SDK 2,
    `inputSchema` in 1."""
    return getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
