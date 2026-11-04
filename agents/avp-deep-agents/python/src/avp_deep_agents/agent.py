"""The native Deep Agents graph runs the Commission and reports its callbacks."""

import asyncio
from contextlib import AsyncExitStack

from langchain_core.messages import HumanMessage
from langchain_core.tools import ToolException
from langchain_mcp_adapters.sessions import create_session
from langchain_mcp_adapters.tools import load_mcp_tools
from langsmith import tracing_context
from mcp.shared.exceptions import McpError
from pydantic import JsonValue

from avp.agent_cli import EventSink
from avp.recorder import Recorder
from avp.utils.run_plan import plan_run
from avp_deep_agents import commission as cm
from avp_deep_agents import translate
from avp_deep_agents.callbacks import RecorderCallbacks
from avp_deep_agents.descriptor import declaration, describe, graph_tools


def model(commission):
    """The native model boundary used by the graph and scripted tests."""
    return cm.model(commission)


def recover_protocol_errors(tool):
    original = tool.coroutine

    async def invoke(*args, **kwargs):
        try:
            return await original(*args, **kwargs)
        except McpError as exc:
            raise ToolException(str(exc)) from exc

    tool.coroutine = invoke
    tool.handle_tool_error = True


async def run(received: JsonValue, sink: EventSink) -> None:
    descriptor = describe()
    rec = Recorder(sink)
    commission = await rec.begin(received, descriptor)
    if commission is None:
        return
    if commission.model.provider not in cm.PROVIDERS:
        await rec.error(
            "invalid_commission", f"{cm.AGENT_NAME} cannot call {commission.model.provider!r}"
        )
        return
    plan = plan_run(commission, descriptor)
    try:
        try:
            native = model(commission)
        except cm.MissingSecret as exc:
            await rec.error("auth_error", str(exc))
            return
        async with AsyncExitStack() as stack:
            tools = []
            owners = {}
            for server in commission.mcp_servers or []:
                try:
                    session = await stack.enter_async_context(create_session(cm.connection(server)))
                    await session.initialize()
                    listed = await load_mcp_tools(
                        session, server_name=server.id, tool_name_prefix=True
                    )
                except cm.MissingSecret as exc:
                    await rec.error("auth_error", str(exc))
                    return
                except Exception as exc:
                    await rec.error("mcp_connect_failed", f"{server.id}: {exc}")
                    return
                for tool in listed:
                    recover_protocol_errors(tool)
                    owners[tool.name] = server.id
                    tools.append(tool)
            hidden = set(plan.turned_off.tools)
            if not plan.started.subagents:
                hidden.add("task")
            instructions = cm.instructions(commission)
            graph = cm.build(
                native,
                cm.backend(),
                tools=tools,
                hidden=hidden,
                instructions=instructions,
                replace_prompt=commission.system_prompt is not None,
                response_schema=commission.output_schema,
            )
            offered = graph_tools(graph)
            unknown = set(offered) - {t.name for t in descriptor.tools or []} - set(owners)
            if unknown:
                await rec.error(
                    "invalid_commission",
                    f"unsupported native model-profile tools: {', '.join(sorted(unknown))}",
                )
                return
            declarations = [
                declaration(t, owners.get(t.name)) for t in offered.values() if t.name not in hidden
            ]
            servers = [
                s.model_copy(update={"status": "connected"}) for s in plan.started.mcp_servers or []
            ]
            managed = [declaration(t, owners[t.name]) for t in tools]
            subagents = [
                s.model_copy(
                    update={"tools": list(s.tools or []) + managed, "mcp_servers": servers or None}
                )
                for s in plan.started.subagents or []
            ]
            await rec.start(
                plan.started.model_copy(
                    update={
                        "system_prompt": instructions,
                        "tools": declarations or None,
                        "mcp_servers": servers or None,
                        "subagents": subagents or None,
                    }
                )
            )
            events = RecorderCallbacks(rec, commission.model, {s.name for s in subagents})
            with tracing_context(enabled=False):
                result = await graph.ainvoke(
                    {"messages": [HumanMessage(content=commission.prompt)]}, {"callbacks": [events]}
                )
            await events.settle(result.get("messages", []))
            events.finish()
            reason = "refused" if None in events.refused else "converged"
            output = (
                result["structured_response"]
                if commission.output_schema is not None
                else result["messages"][-1].text
            )
            if commission.output_schema is not None and reason == "converged":
                from jsonschema import Draft202012Validator, ValidationError

                try:
                    Draft202012Validator(commission.output_schema).validate(output)
                except ValidationError as exc:
                    await rec.error("output_invalid", str(exc))
                    reason = "error"
        await rec.stop(reason, output)
    except asyncio.CancelledError:
        await rec.stop("interrupted")
        raise
    except Exception as exc:
        code = translate.error_code(exc)
        await rec.error(code, str(exc) or type(exc).__name__)
        await rec.stop("error")
        if code == "agent_crash":
            raise
