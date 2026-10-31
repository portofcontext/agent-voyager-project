import asyncio
import json
import os
import signal

from pydantic import JsonValue

from avp.agent_cli import EventSink, main
from avp.descriptor import AgentDescriptor
from avp.recorder import Recorder
from avp.trajectory import AgentStarted, parse_trajectory_event

DESCRIPTOR = AgentDescriptor(avp_version="0.1", agent_name="demo", agent_version="1.0.0")
COMMISSION = {
    "avp_version": "0.1",
    "run_id": "run-1",
    "model": {"provider": "anthropic", "id": "claude-sonnet-4-5"},
    "prompt": "Go.",
}


async def run(received: JsonValue, sink: EventSink) -> None:
    rec = Recorder(sink)
    commission = await rec.begin(received, DESCRIPTOR)
    if commission is None:
        return
    await rec.start(AgentStarted(prompt=commission.prompt, model=commission.model))
    await rec.stop("converged")


def trajectory(path) -> list:
    return [parse_trajectory_event(line) for line in path.read_text().splitlines()]


def types(path) -> list[str]:
    return [event.type for event in trajectory(path)]


def cli(*argv: str) -> int:
    return main(run=run, describe=lambda: DESCRIPTOR, argv=list(argv))


def test_ping_never_calls_the_agent(tmp_path, capsys):
    def describe():
        raise AssertionError("ping must not load the agent")

    assert main(run=run, describe=describe, argv=["ping", "--out", str(tmp_path / "p")]) == 0
    assert json.loads((tmp_path / "p").read_text()) == {"type": "pong"}
    assert main(run=run, describe=describe, argv=["ping"]) == 0
    assert json.loads(capsys.readouterr().out) == {"type": "pong"}


def test_describe(tmp_path, capsys):
    assert cli("describe", "--out", str(tmp_path / "d.json")) == 0
    assert AgentDescriptor.model_validate_json((tmp_path / "d.json").read_text()) == DESCRIPTOR
    assert cli("describe") == 0
    assert json.loads(capsys.readouterr().out)["agent_name"] == "demo"


def test_run_writes_the_agents_trajectory(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(COMMISSION))
    out = tmp_path / "t.ndjson"
    assert cli("run", "--commission", str(path), "--out", str(out)) == 0
    assert types(out) == ["run_requested", "agent_described", "agent_started", "agent_stopped"]
    assert trajectory(out)[0].run_id == "run-1"


def test_run_accepts_inline_json_and_stdout(capsys):
    assert cli("run", "--commission", json.dumps(COMMISSION), "--out", "-") == 0
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["type"] for line in lines][-1] == "agent_stopped"


def test_text_that_isnt_json_is_recorded_as_received(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("not json")
    out = tmp_path / "t.ndjson"
    assert cli("run", "--commission", str(path), "--out", str(out)) == 0
    assert trajectory(out)[0].data.commission == "not json"
    assert types(out)[-1] == "error_occurred"


def test_sigterm_cancels_the_run_and_exits_130(tmp_path):
    out = tmp_path / "t.ndjson"
    cancelled = []

    async def slow(received: JsonValue, sink: EventSink) -> None:
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
