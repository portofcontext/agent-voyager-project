"""Scoring a finished run: reading it from its directory, calling a scorer,
a scorer that fails, and the summary."""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import JsonValue, ValidationError

from avp.trajectory import AgentStoppedEvent
from avp_cli import paths
from avp_cli.eval.schemas import Item
from avp_cli.eval.scoring import (
    InvalidEvent,
    Run,
    Score,
    ScorerError,
    ScorerInput,
    call,
    read,
    score,
    summarize,
)

ITEM = Item(id="paris", answer="Paris")


def event(n: int, type: str, data: dict) -> dict:
    return {
        "avp_version": "0.1",
        "id": str(n),
        "type": type,
        "time": "2026-01-01T00:00:00Z",
        "run_id": "r",
        "data": data,
    }


STARTED = [
    event(1, "run_requested", {}),
    event(
        2,
        "agent_started",
        {"prompt": "Name the city", "model": {"provider": "anthropic", "id": "claude-haiku-4-5"}},
    ),
]
STOPPED = event(3, "agent_stopped", {"reason": "converged", "output": "Paris"})


def run_in(directory: Path, *lines: dict | str) -> Run:
    text = "\n".join(e if isinstance(e, str) else json.dumps(e) for e in lines)
    (directory / paths.TRAJECTORY).write_text(text + "\n")
    return read(directory, id="r", agent="pd", commission="inline-1", item=ITEM, exit_code=0)


def test_a_complete_run(tmp_path: Path) -> None:
    run = run_in(tmp_path, *STARTED, STOPPED)
    assert [e.type for e in run.trajectory] == ["run_requested", "agent_started", "agent_stopped"]
    assert isinstance(run.trajectory[-1], AgentStoppedEvent)
    assert run.output == "Paris"
    assert run.reason == "converged"
    assert run.invalid_trajectory == []


def test_an_incomplete_run_has_no_output_or_reason(tmp_path: Path) -> None:
    run = run_in(tmp_path, *STARTED)
    assert (run.output, run.reason) == (None, None)


def test_invalid_lines_are_listed_and_unknown_types_skipped(tmp_path: Path) -> None:
    unknown = event(3, "agent_daydreamed", {})
    broken = event(4, "agent_started", {})
    run = run_in(tmp_path, STARTED[0], "not json", unknown, broken, STOPPED)
    assert [e.type for e in run.trajectory] == ["run_requested", "agent_stopped"]
    [not_json, invalid] = run.invalid_trajectory
    assert not_json.line == 2
    assert not_json.error.startswith("isn't JSON")
    assert not_json.event == "not json"
    assert invalid.line == 4
    assert invalid.error.startswith("isn't a valid event: agent_started.data.prompt")
    assert invalid.event == broken


def test_a_missing_trajectory_is_empty(tmp_path: Path) -> None:
    run = read(tmp_path, id="r", agent="pd", commission="c", item=ITEM, exit_code=1)
    assert (run.trajectory, run.invalid_trajectory, run.reason) == ([], [], None)


def test_the_input_is_the_guides_json(tmp_path: Path) -> None:
    run = run_in(tmp_path, *STARTED, STOPPED)
    dumped = ScorerInput(run=run, config={"x": 1}).model_dump(mode="json")
    assert dumped["config"] == {"x": 1}
    assert set(dumped["run"]) == {
        "id",
        "agent",
        "commission",
        "exit_code",
        "trajectory",
        "invalid_trajectory",
        "output",
        "reason",
        "item",
    }
    assert dumped["run"]["item"] == {"id": "paris", "answer": "Paris"}
    assert dumped["run"]["trajectory"][2] == STOPPED
    # An event's absent fields stay absent.
    assert "meta" not in dumped["run"]["trajectory"][0]
    assert InvalidEvent(line=2, error="x", event=[1]).model_dump() == {
        "line": 2,
        "error": "x",
        "event": [1],
    }


def passing(input: ScorerInput) -> Score:
    return Score(value=1, passed=input.run.output == "Paris")


async def passing_later(input: ScorerInput) -> Score:
    await asyncio.sleep(0)
    return passing(input)


@pytest.mark.parametrize("scorer", [passing, passing_later])
def test_a_plain_or_async_scorer(tmp_path: Path, scorer) -> None:
    input = ScorerInput(run=run_in(tmp_path, *STARTED, STOPPED))
    assert asyncio.run(call(scorer, input)) == Score(value=1, passed=True)


@pytest.mark.parametrize("value", [-0.1, 1.5])
def test_a_score_outside_0_to_1_is_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        Score(value=value, passed=True)


def test_a_scorer_that_returns_something_else_failed(tmp_path: Path) -> None:
    input = ScorerInput(run=run_in(tmp_path, *STARTED, STOPPED))
    with pytest.raises(ScorerError, match="returned dict, not a Score"):
        asyncio.run(call(lambda _: {"value": 1, "passed": True}, input))  # ty: ignore[invalid-argument-type]


def broken(input: ScorerInput) -> Score:
    raise KeyError("words")


def test_a_scorer_that_raises_has_no_score_and_saves_its_traceback(tmp_path: Path) -> None:
    run = run_in(tmp_path, *STARTED, STOPPED)
    result = asyncio.run(score(broken, {}, run, tmp_path))
    assert result.score is None
    assert result.error is not None
    assert result.error.message == "KeyError: 'words'"
    saved = (tmp_path / paths.SCORER_ERROR).read_text()
    assert saved.startswith("KeyError: 'words'\n\nTraceback")
    assert "in broken" in saved


def test_the_config_is_filled_from_the_item_and_the_run(tmp_path: Path) -> None:
    seen: list[dict] = []

    def scorer(input: ScorerInput) -> Score:
        seen.append(input.config)
        return Score(value=1, passed=True)

    run = run_in(tmp_path, *STARTED, STOPPED)
    config: dict[str, JsonValue] = {
        "expected": "{item.answer}",
        "got": {"$run": "output"},
        "agent": "{run.agent}",
    }
    asyncio.run(score(scorer, config, run, tmp_path))
    assert seen == [{"expected": "Paris", "got": "Paris", "agent": "pd"}]


def test_a_placeholder_that_cannot_be_filled_fails_the_scorer(tmp_path: Path) -> None:
    run = run_in(tmp_path, *STARTED)
    result = asyncio.run(score(passing, {"city": "{run.output}"}, run, tmp_path))
    assert result.error is not None
    assert result.error.message == (
        'scorer.city: run.output isn\'t text; insert it whole with {"$run": "output"}'
    )
    assert (tmp_path / paths.SCORER_ERROR).exists()


def test_the_summary_leaves_scorer_failures_out() -> None:
    summary = summarize([Score(value=1, passed=True), Score(value=0.5, passed=False), None])
    assert summary.runs == 3
    assert summary.accuracy == 0.75
    assert summary.pass_rate == 0.5
    assert summary.scorer_failures == 1


def test_a_summary_with_no_scores() -> None:
    summary = summarize([])
    assert (summary.accuracy, summary.pass_rate) == (None, None)


def test_a_json_line_that_is_not_an_object_keeps_its_value(tmp_path: Path) -> None:
    [invalid] = run_in(tmp_path, "[1, 2]").invalid_trajectory
    assert (invalid.error, invalid.event) == ("isn't a JSON object", [1, 2])
