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

from avp.agent_cli import TrajectorySink
from avp.recorder import Recorder
from avp.trajectory import tool_definitions
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


async def run(received: JsonValue, sink: TrajectorySink) -> None:
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
    connecting = None
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
                connecting = server.id
                session = await stack.enter_async_context(create_session(cm.connection(server)))
                await session.initialize()
                listed = await load_mcp_tools(session, server_name=server.id, tool_name_prefix=True)
                connecting = None
                for tool in listed:
                    recover_protocol_errors(tool)
                    owners[tool.name] = server.id
                    tools.append(tool)
            hidden = set(plan.turned_off.tools)
            agent = plan.connected([])
            assert agent.extra is not None and agent.extra.avp is not None
            extra = agent.extra.avp
            if not extra.subagents:
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
            servers = extra.mcp_servers
            managed = [declaration(t, owners[t.name]) for t in tools]
            subagents = [
                s.model_copy(
                    update={"tools": list(s.tools or []) + managed, "mcp_servers": servers or None}
                )
                for s in extra.subagents or []
            ]
            definitions, details = tool_definitions(declarations)
            agent.tool_definitions = definitions or None
            extra.tools = details or None
            extra.subagents = subagents or None
            await rec.start(agent, plan.prompt, system_prompt=instructions)
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
    except cm.MissingSecret as exc:
        await rec.error("auth_error", str(exc))
        await rec.stop("error")
    except Exception as exc:
        code = "mcp_connect_failed" if connecting else translate.error_code(exc)
        message = f"{connecting}: {exc}" if connecting else str(exc) or type(exc).__name__
        await rec.error(code, message)
        await rec.stop("error")
        if code == "agent_crash":
            raise
