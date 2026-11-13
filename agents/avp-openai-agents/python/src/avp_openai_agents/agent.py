"""The native Runner owns the loop; each completed response goes to the Recorder."""

import asyncio
import time
from contextlib import AsyncExitStack
from typing import Any

from agents import Agent, FunctionTool, ModelSettings, RunConfig, RunContextWrapper, Runner
from agents.exceptions import ModelRefusalError
from agents.items import ToolCallOutputItem
from agents.tool import get_function_tool_origin
from openai.types.responses import ResponseCompletedEvent, ResponseIncompleteEvent
from pydantic import JsonValue

from avp.agent_cli import TrajectorySink
from avp.descriptor import Tool
from avp.recorder import Recorder
from avp.utils.run_plan import plan_run
from avp_openai_agents import commission as cm
from avp_openai_agents import translate
from avp_openai_agents.descriptor import AGENT_NAME, describe


def model(commission):
    """The native model for the run. Tests replace only this boundary."""
    return cm.model(commission)


async def run(received: JsonValue, sink: TrajectorySink) -> None:
    descriptor = describe()
    rec = Recorder(sink)
    commission = await rec.begin(received, descriptor)
    if commission is None:
        return
    if commission.model.provider not in {p.provider for p in descriptor.supported_models or []}:
        await rec.error(
            "invalid_commission", f"{AGENT_NAME} cannot call {commission.model.provider!r}"
        )
        return
    plan = plan_run(commission, descriptor)
    reports = {}
    try:
        try:
            native = model(commission)
        except cm.MissingSecret as exc:
            await rec.error("auth_error", str(exc))
            return
        async with AsyncExitStack() as stack:
            servers = []
            for entry in commission.mcp_servers or []:
                try:
                    server = cm.mcp_server(entry, reports)
                    await stack.enter_async_context(server)
                except cm.MissingSecret as exc:
                    await rec.error("auth_error", str(exc))
                    return
                except Exception as exc:
                    await rec.error("mcp_connect_failed", f"{entry.id}: {exc}")
                    return
                servers.append(server)
            instructions = cm.instructions(commission)
            agent = Agent(
                name=AGENT_NAME,
                model=native,
                instructions=instructions,
                mcp_servers=servers,
                model_settings=ModelSettings(include_usage=True),
                output_type=cm.output_type(commission.output_schema),
            )
            try:
                tools = await agent.get_all_tools(RunContextWrapper(context=None))
            except Exception as exc:
                await rec.error("mcp_connect_failed", str(exc))
                return
            declarations = []
            for tool in tools:
                if not isinstance(tool, FunctionTool):
                    raise ValueError(f"unexpected native tool {type(tool).__name__}")
                origin = get_function_tool_origin(tool)
                declarations.append(
                    Tool(
                        name=tool.name,
                        description=tool.description,
                        inputSchema=tool.params_json_schema,
                        mcp_server_id=origin.mcp_server_name if origin else None,
                    )
                )
            await rec.start(
                plan.started.model_copy(
                    update={
                        "system_prompt": instructions,
                        "tools": declarations or None,
                        "mcp_servers": [
                            s.model_copy(update={"status": "connected"})
                            for s in plan.started.mcp_servers or []
                        ]
                        or None,
                    }
                )
            )
            run = Runner.run_streamed(
                agent,
                commission.prompt,
                max_turns=None,
                run_config=RunConfig(tracing_disabled=True),
            )
            started = time.monotonic()
            refused = False
            async for event in run.stream_events():
                if event.type == "raw_response_event":
                    kind = event.data.type
                    if kind == "response.created":
                        started = time.monotonic()
                    elif isinstance(event.data, (ResponseCompletedEvent, ResponseIncompleteEvent)):
                        response = event.data.response
                        blocks = translate.content(response.output)
                        refused |= any(b.type == "refusal" for b in blocks)
                        incomplete = response.incomplete_details
                        await rec.response(
                            blocks,
                            usage=translate.usage(response.usage),
                            response_model=response.model
                            if response.model != commission.model.id
                            else None,
                            finish_reasons=[incomplete.reason]
                            if incomplete and incomplete.reason
                            else [response.status]
                            if response.status
                            else None,
                            duration_ms=int((time.monotonic() - started) * 1000),
                        )
                elif event.type == "run_item_stream_event" and isinstance(
                    event.item, ToolCallOutputItem
                ):
                    item = event.item
                    raw: Any = item.raw_item
                    await rec.tool_returned(
                        raw["call_id"],
                        translate.tool_output(raw["output"]),
                        **reports.pop(raw["call_id"], {}),
                    )
            output = run.final_output
            reason = "refused" if refused else "converged"
        await rec.stop(reason, output)
    except ModelRefusalError as exc:
        await rec.stop("refused", exc.refusal)
    except cm.OutputInvalid as exc:
        await rec.error("output_invalid", str(exc))
        await rec.stop("error")
    except asyncio.CancelledError:
        await rec.stop("interrupted")
        raise
    except Exception as exc:
        code = translate.error_code(exc)
        await rec.error(code, str(exc) or type(exc).__name__)
        await rec.stop("error")
        if code == "agent_crash":
            raise
