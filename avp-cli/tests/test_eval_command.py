"""The `command` scorer: scripts in a temporary directory, run with this
Python, read the input from stdin and print a score."""

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest
from pydantic import JsonValue

from avp_cli import paths
from avp_cli.eval.commission import EvalError, load
from avp_cli.eval.config import EvalConfig
from avp_cli.eval.schemas import Item
from avp_cli.eval.scoring import Result, Run, Score, score

WORDS = """
import json, sys
data = json.load(sys.stdin)
run, config = data["run"], data["config"]
missing = [w for w in run["item"]["words"] if w.lower() not in run["output"].lower()]
reasons = [f"missing {w!r}" for w in missing]
if len((run["trajectory"] or {}).get("steps", [])) > config["max_steps"]:
    reasons.append("too many steps")
value = 1 - len(missing) / len(run["item"]["words"])
json.dump({"value": value, "passed": not reasons, "reasons": reasons}, sys.stdout)
"""


def run_with(output: JsonValue, words: list[str] | None = None) -> Run:
    return Run(
        id="r",
        agent="pd",
        commission="inline-1",
        exit_code=0,
        trajectory=None,
        invalid_trajectory=[],
        output=output,
        reason="converged",
        item=Item(id="paris", words=words or ["Paris", "France"]),
    )


def script(directory: Path, body: str, name: str = "score.py") -> Path:
    path = directory / name
    path.write_text(body)
    return path


def scored(directory: Path, fields: dict[str, JsonValue], run: Run) -> Result:
    eval = {
        "eval_version": "0.1",
        "name": "capitals",
        "agents": "pd",
        "commission": {
            "avp_version": "0.1",
            "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
            "prompt": "x",
        },
        "dataset": [run.item.model_dump(mode="json")],
        "scorer": {"name": "command", **fields},
    }
    path = directory / "capitals.eval.json"
    path.write_text(json.dumps(eval))
    config = EvalConfig.from_eval(load(path), directory)
    return asyncio.run(score(config.scorer, config.scorer_config, run, directory))


def test_a_passing_and_a_failing_run(tmp_path: Path) -> None:
    script(tmp_path, WORDS)
    fields: dict[str, JsonValue] = {
        "command": [sys.executable, "score.py"],
        "config": {"max_steps": 3},
    }
    assert scored(tmp_path, fields, run_with("Paris, France")).score == Score(value=1, passed=True)
    assert scored(tmp_path, fields, run_with("Paris")).score == Score(
        value=0.5, passed=False, reasons=["missing 'France'"]
    )


def test_placeholders_fill_the_command_and_its_config(tmp_path: Path) -> None:
    script(
        tmp_path,
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        "ok = sys.argv[1] == 'paris' and data['config'] == {'answer': 'Paris', 'words': ['a']}\n"
        "json.dump({'value': 1, 'passed': ok}, sys.stdout)\n",
    )
    fields: dict[str, JsonValue] = {
        "command": [sys.executable, "score.py", "{item.id}"],
        "config": {"answer": "{run.output}", "words": {"$item": "words"}},
    }
    assert scored(tmp_path, fields, run_with("Paris", ["a"])).score == Score(value=1, passed=True)


def test_a_relative_program_runs_from_the_eval_files_directory(tmp_path: Path) -> None:
    program = script(
        tmp_path,
        f'#!{sys.executable}\nimport sys\nsys.stdout.write(\'{{"value": 1, "passed": true}}\')\n',
        "scorer",
    )
    program.chmod(0o755)
    result = scored(tmp_path, {"command": ["./scorer"]}, run_with("x"))
    assert result.score == Score(value=1, passed=True)


def test_runs_are_scored_at_once(tmp_path: Path) -> None:
    script(
        tmp_path,
        "import json, sys, time\njson.load(sys.stdin)\ntime.sleep(0.5)\n"
        "json.dump({'value': 1, 'passed': True}, sys.stdout)\n",
    )
    path = tmp_path / "capitals.eval.json"
    scored(tmp_path, {"command": [sys.executable, "score.py"]}, run_with("x"))
    config = EvalConfig.from_eval(load(path), tmp_path)

    async def all_at_once() -> list[Result]:
        runs = [run_with("x") for _ in range(4)]
        return await asyncio.gather(
            *(score(config.scorer, config.scorer_config, r, None) for r in runs)
        )

    started = time.monotonic()
    results = asyncio.run(all_at_once())
    assert all(r.score == Score(value=1, passed=True) for r in results)
    assert time.monotonic() - started < 1.5


@pytest.mark.parametrize(
    ("body", "message", "detail"),
    [
        (
            "import sys\nsys.stderr.write('reading\\nKeyError: words\\n')\nsys.exit(3)\n",
            "score.py exited with 3: KeyError: words",
            "reading\nKeyError: words",
        ),
        (
            "print('done')\n",
            "score.py printed something other than a score: Invalid JSON: expected value",
            "stdout:\ndone",
        ),
        (
            'print(\'{"value": 2, "passed": true}\')\n',
            "score.py printed something other than a score: value: Input should be less than"
            " or equal to 1",
            "stdout:",
        ),
    ],
)
def test_a_command_that_fails(tmp_path: Path, body: str, message: str, detail: str) -> None:
    script(tmp_path, body)
    result = scored(tmp_path, {"command": [sys.executable, "score.py"]}, run_with("x"))
    assert result.score is None
    assert result.error is not None
    assert message in result.error.message
    assert result.error.message.startswith(sys.executable)
    saved = (tmp_path / paths.SCORER_ERROR).read_text()
    assert detail in saved


def test_a_command_that_is_not_found(tmp_path: Path) -> None:
    result = scored(tmp_path, {"command": ["./missing"]}, run_with("x"))
    assert result.error is not None
    assert result.error.message == "can't run ./missing: No such file or directory"


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        (
            {"command": []},
            "scorer.command: List should have at least 1 item after validation, not 0",
        ),
        ({}, "scorer.command: Field required"),
        ({"command": "python score.py"}, "scorer.command: Input should be a valid list"),
        ({"command": ["x"], "config": "{}"}, "scorer.config: Input should be a valid dictionary"),
    ],
)
def test_the_commands_fields_are_checked(tmp_path: Path, fields: dict, problem: str) -> None:
    with pytest.raises(EvalError) as error:
        scored(tmp_path, fields, run_with("x"))
    assert problem in error.value.problems
