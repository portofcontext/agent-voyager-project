"""Observe Codex through the official SDK; Codex owns the model/tool loop."""

from __future__ import annotations

import asyncio
from importlib.metadata import version
from pathlib import Path

from openai_codex import CodexConfig
from openai_codex.async_client import AsyncCodexClient
from openai_codex.generated.v2_all import ListMcpServerStatusResponse, SkillsListResponse

from avp.commission import Commission
from avp.descriptor import AgentDescriptor, McpServerDecl, SkillDecl, ToolDecl
from avp.pricing import load_default_prices
from avp.recorder import Recorder
from avp.sink import EventSink
from avp.trajectory import ErrorCode, StopReason
from avp_codex import commission as cm
from avp_codex.translate import Responses, error_code, notification_params

AGENT_VERSION = version(cm.AGENT_NAME)


def describe() -> AgentDescriptor:
    return AgentDescriptor(
        agent_name=cm.AGENT_NAME,
        agent_version=AGENT_VERSION,
        spec_version="0.1",
        tools=cm.tool_decls(cm.BUILTIN_TOOLS),
    )


async def run(commission: Commission, sink: EventSink) -> None:
    rec = Recorder(sink, run_id=commission.run_id, provider="openai", prices=load_default_prices())
    await rec.prelude(commission, describe())
    if failure := cm.fail_fast(commission, AGENT_VERSION):
        await rec.error(*failure)
        await rec.stop(StopReason.error)
        return
    cwd = str(Path.cwd())
    output = None
    reason = StopReason.error
    try:
        config = CodexConfig(
            cwd=cwd,
            config_overrides=cm.config_overrides(commission),
            client_name="avp_codex",
            client_version=AGENT_VERSION,
        )
        # Use the SDK's typed lower-level client because its high-level
        # thread_start does not expose the required raw-item opt-in.
        async with AsyncCodexClient(config) as server:
            await server.initialize()
            # Codex discovers host and repository skills even with an empty
            # CODEX_HOME. Disable those and embed only commissioned skills.
            listed = await server.request(
                "skills/list",
                {"cwds": [cwd], "forceReload": True},
                response_model=SkillsListResponse,
            )
            disabled = [
                {"path": skill.path.root, "enabled": False}
                for entry in listed.data
                for skill in entry.skills
            ]
            params = {
                "model": commission.model.split("/", 1)[1],
                "modelProvider": "avp",
                "cwd": cwd,
                "approvalPolicy": "never",
                "experimentalRawEvents": True,
                "config": {"skills.config": disabled},
                "allowProviderModelFallback": False,
            }
            if not cm.uses_environment(commission):
                # No native environment also hides model-selected apply_patch.
                params["environments"] = []
            if commission.system_prompt is not None:
                params["baseInstructions"] = commission.system_prompt
            if instructions := cm.skill_instructions(commission):
                params["developerInstructions"] = instructions
            started = await server.thread_start(params)
            if started.approval_policy.model_dump(mode="json") != "never":
                raise RuntimeError("Codex did not honor the noninteractive approval policy")
            if started.thread.cli_version != cm.CODEX_VERSION:
                raise RuntimeError(
                    f"avp-codex requires codex-cli {cm.CODEX_VERSION}; raw events are experimental"
                )
            thread = started.thread.id
            tools = cm.tool_decls(cm.selected_tools(commission), commission.model.split("/", 1)[1])
            declarations = []
            cursor = None
            statuses = {}
            startup_deadline = asyncio.get_running_loop().time() + 30
            while True:
                catalog = await server.request(
                    "mcpServerStatus/list",
                    {
                        "threadId": thread,
                        "cursor": cursor,
                    },
                    response_model=ListMcpServerStatusResponse,
                )
                catalog = catalog.model_dump(mode="json", by_alias=True, exclude_none=True)
                statuses.update((entry["name"], entry) for entry in catalog["data"])
                cursor = catalog.get("nextCursor")
                if not cursor:
                    starting = any(
                        statuses.get(entry.id, {}).get("runtimeStatus")
                        in (None, "notStarted", "starting")
                        for entry in commission.mcp_servers or []
                    )
                    if starting and asyncio.get_running_loop().time() < startup_deadline:
                        # Status/list is a snapshot, not a startup barrier.
                        # Do not publish a failed/empty catalog while the SDK
                        # is still connecting commissioned servers.
                        statuses = {}
                        await asyncio.sleep(0.1)
                        continue
                    break
            for entry in commission.mcp_servers or []:
                status = statuses.get(entry.id, {})
                connected = status.get("runtimeStatus") == "connected" and not status.get(
                    "toolsError"
                )
                declarations.append(
                    McpServerDecl(id=entry.id, status="connected" if connected else "failed")
                )
                if not connected:
                    await rec.error(
                        ErrorCode.mcp_connect_failed,
                        f"{entry.id}: MCP startup or tool listing failed",
                    )
                    continue
                for native in status["tools"].values():
                    tools.append(
                        ToolDecl(
                            name=f"mcp__{entry.id}.{native['name']}",
                            description=native.get("description"),
                            inputSchema=native["inputSchema"],
                            mcp_server_id=entry.id,
                        )
                    )
            await rec.start(
                request_model=commission.model,
                prompt=commission.prompt or "",
                system_prompt=commission.system_prompt,
                tools=tools,
                mcp_servers=declarations or None,
                skills=[
                    SkillDecl(name=s.name or s.id, description=s.description)
                    for s in commission.skills or []
                ]
                or None,
                thread_id=commission.thread_id,
                tags=commission.tags,
            )
            turn_params = {
                "threadId": thread,
                "input": [{"type": "text", "text": commission.prompt or ""}],
            }
            if commission.output_schema is not None:
                turn_params["outputSchema"] = commission.output_schema
            turn = await server.turn_start(thread, turn_params["input"], params=turn_params)
            turn_id = turn.turn.id
            responses = Responses(rec, commission.model)
            terminal_error = False
            try:
                while True:
                    message = await server.next_turn_notification(turn_id)
                    method, data = message.method, notification_params(message)
                    if data.get("threadId") != thread or data.get("turnId", turn_id) != turn_id:
                        continue
                    await responses.accept(method, data)
                    if method == "error" and not data.get("willRetry", False):
                        terminal_error = True
                        await rec.error(error_code(data["error"]), data["error"]["message"])
                    if method == "turn/completed":
                        status = data["turn"]["status"]
                        if status == "completed" and not terminal_error:
                            responses.finish()
                            output = responses.output
                            if commission.output_schema:
                                import json

                                output = json.loads(output)
                            reason = (
                                StopReason.refused if responses.refused else StopReason.converged
                            )
                        elif status == "interrupted":
                            reason = StopReason.interrupted
                        else:
                            if not terminal_error:
                                error = data["turn"].get("error") or {
                                    "message": "Codex turn failed"
                                }
                                await rec.error(error_code(error), error["message"])
                            reason = StopReason.error
                        break
            finally:
                server.unregister_turn_notifications(turn_id)
        await rec.stop(reason, output)
    except asyncio.CancelledError:
        await rec.stop(StopReason.interrupted)
        raise
    except Exception as exc:
        await rec.error(ErrorCode.agent_crash, str(exc) or type(exc).__name__)
        await rec.stop(StopReason.error)
        raise
