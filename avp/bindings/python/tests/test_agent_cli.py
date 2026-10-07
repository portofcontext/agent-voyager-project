"""Seam test for the stock agent command line: argv in, Commission through the
agent's `run`, NDJSON trajectory out (and `ping` / `describe`)."""

from __future__ import annotations

import json
from pathlib import Path

from avp.agent_cli import main
from avp.commission import Commission
from avp.content import TextBlock
from avp.descriptor import AgentDescriptor
from avp.recorder import Recorder
from avp.sink import EventSink
from avp.trajectory import StopReason, Usage

DESCRIPTOR = AgentDescriptor(agent_name="echo", agent_version="0.0.1", spec_version="0.1")


def describe() -> AgentDescriptor:
    return DESCRIPTOR


async def run(commission: Commission, sink: EventSink) -> None:
    """A one-turn agent that echoes its prompt and system prompt."""
    rec = Recorder(sink, run_id=commission.run_id)
    await rec.prelude(commission, DESCRIPTOR)
    await rec.start(request_model=commission.model, prompt=commission.prompt)
    text = f"{commission.system_prompt}|{commission.prompt}"
    await rec.assistant([TextBlock(text=text)], Usage(input_tokens=3, output_tokens=1))
    await rec.stop(StopReason.converged, text)


def test_ping_writes_pong(tmp_path: Path) -> None:
    out = tmp_path / "pong.json"
    assert main(run=run, describe=describe, argv=["ping", "--out", str(out)]) == 0
    assert json.loads(out.read_text()) == {"type": "pong"}


def test_describe_writes_descriptor(tmp_path: Path) -> None:
    out = tmp_path / "d.json"
    assert main(run=run, describe=describe, argv=["describe", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["agent_name"] == "echo"


async def _adescribe() -> AgentDescriptor:
    return DESCRIPTOR


def test_describe_accepts_async(capsys) -> None:
    assert main(run=run, describe=_adescribe, argv=["describe"]) == 0
    assert json.loads(capsys.readouterr().out)["agent_name"] == "echo"


def test_run_streams_trajectory_and_seeds_built_ins(tmp_path: Path) -> None:
    commission = tmp_path / "c.json"
    commission.write_text(
        json.dumps({"schema_version": "0.1", "run_id": "r1", "model": "x/m", "prompt": "hi"})
    )
    built_in = json.dumps({"system_prompt": "be brief", "prompt": "ignored: commission wins"})
    out = tmp_path / "t.jsonl"
    argv = ["run", "--commission", str(commission), "--built-in", built_in, "--out", str(out)]
    assert main(run=run, describe=describe, argv=argv) == 0
    events = [json.loads(line) for line in out.read_text().splitlines()]
    assert [e["type"] for e in events] == [
        "avp.run_requested",
        "avp.agent_described",
        "avp.agent_started",
        "avp.assistant_message",
        "avp.agent_stopped",
    ]
    assert events[-1]["data"]["avp.output"] == "be brief|hi"
    assert all(e["subject"] == "r1" for e in events)
