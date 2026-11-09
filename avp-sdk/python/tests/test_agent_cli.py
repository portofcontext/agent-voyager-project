import asyncio
import json
import os
import signal

from pydantic import JsonValue

from avp.agent_cli import TrajectorySink, main
from avp.descriptor import AgentDescriptor
from avp.recorder import Recorder
from avp.reports import RunContext
from avp.trajectory import avp_metadata, parse_trajectory

DESCRIPTOR = AgentDescriptor(avp_version="0.1", agent_name="demo", agent_version="1.0.0")
COMMISSION = {
    "avp_version": "0.1",
    "run_id": "run-1",
    "model": {"provider": "anthropic", "id": "claude-sonnet-4-5"},
    "prompt": "Go.",
}


async def run(received: JsonValue, sink: TrajectorySink) -> None:
    rec = Recorder(sink)
    commission = await rec.begin(received, DESCRIPTOR)
    if commission is None:
        return
    await rec.start(RunContext(prompt=commission.prompt, model=commission.model))
    await rec.stop("converged")


def trajectory(path):
    return parse_trajectory(path.read_text())


def cli(*argv: str) -> int:
    return main(run=run, describe=lambda: DESCRIPTOR, argv=list(argv))


def test_ping_never_calls_the_agent(tmp_path, capsys):
    def describe():
        raise AssertionError("ping must not load the agent")

    assert main(run=run, describe=describe, argv=["ping", "--out", str(tmp_path / "p")]) == 0
    assert json.loads((tmp_path / "p").read_text()) == {"type": "pong", "avp_version": "0.1"}
    assert main(run=run, describe=describe, argv=["ping"]) == 0
    assert json.loads(capsys.readouterr().out) == {"type": "pong", "avp_version": "0.1"}


def test_describe(tmp_path, capsys):
    assert cli("describe", "--out", str(tmp_path / "d.json")) == 0
    assert AgentDescriptor.model_validate_json((tmp_path / "d.json").read_text()) == DESCRIPTOR
    assert cli("describe") == 0
    assert json.loads(capsys.readouterr().out)["agent_name"] == "demo"


def test_run_writes_the_agents_trajectory(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(COMMISSION))
    out = tmp_path / "trajectory.json"
    assert cli("run", "--commission", str(path), "--out", str(out)) == 0
    assert avp_metadata(trajectory(out))["stop_reason"] == "converged"
    assert trajectory(out).session_id == "run-1"


def test_run_accepts_inline_json_and_stdout(capsys):
    assert cli("run", "--commission", json.dumps(COMMISSION), "--out", "-") == 0
    assert avp_metadata(parse_trajectory(capsys.readouterr().out))["complete"]


def test_invalid_text_is_refused_without_archiving_the_input(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("not json")
    out = tmp_path / "trajectory.json"
    assert cli("run", "--commission", str(path), "--out", str(out)) == 0
    assert avp_metadata(trajectory(out))["stop_reason"] == "error"
    assert avp_metadata(trajectory(out).steps[0])["error_code"] == "invalid_commission"


def test_sigterm_cancels_the_run_and_exits_130(tmp_path):
    out = tmp_path / "trajectory.json"
    cancelled = []

    async def slow(received: JsonValue, sink: TrajectorySink) -> None:
        asyncio.get_running_loop().call_later(0.05, os.kill, os.getpid(), signal.SIGTERM)
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    code = main(
        run=slow,
        describe=lambda: DESCRIPTOR,
        argv=["run", "--commission", json.dumps(COMMISSION), "--out", str(out)],
    )
    assert code == 130 and cancelled == [True]
