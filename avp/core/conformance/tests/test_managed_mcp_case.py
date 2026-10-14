"""Recorder → common MCP case: connecting alone cannot pass tool conformance."""

import asyncio
from copy import deepcopy
from importlib.resources import files

from avp_conformance._match import match_case
from avp_conformance.case import TestCase as Case

from avp.content import TextBlock, ToolUseBlock
from avp.descriptor import AgentDescriptor, McpServerDecl, ToolDecl
from avp.recorder import Recorder
from avp.trajectory import StopReason


def test_managed_mcp_case_requires_invocation_success_and_followup():
    case = Case.model_validate_json(
        files("avp_conformance")
        .joinpath("cases/v0.1/mcp/managed-mcp-tool-round-trip.json")
        .read_text()
    )
    assert not case.requires  # Applies even when the agent has no built-ins.
    events = []

    async def sink(event):
        events.append(event.model_dump(by_alias=True, exclude_none=True))

    async def drive():
        rec = Recorder(sink)
        await rec.prelude(
            case.commission,
            AgentDescriptor(agent_name="framework", agent_version="1", spec_version="0.1"),
        )
        await rec.start(
            tools=[ToolDecl(name="echo", mcp_server_id="avptest")],
            mcp_servers=[McpServerDecl(id="avptest", status="connected")],
        )
        await rec.assistant(
            [ToolUseBlock(id="call", name="echo", input={"text": "AVP-MCP-ROUNDTRIP"})]
        )
        await rec.tool_result("call", "AVP-MCP-ROUNDTRIP")
        await rec.assistant([TextBlock(text="AVP-MCP-ROUNDTRIP")])
        await rec.stop(StopReason.converged)

    asyncio.run(drive())
    assert match_case(events, case.expectations).ok
    connected_only = [
        e for e in events if e["type"] not in {"avp.tool_invoked", "avp.tool_returned"}
    ]
    assert not match_case(connected_only, case.expectations).ok
    for field, value in [("is_error", True), ("content", "wrong result")]:
        broken = deepcopy(events)
        result = next(e for e in broken if e["type"] == "avp.tool_returned")
        result["data"]["avp.tool_result"][field] = value
        assert not match_case(broken, case.expectations).ok
    no_followup = events[:-2] + events[-1:]
    assert not match_case(no_followup, case.expectations).ok
