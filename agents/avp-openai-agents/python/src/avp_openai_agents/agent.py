"""The adapter: OpenAI Agents SDK stream in, Recorder calls out.

The SDK owns the loop (`Runner.run_streamed`). Each raw `response.completed`
(or `response.incomplete`) event closes one model call and is reported as one
complete turn; each `tool_output` run item is reported as its tool result.

The OpenAI Agents SDK is a framework: its agents ship with no tools, skills, or
subagents, so neither does this one (the descriptor mirrors the harness). Tools
come from the Commission's `mcp_servers`. The SDK is imported inside `run` so
`ping` stays light.
"""

from __future__ import annotations

import asyncio
import time
from importlib.metadata import version
from typing import Any

from avp.commission import Commission
from avp.descriptor import AgentDescriptor, McpServerDecl, SkillDecl, ToolDecl
from avp.pricing import load_default_prices
from avp.recorder import Recorder
from avp.sink import EventSink
from avp.trajectory import ErrorCode, StopReason
from avp_openai_agents import commission as cm
from avp_openai_agents import translate

AGENT_VERSION = version(cm.AGENT_NAME)


def describe() -> AgentDescriptor:
    """What the agent ships with, before any Commission."""
    return AgentDescriptor(
        agent_name=cm.AGENT_NAME,
        agent_version=AGENT_VERSION,
        spec_version="0.1",
    )


def model_provider(plan: cm.RunPlan) -> Any:
    """The SDK `ModelProvider` for the run; None keeps the SDK default.
    Tests replace this to script the model."""
    if plan.base_url and plan.origin == "openai":
        from agents import OpenAIProvider

        return OpenAIProvider(base_url=plan.base_url)
    return None


async def _dial(
    commission: Commission, rec: Recorder, errored: set[str]
) -> tuple[list, list, list]:
    """Connect each inline MCP server; a server that fails is reported and
    left out of the run."""
    servers, decls, tool_decls = [], [], []
    for entry in commission.mcp_servers or []:
        server = cm.mcp_server(entry, _failure_recorder(errored))
        try:
            await server.connect()
            listed = await server.list_tools()
        except Exception as exc:
            await rec.error(ErrorCode.mcp_connect_failed, f"{entry.id}: {exc}")
            decls.append(McpServerDecl(id=entry.id, status="failed"))
            await server.cleanup()
            continue
        servers.append(server)
        decls.append(McpServerDecl(id=entry.id, status="connected"))
        tool_decls += [
            ToolDecl(
                name=t.name,
                description=t.description,
                inputSchema=t.inputSchema,
                mcp_server_id=entry.id,
            )
            for t in listed
        ]
    return servers, decls, tool_decls


async def run(commission: Commission, sink: EventSink) -> None:
    prices = load_default_prices()
    origin = commission.model.split("/", 1)[0]
    rec = Recorder(sink, run_id=commission.run_id, provider=origin, prices=prices)
    await rec.prelude(commission, describe())
    if failure := cm.fail_fast(commission, AGENT_VERSION):
        await rec.error(*failure)
        await rec.stop(StopReason.error)
        return

    from agents import Agent, ModelSettings, RunConfig, Runner
    from agents.exceptions import ModelRefusalError

    plan = cm.from_commission(commission)
    # MCP tool calls that failed; the SDK's tool output item has no error flag.
    errored: set[str] = set()
    servers: list[Any] = []
    try:
        servers, mcp_decls, mcp_tool_decls = await _dial(commission, rec, errored)
        await rec.start(
            request_model=commission.model,
            prompt=plan.prompt,
            system_prompt=plan.instructions,
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
        config = RunConfig(tracing_disabled=True)
        if (provider := model_provider(plan)) is not None:
            config.model_provider = provider
        agent = Agent(
            name=cm.AGENT_NAME,
            instructions=plan.instructions,
            model=plan.sdk_model,
            mcp_servers=servers,
            output_type=cm.output_type(commission.output_schema)
            if commission.output_schema
            else None,
            model_settings=ModelSettings(include_usage=True),
        )
        # No turn cap from the adapter (the SDK defaults to 10): the supervisor
        # bounds the run.
        result = Runner.run_streamed(agent, plan.prompt, max_turns=None, run_config=config)
        started = time.monotonic()
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                kind = event.data.type
                if kind == "response.created":
                    started = time.monotonic()
                elif kind in ("response.completed", "response.incomplete"):
                    response = event.data.response
                    await rec.assistant(
                        translate.content(response.output),
                        translate.usage(response.usage),
                        model=response.model,
                        request_model=commission.model,
                        finish_reasons=translate.finish_reasons(response),
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
            elif event.type == "run_item_stream_event" and event.name == "tool_output":
                if (call_id := translate.call_id(event.item)) is not None:
                    await rec.tool_result(
                        call_id, translate.tool_output(event.item), is_error=call_id in errored
                    )
        await rec.stop(StopReason.converged, result.final_output)
    except ModelRefusalError as exc:
        await rec.stop(StopReason.refused, exc.refusal)
    except asyncio.CancelledError:
        await rec.stop(StopReason.interrupted)
        raise
    except Exception as exc:
        code = translate.error_code(exc)
        await rec.error(code, str(exc) or type(exc).__name__)
        await rec.stop(StopReason.error)
        if code is ErrorCode.agent_crash:
            raise
    finally:
        for server in servers:
            await server.cleanup()


def _failure_recorder(errored: set[str]) -> Any:
    def on_failure(ctx: Any, exc: Exception) -> str:
        if call_id := getattr(ctx, "tool_call_id", None):
            errored.add(call_id)
        return f"Error: {exc}"

    return on_failure
