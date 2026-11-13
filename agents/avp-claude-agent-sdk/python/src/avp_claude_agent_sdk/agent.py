"""The Claude SDK owns the loop; its native events become a Trajectory."""

import asyncio
import re

from claude_agent_sdk import ClaudeSDKClient, ResultMessage, SystemMessage
from pydantic import JsonValue

from avp.agent_cli import TrajectorySink
from avp.descriptor import Tool
from avp.recorder import Recorder
from avp.utils.run_plan import plan_run
from avp_claude_agent_sdk import commission as cm
from avp_claude_agent_sdk.descriptor import CLAUDE_VERSION, describe
from avp_claude_agent_sdk.translate import Responses, error_code


async def run(received: JsonValue, sink: TrajectorySink) -> None:
    descriptor = describe()
    rec = Recorder(sink)
    commission = await rec.begin(received, descriptor)
    if commission is None:
        return
    plan = plan_run(commission, descriptor)
    if commission.model.provider != "anthropic":
        await rec.error(
            "invalid_commission", "Claude Code runs Anthropic models through the Anthropic API"
        )
        return
    try:
        try:
            options = cm.options(commission, plan)
        except cm.MissingSecret as exc:
            await rec.error("auth_error", str(exc))
            return
        result = None
        responses = None
        async with ClaudeSDKClient(options) as client:
            await client.query(commission.prompt)
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    if message.data["claude_code_version"] != CLAUDE_VERSION:
                        raise RuntimeError(
                            f"Claude Code {CLAUDE_VERSION} is required for the captured profile"
                        )
                    statuses = (await client.get_mcp_status())["mcpServers"]
                    by_name = {s["name"]: s for s in statuses}
                    managed = []
                    servers = []
                    for server in plan.started.mcp_servers or []:
                        status = by_name.get(server.id, {})
                        if status.get("status") != "connected":
                            await rec.error(
                                "mcp_connect_failed", f"{server.id}: MCP startup failed"
                            )
                            return
                        servers.append(server.model_copy(update={"status": "connected"}))
                        for native in status.get("tools", []):
                            prefix = re.sub(r"[^A-Za-z0-9_]", "_", server.id)
                            managed.append(
                                Tool.model_validate(
                                    {
                                        **native,
                                        "name": f"mcp__{prefix}__{native['name']}",
                                        "mcp_server_id": server.id,
                                        "inputSchema": native.get(
                                            "inputSchema",
                                            native.get("input_schema", {"type": "object"}),
                                        ),
                                    }
                                )
                            )
                    tools = list(plan.started.tools or []) + managed
                    await rec.start(
                        plan.started.model_copy(
                            update={"tools": tools or None, "mcp_servers": servers or None}
                        )
                    )
                    responses = Responses(rec, commission.model.id, {t.name for t in tools})
                elif isinstance(message, ResultMessage):
                    result = message
                elif responses is not None:
                    await responses.accept(message)
            if result is None or responses is None:
                raise ValueError("Claude ended without a run result")
            output = (
                result.structured_output if commission.output_schema is not None else result.result
            )
            if result.is_error or responses.error:
                if not responses.error:
                    await rec.error(
                        error_code(result.api_error_status),
                        "\n".join(result.errors or [result.result or "Claude run failed"]),
                    )
                reason = "error"
            else:
                responses.finish()
                reason = "refused" if responses.refused else "converged"
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
        await rec.error("agent_crash", str(exc) or type(exc).__name__)
        await rec.stop("error")
        raise
