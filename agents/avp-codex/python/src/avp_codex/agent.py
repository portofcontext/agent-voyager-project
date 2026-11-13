"""The run: Codex's app-server events in, Recorder calls out."""

import asyncio
import json
from importlib.metadata import version
from pathlib import Path
from typing import Any

from openai_codex import CodexConfig
from openai_codex.async_client import AsyncCodexClient
from openai_codex.generated.v2_all import ListMcpServerStatusResponse, SkillsListResponse
from pydantic import JsonValue

from avp.agent_cli import TrajectorySink
from avp.commission import Commission
from avp.descriptor import Tool
from avp.recorder import Recorder
from avp.reports import StopReason
from avp.utils.run_plan import plan_run
from avp_codex import commission as cm
from avp_codex import descriptor, translate

CODEX_VERSION = version("openai-codex")


async def mcp_tools(server: AsyncCodexClient, thread: str, commission: Commission) -> list[Tool]:
    """Wait for the Commission's native MCP clients and list their tools."""
    if not commission.mcp_servers:
        return []
    deadline = asyncio.get_running_loop().time() + 30
    while True:
        statuses = {}
        cursor = None
        while True:
            response = await server.request(
                "mcpServerStatus/list",
                {"threadId": thread, "cursor": cursor},
                response_model=ListMcpServerStatusResponse,
            )
            page = response.model_dump(mode="json", by_alias=True, exclude_none=True)
            statuses.update((entry["name"], entry) for entry in page["data"])
            cursor = page.get("nextCursor")
            if not cursor:
                break
        pending = any(
            statuses.get(entry.id, {}).get("runtimeStatus") in (None, "notStarted", "starting")
            for entry in commission.mcp_servers
        )
        if not pending or asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(0.1)
    result = []
    for entry in commission.mcp_servers:
        status = statuses.get(entry.id, {})
        if status.get("runtimeStatus") != "connected" or status.get("toolsError"):
            raise ConnectionError(f"{entry.id}: MCP startup or tool listing failed")
        for native in status["tools"].values():
            result.append(
                Tool.model_validate(
                    {
                        **native,
                        "name": f"mcp__{entry.id}.{native['name']}",
                        "mcp_server_id": entry.id,
                    }
                )
            )
    return result


async def run(received: JsonValue, sink: TrajectorySink) -> None:
    declared = descriptor.describe()
    rec = Recorder(sink)
    commission = await rec.begin(received, declared)
    if commission is None:
        return
    plan = plan_run(commission, declared)
    if refusal := cm.refusal(commission, plan):
        await rec.error("invalid_commission", refusal)
        return
    cwd = str(Path.cwd())
    reason: StopReason = "error"
    output = None
    try:
        try:
            overrides, env = cm.configuration(commission, plan)
        except cm.MissingSecret as exc:
            await rec.error("auth_error", str(exc))
            return
        config = CodexConfig(
            cwd=cwd,
            config_overrides=overrides,
            env=env,
            client_name="avp_codex",
            client_version=declared.agent_version,
        )
        async with AsyncCodexClient(config) as server:
            await server.initialize()
            skills = await server.request(
                "skills/list",
                {"cwds": [cwd], "forceReload": True},
                response_model=SkillsListResponse,
            )
            disabled = [
                {"path": skill.path.root, "enabled": False}
                for entry in skills.data
                for skill in entry.skills
            ]
            params: dict[str, Any] = {
                "model": commission.model.id,
                "modelProvider": "avp",
                "cwd": cwd,
                "approvalPolicy": "never",
                "experimentalRawEvents": True,
                "config": {"skills.config": disabled},
                "allowProviderModelFallback": False,
            }
            names = [tool.name for tool in plan.started.tools or []]
            if not set(names) & descriptor.ENVIRONMENT_TOOLS:
                params["environments"] = []
            if commission.system_prompt is not None:
                params["baseInstructions"] = commission.system_prompt
            if instructions := cm.skill_instructions(commission):
                params["developerInstructions"] = instructions
            started = await server.thread_start(params)
            if started.approval_policy.model_dump(mode="json") != "never":
                raise RuntimeError("Codex did not honor the noninteractive approval policy")
            if started.thread.cli_version != CODEX_VERSION:
                raise RuntimeError(
                    f"avp-codex requires codex-cli {CODEX_VERSION}; raw events are experimental"
                )
            thread = started.thread.id
            try:
                managed = await mcp_tools(server, thread, commission)
            except ConnectionError as exc:
                await rec.error("mcp_connect_failed", str(exc))
                return
            # These helpers appear only when MCP is configured; patch is model-dependent.
            if not commission.mcp_servers:
                names = [
                    name
                    for name in names
                    if name not in descriptor.RESOURCE_TOOLS | {"tool_search"}
                ]
            elif commission.model.id == "gpt-5-mini":
                names = [name for name in names if name != "tool_search"]
            if commission.model.id == "gpt-5-mini":
                names = [name for name in names if name != "apply_patch"]
            tools = descriptor.tools(names, commission.model.id) + managed
            servers = [
                entry.model_copy(update={"status": "connected"})
                for entry in plan.started.mcp_servers or []
            ]
            await rec.start(
                plan.started.model_copy(
                    update={"tools": tools or None, "mcp_servers": servers or None}
                )
            )
            turn_params: dict[str, Any] = {
                "threadId": thread,
                "input": [{"type": "text", "text": commission.prompt}],
            }
            if commission.output_schema is not None:
                turn_params["outputSchema"] = commission.output_schema
            turn = await server.turn_start(thread, commission.prompt, params=turn_params)
            responses = translate.Responses(rec, commission.model.id, plan.turned_off.tools)
            terminal_error = False
            try:
                while True:
                    notification = await server.next_turn_notification(turn.turn.id)
                    method = notification.method
                    data = translate.notification_params(notification)
                    if (
                        data.get("threadId") != thread
                        or data.get("turnId", turn.turn.id) != turn.turn.id
                    ):
                        continue
                    await responses.accept(method, data)
                    if method == "error" and not data.get("willRetry", False):
                        terminal_error = True
                        await rec.error(
                            translate.error_code(data["error"]), data["error"]["message"]
                        )
                    if method != "turn/completed":
                        continue
                    status = data["turn"]["status"]
                    if status == "completed" and not terminal_error:
                        responses.finish()
                        reason = "refused" if responses.refused else "converged"
                        output = responses.output
                        if commission.output_schema is not None and reason == "converged":
                            from jsonschema import Draft202012Validator, ValidationError

                            try:
                                output = json.loads(output)
                                Draft202012Validator(commission.output_schema).validate(output)
                            except (json.JSONDecodeError, ValidationError) as exc:
                                await rec.error("output_invalid", str(exc))
                                reason = "error"
                    elif status == "interrupted":
                        reason = "interrupted"
                    else:
                        if not terminal_error:
                            error = data["turn"].get("error") or {"message": "Codex turn failed"}
                            await rec.error(translate.error_code(error), error["message"])
                        reason = "error"
                    break
            finally:
                server.unregister_turn_notifications(turn.turn.id)
        await rec.stop(reason, output)
    except asyncio.CancelledError:
        await rec.stop("interrupted")
        raise
    except Exception as exc:
        await rec.error("agent_crash", str(exc) or type(exc).__name__)
        await rec.stop("error")
        raise
