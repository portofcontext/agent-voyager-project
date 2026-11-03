"""`avp eval run`, `show`, and `list`, with `dispatch` faked to write a saved
Trajectory, so no sandbox starts."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avp.commission import Commission
from avp_cli import console
from avp_cli.agents import store
from avp_cli.cli import app
from avp_cli.engine import images
from avp_cli.eval import engine
from avp_cli.runs import directory
from avp_cli.runs.dispatch import Finished, Options

ANSWERS = {"paris": "Paris", "tokyo": "Kyoto"}


def fake_dispatch(
    agent: store.Agent, entrypoint: list[str], commission: Commission, options: Options
) -> Finished:
    assert options.directory is not None
    item = commission.run_id.rsplit("-", 1)[1]
    options.directory.mkdir(parents=True)
    event = {
        "avp_version": "0.1",
        "id": "1",
        "type": "agent_stopped",
        "time": "2026-01-01T00:00:00Z",
        "run_id": commission.run_id,
        "data": {"reason": "converged", "output": ANSWERS[item]},
    }
    (options.directory / directory.TRAJECTORY).write_text(json.dumps(event) + "\n")
    return Finished(options.directory, 0, "")


@pytest.fixture(autouse=True)
def no_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No sandbox, a scratch AVP home, and a wide terminal so tables don't wrap."""
    monkeypatch.setenv("AVP_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(console.out, "width", 200)
    monkeypatch.setattr(engine, "dispatch", fake_dispatch)
    monkeypatch.setattr(store, "load", lambda name: store.Agent(name=name, image=f"avp/{name}"))
    monkeypatch.setattr(images, "entrypoint", lambda image: ["/agent"])


def eval_file(tmp_path: Path, **change: object) -> Path:
    path = tmp_path / "capitals.eval.json"
    fields = {
        "eval_version": "0.1",
        "name": "capitals",
        "agents": "pd",
        "commission": {
            "avp_version": "0.1",
            "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
            "prompt": "Name the city in: {item.id}",
        },
        "dataset": [{"id": "paris", "answer": "Paris"}, {"id": "tokyo", "answer": "Tokyo"}],
        "scorer": {"name": "match", "expected": "{item.answer}"},
    }
    path.write_text(json.dumps({**fields, **change}))
    return path


def avp(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(app, list(args))
    return result.exit_code, result.output


def test_run_prints_the_scoreboard_and_saves_results(tmp_path: Path) -> None:
    code, output = avp("eval", "run", str(eval_file(tmp_path)))
    assert code == 0, output
    assert "inline-1" in output
    assert "50%" in output
    assert "expected 'Tokyo', got 'Kyoto'" in output
    [eval_directory] = (tmp_path / "home" / "evals").iterdir()
    assert eval_directory.name.endswith("-capitals")
    saved = json.loads((eval_directory / "results.json").read_text())
    assert saved["finished"] is not None
    assert [(r["item"], r["score"]["passed"]) for r in saved["runs"]] == [
        ("paris", True),
        ("tokyo", False),
    ]
    assert (eval_directory / "eval.json").read_text() == eval_file(tmp_path).read_text()
    assert (eval_directory / "runs" / "inline-1-pd-paris" / "trajectory.ndjson").is_file()


def test_run_json(tmp_path: Path) -> None:
    code, output = avp("eval", "run", str(eval_file(tmp_path)), "--json")
    assert code == 0, output
    assert json.loads(output)["name"] == "capitals"


def test_threshold_exits_1_below_it(tmp_path: Path) -> None:
    assert avp("eval", "run", str(eval_file(tmp_path)), "--threshold", "0.5")[0] == 0
    assert avp("eval", "run", str(eval_file(tmp_path)), "--threshold", "0.6")[0] == 1


def test_max_items(tmp_path: Path) -> None:
    avp("eval", "run", str(eval_file(tmp_path)), "--max-items", "1", "--json")
    [eval_directory] = (tmp_path / "home" / "evals").iterdir()
    saved = json.loads((eval_directory / "results.json").read_text())
    assert [r["item"] for r in saved["runs"]] == ["paris"]


def test_problems_are_listed_with_the_agent_hint(tmp_path: Path) -> None:
    path = eval_file(tmp_path, agents=None, scorer={"name": "match", "expected": "{item.city}"})
    result = CliRunner().invoke(app, ["eval", "run", str(path)])
    assert result.exit_code == 1
    assert isinstance(result.exception, Exception)
    message = str(result.exception)
    assert "no agents: the eval names none, and none were given; give --agent" in message
    assert "item paris, scorer.expected: item has no field 'city'" in message
    assert not (tmp_path / "home" / "evals").exists()


def test_a_missing_variable_fails_before_any_run(tmp_path: Path) -> None:
    commission = {
        "avp_version": "0.1",
        "model": {"provider": "anthropic", "id": "claude-haiku-4-5", "credential": {"env": "KEY"}},
        "prompt": "x",
    }
    result = CliRunner().invoke(
        app, ["eval", "run", str(eval_file(tmp_path, commission=commission))]
    )
    assert result.exit_code == 1
    assert "KEY" in str(result.exception)
    assert not (tmp_path / "home" / "evals").exists()


def test_show_and_list(tmp_path: Path) -> None:
    avp("eval", "run", str(eval_file(tmp_path)))
    [eval_directory] = (tmp_path / "home" / "evals").iterdir()
    code, shown = avp("eval", "show")
    assert code == 0, shown
    assert eval_directory.name in shown
    assert "expected 'Tokyo', got 'Kyoto'" in shown
    assert json.loads(avp("eval", "show", eval_directory.name, "--json")[1])["id"] == (
        eval_directory.name
    )
    assert json.loads(avp("eval", "show", "--agent", "other", "--json")[1])["runs"] == []
    code, listed = avp("eval", "list")
    assert code == 0
    assert eval_directory.name in listed


def test_show_without_evals() -> None:
    result = CliRunner().invoke(app, ["eval", "show"])
    assert result.exit_code == 1
    assert "no evals have run yet" in str(result.exception)


@pytest.mark.parametrize("flag", [["--model", "openai/gpt-5-mini"], ["--resume", "x"]])
def test_unbuilt_options_say_so(tmp_path: Path, flag: list[str]) -> None:
    result = CliRunner().invoke(app, ["eval", "run", str(eval_file(tmp_path)), *flag])
    assert "isn't built yet" in str(result.exception)
