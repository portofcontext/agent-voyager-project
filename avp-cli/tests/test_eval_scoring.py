"""Scoring a finished run: reading it from its directory, calling a scorer,
a scorer that fails, and the summary."""

import asyncio
import json
from pathlib import Path

import pytest
from conftest import atif
from pydantic import JsonValue, ValidationError

from avp.trajectory import Trajectory
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


def run_in(directory: Path, document=None) -> Run:
    document = atif() if document is None else document
    (directory / paths.TRAJECTORY).write_text(
        document if isinstance(document, str) else json.dumps(document)
    )
    return read(directory, id="r", agent="pd", commission="inline-1", item=ITEM, exit_code=0)


def test_a_complete_run(tmp_path):
    run = run_in(tmp_path)
    assert isinstance(run.trajectory, Trajectory)
    assert run.trajectory.schema_version == "ATIF-v1.8"
    assert run.output == "Paris"
    assert run.reason == "converged"
    assert run.invalid_trajectory == []


def test_an_incomplete_run_has_no_output_or_reason(tmp_path):
    run = run_in(tmp_path, atif(complete=False))
    assert (run.output, run.reason) == (None, None)


@pytest.mark.parametrize("document", ["not json", "3", '"text"', {"steps": []}])
def test_invalid_documents_are_listed(tmp_path, document):
    run = run_in(tmp_path, document)
    assert run.trajectory is None
    assert run.invalid_trajectory


def test_a_missing_trajectory_is_empty(tmp_path):
    run = read(tmp_path, id="r", agent="pd", commission="c", item=ITEM, exit_code=1)
    assert (run.trajectory, run.invalid_trajectory, run.reason) == (None, [], None)


def test_external_atif_without_avp_extensions(tmp_path):
    document = atif()
    del document["extra"]
    run = run_in(tmp_path, document)
    assert run.output == "Paris"
    assert run.reason is None


def test_the_input_is_the_guides_json(tmp_path):
    dumped = ScorerInput(run=run_in(tmp_path), config={"x": 1}).model_dump(mode="json")
    assert dumped["config"] == {"x": 1}
    assert dumped["run"]["item"] == {"id": "paris", "answer": "Paris"}
    assert dumped["run"]["trajectory"]["steps"][-1]["message"] == "Paris"


def passing(input: ScorerInput) -> Score:
    return Score(value=1, passed=input.run.output == "Paris")


async def passing_later(input: ScorerInput) -> Score:
    await asyncio.sleep(0)
    return passing(input)


@pytest.mark.parametrize("scorer", [passing, passing_later])
def test_a_plain_or_async_scorer(tmp_path: Path, scorer) -> None:
    input = ScorerInput(run=run_in(tmp_path))
    assert asyncio.run(call(scorer, input)) == Score(value=1, passed=True)


@pytest.mark.parametrize("value", [-0.1, 1.5])
def test_a_score_outside_0_to_1_is_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        Score(value=value, passed=True)


def test_a_scorer_that_returns_something_else_failed(tmp_path: Path) -> None:
    input = ScorerInput(run=run_in(tmp_path))
    with pytest.raises(ScorerError, match="returned dict, not a Score"):
        asyncio.run(call(lambda _: {"value": 1, "passed": True}, input))  # ty: ignore[invalid-argument-type]


def broken(input: ScorerInput) -> Score:
    raise KeyError("words")


def test_a_scorer_that_raises_has_no_score_and_saves_its_traceback(tmp_path: Path) -> None:
    run = run_in(tmp_path)
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

    run = run_in(tmp_path)
    config: dict[str, JsonValue] = {
        "expected": "{item.answer}",
        "got": {"$run": "output"},
        "agent": "{run.agent}",
    }
    asyncio.run(score(scorer, config, run, tmp_path))
    assert seen == [{"expected": "Paris", "got": "Paris", "agent": "pd"}]


def test_a_placeholder_that_cannot_be_filled_fails_the_scorer(tmp_path: Path) -> None:
    run = run_in(tmp_path, atif(complete=False))
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


def test_totals_add_up_the_trajectory(tmp_path):
    steps = [
        {"step_id": 1, "source": "user", "message": "x"},
        {
            "step_id": 2,
            "source": "agent",
            "message": "",
            "metrics": {"prompt_tokens": 100, "completion_tokens": 20, "cost_usd": 0.01},
            "tool_calls": [
                {"tool_call_id": str(n), "function_name": name, "arguments": {}}
                for n, name in enumerate(["add", "add", "read"])
            ],
        },
        {
            "step_id": 3,
            "source": "agent",
            "message": "Paris",
            "metrics": {"prompt_tokens": 150, "completion_tokens": 5, "cost_usd": 0.002},
        },
    ]
    run = run_in(tmp_path, atif(steps=steps))
    totals = run.totals
    assert (totals.turns, totals.input_tokens, totals.output_tokens) == (2, 250, 25)
    assert totals.cost_usd == pytest.approx(0.012)
    assert totals.tool_calls == {"add": 2, "read": 1}
    assert ScorerInput(run=run).model_dump(mode="json")["run"]["totals"]["turns"] == 2


def test_unknown_external_usage_is_not_reported_as_measured_zero(tmp_path):
    run = run_in(tmp_path, atif())
    assert set(run.totals.unknown_metrics) == {"input_tokens", "output_tokens", "cost_usd"}


def test_incomplete_avp_response_is_not_final_output(tmp_path):
    doc = atif(complete=False)
    doc["steps"].append({"step_id": 2, "source": "agent", "message": "still thinking"})
    assert run_in(tmp_path, doc).output is None


def test_external_multimodal_output_and_unknown_extensions(tmp_path):
    doc = atif()
    doc["extra"] = {"avp": {"stop_reason": "future-reason"}, "other": {"version": 3}}
    doc["steps"][-1]["message"] = [
        {"type": "image", "source": {"media_type": "image/png", "path": "image.png"}}
    ]
    run = run_in(tmp_path, doc)
    assert run.output == doc["steps"][-1]["message"]
    assert run.reason is None
