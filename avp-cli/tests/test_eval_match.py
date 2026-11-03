"""The `match` scorer, from a run's output to its score, and an eval file
scored end to end from a saved run."""

import asyncio
import json
import re
from pathlib import Path

import pytest
from pydantic import JsonValue, ValidationError

from avp.trajectory import StopReason
from avp_cli import paths
from avp_cli.eval.commission import load
from avp_cli.eval.config import EvalConfig
from avp_cli.eval.schemas import Item
from avp_cli.eval.scorers.match import Match
from avp_cli.eval.scoring import Run, Score, read, score


def run_with(output: JsonValue, reason: StopReason | None = "converged") -> Run:
    return Run(
        id="r",
        agent="pd",
        commission="inline-1",
        exit_code=0,
        trajectory=[],
        invalid_trajectory=[],
        output=output,
        reason=reason,
        item=Item(id="paris"),
    )


PASSED = Score(value=1, passed=True)


def failed(reason: str, value: float = 0) -> Score:
    return Score(value=value, passed=False, reasons=[reason])


@pytest.mark.parametrize(
    ("fields", "output", "result"),
    [
        ({"expected": "Paris"}, "Paris", PASSED),
        ({"expected": "Paris"}, "  paris\n", PASSED),
        ({"expected": "PARIS"}, "Paris", PASSED),
        (
            {"expected": "Paris", "case_sensitive": True},
            "paris",
            failed("expected 'Paris', got 'paris'"),
        ),
        ({"expected": "Paris"}, "Lyon", failed("expected 'Paris', got 'Lyon'")),
        ({"expected": "Paris"}, "Paris, France", failed("expected 'Paris', got 'Paris, France'")),
        ({"expected": "1"}, 1, failed("output isn't a string (reason: converged)")),
        (
            {"expected": '{"city": "Paris"}'},
            {"city": "Paris"},
            failed("output isn't a string (reason: converged)"),
        ),
        # levenshtein: the similarity is the value.
        (
            {"expected": "Paris", "mode": "levenshtein", "threshold": 0.8},
            "Pariss",
            Score(value=5 / 6, passed=True),
        ),
        ({"expected": "Paris", "mode": "levenshtein", "threshold": 0.8}, " PARIS ", PASSED),
        (
            {"expected": "Paris", "mode": "levenshtein", "threshold": 0.9},
            "Pariss",
            failed("expected 'Paris', got 'Pariss': similarity 0.83, below 0.9", 5 / 6),
        ),
        (
            {"expected": "Paris", "mode": "levenshtein", "threshold": 0.5, "case_sensitive": True},
            "PARIS",
            failed("expected 'Paris', got 'PARIS': similarity 0.20, below 0.5", 1 - 4 / 5),
        ),
        # regex: found anywhere unless anchored.
        ({"expected": r"\bparis\b", "mode": "regex"}, "It is Paris, France.", PASSED),
        (
            {"expected": "^Paris$", "mode": "regex"},
            "Paris, France",
            failed("no match for '^Paris$' in 'Paris, France'"),
        ),
        (
            {"expected": "Paris", "mode": "regex", "case_sensitive": True},
            "paris",
            failed("no match for 'Paris' in 'paris'"),
        ),
        (
            {"expected": "Paris", "mode": "regex"},
            None,
            failed("output isn't a string (reason: converged)"),
        ),
    ],
)
def test_match(fields: dict, output: JsonValue, result: Score) -> None:
    assert Match.model_validate(fields).score(run_with(output)) == result


def test_match_without_agent_stopped() -> None:
    result = Match(expected="Paris").score(run_with(None, None))
    assert result == failed("output isn't a string (no agent_stopped)")


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({"expected": {"city": "Paris"}}, "valid string"),
        (
            {"expected": "Paris", "mode": "levenshtein"},
            "threshold is required with mode levenshtein",
        ),
        (
            {"expected": "Paris", "threshold": 0.8},
            "threshold only applies to mode levenshtein, not exact",
        ),
        ({"expected": "Paris", "mode": "regex", "threshold": 0.8}, "not regex"),
        ({"expected": "Paris", "mode": "levenshtein", "threshold": 1.5}, "less than or equal to 1"),
        ({"expected": "(", "mode": "regex"}, "expected isn't a valid regular expression"),
        ({"expected": "Paris", "mode": "fuzzy"}, "'exact', 'levenshtein' or 'regex'"),
    ],
)
def test_match_fields_for_each_mode(fields: dict, error: str) -> None:
    with pytest.raises(ValidationError, match=re.escape(error)):
        Match.model_validate(fields)


def stopped(output: JsonValue) -> str:
    return json.dumps(
        {
            "avp_version": "0.1",
            "id": "1",
            "type": "agent_stopped",
            "time": "2026-01-01T00:00:00Z",
            "run_id": "r",
            "data": {"reason": "converged", "output": output},
        }
    )


def test_an_eval_scored_with_match(tmp_path: Path) -> None:
    path = tmp_path / "capitals.eval.json"
    path.write_text(
        json.dumps(
            {
                "eval_version": "0.1",
                "name": "capitals",
                "agents": "pd",
                "commission": {
                    "avp_version": "0.1",
                    "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
                    "prompt": "Name the city in: {item.text}",
                },
                "dataset": [
                    {"id": "paris", "text": "Paris is in France.", "answer": "Paris"},
                    {"id": "tokyo", "text": "Tokyo is in Japan.", "answer": "Tokyo"},
                ],
                "scorer": {"name": "match", "expected": "{item.answer}"},
            }
        )
    )
    config = EvalConfig.from_eval(load(path), tmp_path)
    outputs = {"paris": "Paris", "tokyo": "Kyoto"}
    scores = {}
    for commission, agent, item, built in config:
        directory = tmp_path / built.run_id
        directory.mkdir()
        (directory / paths.TRAJECTORY).write_text(stopped(outputs[item.id]) + "\n")
        run = read(
            directory, id=built.run_id, agent=agent, commission=commission, item=item, exit_code=0
        )
        result = asyncio.run(score(config.scorer, config.scorer_config, run, directory))
        scores[item.id] = result.score
    assert scores == {
        "paris": PASSED,
        "tokyo": Score(value=0, passed=False, reasons=["expected 'Tokyo', got 'Kyoto'"]),
    }
