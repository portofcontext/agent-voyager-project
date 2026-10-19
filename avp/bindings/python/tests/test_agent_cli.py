"""Integration test for the stock agent command line: argv in, Commission through the
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


def test_workspace_includes_subprocesses_and_keeps_cli_paths(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    import pytest

    launch = tmp_path / "launch"
    workspace = tmp_path / "workspace"
    launch.mkdir()
    workspace.mkdir()
    monkeypatch.chdir(launch)
    monkeypatch.setenv("AVP_WORKSPACE", str(workspace))
    (launch / "c.json").write_text(
        json.dumps({"schema_version": "0.1", "run_id": "r", "model": "x/m"})
    )

    def inspect_workspace():
        child = subprocess.check_output(
            [sys.executable, "-c", "import os; print(os.getcwd())"], text=True
        ).strip()
        assert Path(child) == workspace
        assert Path.cwd() == workspace
        return DESCRIPTOR

    async def inspect_run(commission, sink):
        inspect_workspace()
        await run(commission, sink)
        raise RuntimeError("after recording")

    assert main(run=run, describe=inspect_workspace, argv=["describe", "--out", "d.json"]) == 0
    assert (launch / "d.json").exists()
    with pytest.raises(RuntimeError, match="after recording"):
        main(
            run=inspect_run,
            describe=describe,
            argv=["run", "--commission", "c.json", "--out", "t.jsonl"],
        )
    assert Path.cwd() == launch
    assert (launch / "t.jsonl").exists()
    assert not list(workspace.iterdir())
    assert os.environ["AVP_WORKSPACE"] == str(workspace)


_SLOW_AGENT = """
import asyncio
from avp.agent_cli import main
from avp.descriptor import AgentDescriptor
from avp.recorder import Recorder
from avp.trajectory import StopReason

DESCRIPTOR = AgentDescriptor(agent_name="slow", agent_version="0.0.1", spec_version="0.1")

async def run(commission, sink):
    rec = Recorder(sink, run_id=commission.run_id)
    await rec.prelude(commission, DESCRIPTOR)
    await rec.start(request_model=commission.model)
    try:
        await asyncio.sleep(60)
    except asyncio.CancelledError:
        await rec.stop(StopReason.interrupted)
        raise
    await rec.stop(StopReason.converged)

raise SystemExit(main(run=run, describe=lambda: DESCRIPTOR))
"""


def test_sigterm_closes_the_trajectory_as_interrupted(tmp_path: Path) -> None:
    import signal
    import subprocess
    import sys
    import time

    (tmp_path / "agent.py").write_text(_SLOW_AGENT)
    (tmp_path / "c.json").write_text(
        json.dumps({"schema_version": "0.1", "run_id": "r", "model": "x/m"})
    )
    out = tmp_path / "t.jsonl"
    proc = subprocess.Popen(
        [sys.executable, "agent.py", "run", "--commission", "c.json", "--out", str(out)],
        cwd=tmp_path,
    )
    deadline = time.monotonic() + 30
    while "avp.agent_started" not in (out.read_text() if out.exists() else ""):
        assert proc.poll() is None and time.monotonic() < deadline
        time.sleep(0.05)
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=30) == 130
    events = [json.loads(line) for line in out.read_text().splitlines()]
    assert events[-1]["type"] == "avp.agent_stopped"
    assert events[-1]["data"]["avp.reason"] == "interrupted"
