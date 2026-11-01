"""The run: Pydantic AI's run graph in, Recorder calls out.

Pydantic AI runs the loop (`Agent.iter`). After each graph node the agent reads
what the node added to the run's message history: each `ModelResponse` is one
model response, and each tool return or retry prompt in the following
`ModelRequest` is the result of the call it answers.
"""

import asyncio
import time
from contextlib import AsyncExitStack

import pydantic_ai
from pydantic import JsonValue
from pydantic_ai import Agent, ModelMessage, ModelResponse
from pydantic_ai.models import Model

from avp.agent_cli import EventSink
from avp.commission import Commission
from avp.descriptor import Tool
from avp.recorder import Recorder
from avp.trajectory import StopReason
from avp.utils.run_plan import plan_run
from avp_pydantic_ai import commission as cm
from avp_pydantic_ai import translate
from avp_pydantic_ai.descriptor import AGENT_NAME, describe

pydantic_ai.BANNER_ENABLED = False  # ty: ignore[invalid-assignment]
"""Pydantic AI prints a banner to stderr on its first run in a process."""


def model(commission: Commission) -> Model:
    """The Pydantic AI model for the run. Tests replace this to script it."""
    return cm.model(commission)


class _ConnectFailed(Exception):
    pass


async def _connect(commission: Commission, stack: AsyncExitStack) -> tuple[list, list[Tool]]:
    """Connect each of the Commission's MCP servers for the length of the run,
    and list their tools. Raises `_ConnectFailed` naming the first that fails."""
    toolsets, tools = [], []
    for server in commission.mcp_servers or []:
        try:
            toolset = cm.mcp_toolset(server)
            await stack.enter_async_context(toolset)
            listed = await toolset.list_tools()
        except Exception as exc:
            raise _ConnectFailed(f"{server.id}: {exc}") from exc
        toolsets.append(toolset)
        tools += [
            Tool.model_validate(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                    "mcp_server_id": server.id,
                }
            )
            for tool in listed
        ]
    return toolsets, tools


class _History:
    """Reports the messages a run adds to its history, in order."""

    def __init__(self, rec: Recorder, model_id: str) -> None:
        self.rec = rec
        self.model_id = model_id
        self.seen = 0
        self.started = time.monotonic()
        self.finish: str | None = None

    async def report(self, messages: list[ModelMessage]) -> None:
        for message in messages[self.seen :]:
            if isinstance(message, ModelResponse):
                self.finish = message.finish_reason
                await self.rec.response(
                    translate.content(message.parts),
                    usage=translate.usage(message.usage),
                    response_model=message.model_name
                    if message.model_name != self.model_id
                    else None,
                    finish_reasons=translate.finish_reasons(message),
                    duration_ms=int((time.monotonic() - self.started) * 1000),
                )
            else:
                for call_id, output, is_error in translate.tool_results(message.parts):
                    await self.rec.tool_returned(call_id, output, is_error=is_error)
        self.seen = len(messages)


async def run(received: JsonValue, sink: EventSink) -> None:
    descriptor = describe()
    rec = Recorder(sink)
    commission = await rec.begin(received, descriptor)
    if commission is None:
        return
    if refusal := cm.refusal(commission):
        await rec.error("invalid_commission", refusal)
        return

    instructions = cm.instructions(commission)
    plan = plan_run(commission, descriptor)
    history = _History(rec, commission.model.id)
    async with AsyncExitStack() as stack:
        try:
            try:
                run_model = model(commission)
            except cm.MissingSecret as exc:
                await rec.error("auth_error", str(exc))
                return
            try:
                toolsets, tools = await _connect(commission, stack)
            except _ConnectFailed as exc:
                await rec.error("mcp_connect_failed", str(exc))
                return
            servers = [
                server.model_copy(update={"status": "connected"})
                for server in plan.started.mcp_servers or []
            ]
            await rec.start(
                plan.started.model_copy(
                    update={
                        "system_prompt": instructions,
                        "tools": tools or None,
                        "mcp_servers": servers or None,
                    }
                )
            )
            agent = Agent(
                run_model,
                name=AGENT_NAME,
                instructions=instructions,
                output_type=cm.output_type(commission.output_schema),
                toolsets=toolsets,
            )
            async with agent.iter(commission.prompt) as agent_run:
                async for node in agent_run:
                    await history.report(agent_run.ctx.state.message_history)
                    if Agent.is_model_request_node(node):
                        history.started = time.monotonic()
                await history.report(agent_run.ctx.state.message_history)
                output = agent_run.result.output if agent_run.result else None
            reason: StopReason = "refused" if history.finish == "content_filter" else "converged"
            await rec.stop(reason, output)
        except asyncio.CancelledError:
            await rec.stop("interrupted")
            raise
        except Exception as exc:
            if history.finish == "content_filter":
                await rec.stop("refused", str(exc) or None)
                return
            code = translate.error_code(exc)
            await rec.error(code, str(exc) or type(exc).__name__)
            await rec.stop("error")
            if code == "agent_crash":
                raise
