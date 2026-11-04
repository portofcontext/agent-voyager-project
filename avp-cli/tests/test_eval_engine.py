"""Running an eval, with `dispatch` faked to write a saved Trajectory, so no
sandbox starts. test_agent.py runs `dispatch` in a real one."""

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest
from conftest import DESCRIPTOR, no_sandbox
from pydantic import JsonValue

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp_cli import paths
from avp_cli.agents import command, store
from avp_cli.console import Failed
from avp_cli.eval import engine, results
from avp_cli.eval.commission import load
from avp_cli.eval.config import EvalConfig
from avp_cli.eval.engine import run_eval
from avp_cli.eval.scoring import Result, Score
from avp_cli.runs.dispatch import Finished, Options
from avp_cli.sandbox import sandboxes

ANSWERS = {"paris": "Paris", "tokyo": "Kyoto", "lima": "Lima"}


def stopped(run_id: str, output: str) -> str:
    return json.dumps(
        {
            "avp_version": "0.1",
            "id": "1",
            "type": "agent_stopped",
            "time": "2026-01-01T00:00:00Z",
            "run_id": run_id,
            "data": {"reason": "converged", "output": output},
        }
    )


class Fake:
    """`dispatch`: answers from ANSWERS by the run's item, after `seconds`,
    counting how many run at once."""

    def __init__(self, seconds: float = 0, fail: set[str] | None = None) -> None:
        self.seconds = seconds
        self.fail = fail or set()
        self.running = 0
        self.most = 0
        self.options: list[Options] = []
        self.lock = threading.Lock()
        self.described: list[str] = []

    def __call__(
        self,
        agent: store.Agent,
        entrypoint: list[str],
        commission: Commission,
        options: Options | None = None,
    ) -> Finished:
        assert options is not None and options.directory is not None
        self.options.append(options)
        item = commission.run_id.rsplit("-", 1)[1]
        if item in self.fail:
            raise Failed("OpenSandbox couldn't start a sandbox")
        with self.lock:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(self.seconds)
        with self.lock:
            self.running -= 1
        options.directory.mkdir(parents=True)
        trajectory = options.directory / paths.TRAJECTORY
        trajectory.write_text(stopped(commission.run_id, ANSWERS[item]) + "\n")
        return Finished(options.directory, 0, "")


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Fake:
    fake = Fake()
    fake.described = no_sandbox(monkeypatch)
    monkeypatch.setattr(engine, "dispatch", fake)
    return fake


def config(tmp_path: Path, **change: JsonValue) -> EvalConfig:
    path = tmp_path / "capitals.eval.json"
    fields: dict[str, JsonValue] = {
        "eval_version": "0.1",
        "name": "capitals",
        "agents": ["pd", "my-agent"],
        "commission": {
            "avp_version": "0.1",
            "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
            "prompt": "Name the city in: {item.id}",
        },
        "dataset": [{"id": i, "answer": a} for i, a in [("paris", "Paris"), ("tokyo", "Tokyo")]],
        "scorer": {"name": "match", "expected": "{item.answer}"},
    }
    path.write_text(json.dumps({**fields, **change}))
    return EvalConfig.from_eval(load(path), tmp_path)


def test_every_run_is_run_and_scored_in_order(tmp_path: Path, fake: Fake) -> None:
    seen: list[str] = []
    results = asyncio.run(
        run_eval(config(tmp_path), tmp_path / "eval", progress=lambda r: seen.append(r.run.id))
    )
    assert [(r.run.agent, r.run.item.id, r.score) for r in results] == [
        ("pd", "paris", Score(value=1, passed=True)),
        ("pd", "tokyo", Score(value=0, passed=False, reasons=["expected 'Tokyo', got 'Kyoto'"])),
        ("my-agent", "paris", Score(value=1, passed=True)),
        (
            "my-agent",
            "tokyo",
            Score(value=0, passed=False, reasons=["expected 'Tokyo', got 'Kyoto'"]),
        ),
    ]
    assert seen == [r.run.id for r in results]
    assert [o.directory for o in fake.options] == [
        tmp_path / "eval" / paths.EVAL_RUNS / r.run.id for r in results
    ]
    assert results[0].run.output == "Paris"


def test_options_apply_to_every_run(tmp_path: Path, fake: Fake) -> None:
    options = Options(env={"KEY": "x"}, allow_hosts=["pypi.org"])
    asyncio.run(run_eval(config(tmp_path, agents="pd"), tmp_path / "eval", options))
    assert all(o.env == {"KEY": "x"} and o.allow_hosts == ["pypi.org"] for o in fake.options)


def run_timed(tmp_path: Path, fake: Fake, concurrency: int) -> list[Result]:
    fake.seconds = 0.2
    dataset: JsonValue = [{"id": i, "answer": a} for i, a in ANSWERS.items()]
    return asyncio.run(
        run_eval(
            config(tmp_path, agents="pd", dataset=dataset),
            tmp_path / "eval",
            concurrency=concurrency,
        )
    )


def test_runs_go_one_at_a_time_by_default(tmp_path: Path, fake: Fake) -> None:
    run_timed(tmp_path, fake, 1)
    assert fake.most == 1


def test_concurrency_runs_several_at_once(tmp_path: Path, fake: Fake) -> None:
    results = run_timed(tmp_path, fake, 3)
    assert fake.most == 3
    assert [r.run.item.id for r in results] == ["paris", "tokyo", "lima"]


def test_a_run_that_does_not_start_fails_with_0(tmp_path: Path, fake: Fake) -> None:
    fake.fail = {"tokyo"}
    results = asyncio.run(run_eval(config(tmp_path, agents="pd"), tmp_path / "eval"))
    assert results[0].score == Score(value=1, passed=True)
    assert results[1].score == Score(
        value=0,
        passed=False,
        reasons=["the run didn't start: OpenSandbox couldn't start a sandbox"],
    )
    assert results[1].error is None


def test_an_agent_that_is_not_installed_fails_before_any_run(
    tmp_path: Path, fake: Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(name: str) -> store.Agent:
        raise Failed(f"no agent named {name!r}")

    monkeypatch.setattr(store, "load", missing)
    with pytest.raises(Failed, match="no agent named 'pd'"):
        asyncio.run(run_eval(config(tmp_path), tmp_path / "eval"))
    assert fake.options == []


def test_concurrency_must_be_at_least_1(tmp_path: Path, fake: Fake) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        asyncio.run(run_eval(config(tmp_path), tmp_path / "eval", concurrency=0))


def test_cancelling_deletes_running_sandboxes_without_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C cancels the eval: avp deletes the sandboxes still running, and
    doesn't wait for the threads, which are daemons."""
    killed = threading.Event()
    started = threading.Event()

    def stuck(*args: object) -> Finished:
        started.set()
        killed.wait(5)
        time.sleep(5)  # A thread that never notices; avp must not wait for it.
        raise AssertionError("unreachable")

    no_sandbox(monkeypatch)
    monkeypatch.setattr(engine, "dispatch", stuck)
    monkeypatch.setattr(sandboxes, "kill_all", killed.set)

    async def interrupted() -> None:
        task = asyncio.create_task(run_eval(config(tmp_path, agents="pd"), tmp_path / "eval"))
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await task

    began = time.monotonic()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(interrupted())
    assert killed.is_set()
    assert time.monotonic() - began < 2


def test_each_agent_is_described_once_and_saved(tmp_path: Path, fake: Fake) -> None:
    found = asyncio.run(run_eval(config(tmp_path), tmp_path / "eval"))
    assert sorted(fake.described) == ["my-agent", "pd"]
    saved = results.agents(tmp_path / "eval")
    assert list(saved) == ["my-agent", "pd"]
    assert saved["pd"].image_id == "sha256:avp/pd"
    assert saved["pd"].descriptor == DESCRIPTOR
    assert all(r.run.model == "anthropic/claude-haiku-4-5" for r in found)
    assert all(r.run.seconds is not None for r in found)


def test_agents_are_described_at_the_same_time(
    tmp_path: Path, fake: Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    both = threading.Barrier(2, timeout=5)

    def describe(agent: store.Agent, entrypoint: list[str]) -> AgentDescriptor:
        both.wait()
        return DESCRIPTOR

    monkeypatch.setattr(command, "describe_in_sandbox", describe)
    found = asyncio.run(run_eval(config(tmp_path), tmp_path / "eval"))
    assert found


def test_a_failed_describe_deletes_the_other_sandboxes(
    tmp_path: Path, fake: Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    killed: list[bool] = []

    def describe(agent: store.Agent, entrypoint: list[str]) -> AgentDescriptor:
        raise Failed("`describe` didn't print a valid Agent Descriptor")

    monkeypatch.setattr(command, "describe_in_sandbox", describe)
    monkeypatch.setattr(sandboxes, "kill_all", lambda: killed.append(True))
    with pytest.raises(Failed, match="didn't print a valid"):
        asyncio.run(run_eval(config(tmp_path), tmp_path / "eval"))
    assert killed == [True]
    assert fake.options == []


def test_started_is_called_as_each_run_starts(tmp_path: Path, fake: Fake) -> None:
    seen: list[str] = []
    asyncio.run(
        run_eval(
            config(tmp_path, agents=["pd"]),
            tmp_path / "eval",
            None,
            1,
            lambda result: seen.append(f"scored {result.run.item.id}"),
            lambda case: seen.append(f"started {case.item.id}"),
        )
    )
    assert seen[:4] == ["started paris", "scored paris", "started tokyo", "scored tokyo"]
