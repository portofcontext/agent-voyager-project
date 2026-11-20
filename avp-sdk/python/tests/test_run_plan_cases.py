"""The shared run plan cases in `avp-sdk/testdata/run_plan/`, which every SDK
passes. Each case gives a Commission and a Descriptor and expects the plan."""

import json
from pathlib import Path
from typing import Any

import pytest

from avp.commission import Commission
from avp.descriptor import AgentDescriptor, Tool
from avp.utils.preflight import check_commission
from avp.utils.run_plan import plan_run

CASES = Path(__file__).resolve().parents[2] / "testdata" / "run_plan"


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    commission = Commission.model_validate(case["commission"])
    descriptor = AgentDescriptor.model_validate(case["descriptor"])
    assert check_commission(commission, descriptor) is None, "the case's Commission is refused"
    return plan_run(commission, descriptor).model_dump(
        mode="json", exclude_none=True, by_alias=True
    )


@pytest.mark.parametrize("path", sorted(CASES.glob("*.json")), ids=lambda path: path.stem)
def test_case(path: Path) -> None:
    case = json.loads(path.read_text())
    assert run_case(case) == case["plan"]


def test_connected_adds_server_tools_and_statuses() -> None:
    commission = Commission.model_validate(
        {
            "avp_version": "0.1",
            "run_id": "r1",
            "model": {"provider": "anthropic", "id": "m"},
            "prompt": "hi",
            "mcp_servers": [
                {"id": "a", "type": "stdio", "command": ["a"]},
                {"id": "b", "type": "stdio", "command": ["b"]},
            ],
        }
    )
    descriptor = AgentDescriptor(avp_version="0.1", agent_name="x", agent_version="1")
    tool = Tool.model_validate(
        {"name": "add", "inputSchema": {"type": "object"}, "mcp_server_id": "a"}
    )
    agent = plan_run(commission, descriptor).connected([tool], {"b": "failed"})
    assert agent.tool_definitions == [
        {"type": "function", "function": {"name": "add", "parameters": {"type": "object"}}}
    ]
    avp = agent.extra.avp if agent.extra else None
    assert avp is not None and avp.tools and avp.mcp_servers
    assert avp.tools["add"].mcp_server_id == "a"
    assert [(s.id, s.status) for s in avp.mcp_servers] == [("a", "connected"), ("b", "failed")]
