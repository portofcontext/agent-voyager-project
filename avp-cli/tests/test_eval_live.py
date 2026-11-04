"""`run_live`'s spinner, with the engine faked."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from rich.text import Text

from avp_cli.eval import live
from avp_cli.eval.config import EvalCase, EvalConfig
from avp_cli.eval.schemas import Item, JsonObject
from avp_cli.eval.scoring import Result, Run, Score
from avp_cli.runs.dispatch import Options

COMMISSION: JsonObject = {
    "avp_version": "0.1",
    "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
    "prompt": "x",
}


def test_the_spinner_shows_the_active_runs_dimmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[Text] = []

    class Status:
        def update(self, text: Text) -> None:
            shown.append(text)

    @contextmanager
    def status(text: Text) -> Generator[Status]:
        shown.append(text)
        yield Status()

    async def run_eval(
        config: EvalConfig,
        directory: Path,
        options: Options,
        concurrency: int,
        progress: Callable[[Result], None],
        started: Callable[[EvalCase], None],
    ) -> list[Result]:
        a, b = list(config)
        started(a)
        started(b)
        run = Run(
            id=a.built.run_id,
            agent=a.agent,
            commission=a.commission,
            exit_code=0,
            trajectory=[],
            invalid_trajectory=[],
            item=a.item,
        )
        result = Result(run, Score(value=1, passed=True))
        progress(result)
        return [result]

    monkeypatch.setattr(live.err, "status", status)
    monkeypatch.setattr(live, "run_eval", run_eval)
    config = EvalConfig(
        name="capitals",
        agents=["pd"],
        commissions={"c": COMMISSION},
        dataset=[Item(id="a"), Item(id="b")],
        scorer=lambda input: Score(value=1, passed=True),
    )
    live.run_live(config, tmp_path, Options(), 2, tmp_path)
    assert [t.plain for t in shown] == [
        "Running capitals - 0 of 2",
        "Running capitals - 0 of 2  c-pd-a",
        "Running capitals - 0 of 2  c-pd-a, c-pd-b",
        "Running capitals - 1 of 2  c-pd-b",
    ]
    assert [s.style for s in shown[-1].spans] == ["bold", "dim"]
