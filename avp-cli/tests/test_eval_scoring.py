"""Scoring a finished run: reading it from its directory, calling a scorer,
a scorer that fails, and the summary."""

import asyncio
import json
from pathlib import Path

import pytest
from conftest import event
from pydantic import JsonValue, ValidationError

from avp.trajectory import AgentStoppedEvent
from avp_cli import paths
from avp_cli.eval.schemas import Item
from avp_cli.eval.scoring import (
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


def test_invalid_lines_and_unknown_types_are_listed(tmp_path: Path) -> None:
    unknown = event(3, "agent_daydreamed", {})
    broken = event(4, "agent_started", {})
    run = run_in(tmp_path, STARTED[0], "not json", unknown, broken, STOPPED)
    assert [e.type for e in run.trajectory] == ["run_requested", "agent_stopped"]
    assert run.invalid_trajectory == ["not json", unknown, broken]


def test_a_line_that_is_json_but_not_an_object_is_invalid(tmp_path: Path) -> None:
    run = run_in(tmp_path, "3", '"text"', STOPPED)
    assert run.invalid_trajectory == [3, "text"]


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
        "model",
        "seconds",
        "totals",
    }
    assert dumped["run"]["item"] == {"id": "paris", "answer": "Paris"}
    assert dumped["run"]["trajectory"][2] == STOPPED
    # An event's absent fields stay absent.
    assert "meta" not in dumped["run"]["trajectory"][0]


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


def message(n: int, cost: float, tokens: tuple[int, int]) -> dict:
    return event(
        n,
        "assistant_message",
        {
            "content": [{"type": "text", "text": "x"}],
            "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
            "duration_ms": 10,
            "usage": {
                "input_tokens": tokens[0],
                "output_tokens": tokens[1],
                "cost_usd": cost,
                "cost_source": "computed",
            },
        },
    )


def tool(n: int, name: str) -> dict:
    return event(n, "tool_invoked", {"tool_call_id": str(n), "tool_name": name, "tool_input": {}})


def test_totals_add_up_the_trajectory(tmp_path: Path) -> None:
    run = run_in(
        tmp_path,
        *STARTED,
        message(3, 0.01, (100, 20)),
        tool(4, "add"),
        tool(5, "add"),
        tool(6, "read"),
        message(7, 0.002, (150, 5)),
        STOPPED,
    )
    totals = run.totals
    assert (totals.turns, totals.input_tokens, totals.output_tokens) == (2, 250, 25)
    assert totals.cost_usd == pytest.approx(0.012)
    assert totals.tool_calls == {"add": 2, "read": 1}
    assert ScorerInput(run=run).model_dump(mode="json")["run"]["totals"]["turns"] == 2
