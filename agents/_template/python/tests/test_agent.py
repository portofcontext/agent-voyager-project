"""Seam test: the agent's command line drives a run end to end and the
trajectory parses as AVP. Keep this test when you replace the harness; point
it at a recorded or stubbed SDK stream."""

from __future__ import annotations

import json
from pathlib import Path

from avp_agent_template.agent import describe, run

from avp.agent_cli import main
from avp.trajectory import parse_event


def _run(tmp_path: Path, commission: dict) -> list[dict]:
    out = tmp_path / "t.jsonl"
    argv = ["run", "--commission", json.dumps(commission), "--out", str(out)]
    assert main(run=run, describe=describe, argv=argv) == 0
    events = [json.loads(line) for line in out.read_text().splitlines()]
    for event in events:
        parse_event(event)
    return events


def test_tool_round_trip(tmp_path: Path) -> None:
    events = _run(
        tmp_path,
        {
            "schema_version": "0.1",
            "run_id": "r1",
            "model": "openai/gpt-4o-mini",
            "prompt": "use a tool",
        },
    )
    assert [e["type"] for e in events] == [
        "avp.run_requested",
        "avp.agent_described",
        "avp.agent_started",
        "avp.assistant_message",
        "avp.tool_invoked",
        "avp.tool_returned",
        "avp.assistant_message",
        "avp.agent_stopped",
    ]
    assert events[3]["data"]["avp.cost.source"] == "computed"
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_empty_allowlist_hides_the_tool(tmp_path: Path) -> None:
    events = _run(
        tmp_path,
        {
            "schema_version": "0.1",
            "run_id": "r2",
            "model": "openai/gpt-4o-mini",
            "prompt": "use a tool",
            "enabled_builtin_tools": {"avp-agent-template": []},
        },
    )
    assert "avp.tool_invoked" not in [e["type"] for e in events]
    assert events[2]["data"]["avp.tools"] == []


def test_unknown_allowlisted_tool_fails_fast(tmp_path: Path) -> None:
    events = _run(
        tmp_path,
        {
            "schema_version": "0.1",
            "run_id": "r3",
            "model": "openai/gpt-4o-mini",
            "enabled_builtin_tools": {"avp-agent-template": ["nope"]},
        },
    )
    assert [e["type"] for e in events][-2:] == ["avp.error_occurred", "avp.agent_stopped"]
    assert events[-2]["data"]["avp.error.code"] == "commission_collision"
    assert "avp.agent_started" not in [e["type"] for e in events]
