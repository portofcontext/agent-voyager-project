"""From an eval file to an EvalConfig: agents, the scorer and its
placeholders, and the runs it yields. The `fixed` scorer comes from
conftest.py."""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import JsonValue

from avp_cli.eval.commission import EvalError, load
from avp_cli.eval.config import EvalConfig
from avp_cli.eval.schemas import Item
from avp_cli.eval.scoring import Run, Score, ScorerInput, call

COMMISSION: dict[str, JsonValue] = {
    "avp_version": "0.1",
    "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
    "prompt": "Name the city in: {item.text}",
}
DATASET: list[JsonValue] = [
    {"id": "paris", "text": "Paris is in France.", "answer": {"city": "Paris"}},
    {"id": "tokyo", "text": "Tokyo is in Japan.", "answer": {"city": "Tokyo"}},
]


def eval_file(tmp_path: Path, **change: JsonValue) -> Path:
    path = tmp_path / "capitals.eval.json"
    fields = {
        "eval_version": "0.1",
        "name": "capitals",
        "agents": ["pd", "my-agent"],
        "commission": [COMMISSION, {**COMMISSION, "prompt": "City? {item.text}"}],
        "dataset": DATASET,
        "scorer": {"name": "fixed"},
    }
    path.write_text(json.dumps({**fields, **change}))
    return path


def problems(path: Path, agents: list[str] | None = None) -> list[str]:
    try:
        EvalConfig.from_eval(load(path), path.parent, agents)
    except EvalError as error:
        return error.problems
    return []


def test_every_commission_on_every_agent_for_every_item(tmp_path: Path) -> None:
    path = eval_file(tmp_path)
    config = EvalConfig.from_eval(load(path), path.parent)
    runs = list(config)
    assert [(c, a, i.id) for c, a, i, _ in runs] == [
        (c, a, i)
        for c in ["inline-1", "inline-2"]
        for a in ["pd", "my-agent"]
        for i in ["paris", "tokyo"]
    ]
    first = runs[0].built
    assert first.run_id.endswith("-inline-1-pd-paris")
    assert first.prompt == "Name the city in: Paris is in France."
    assert runs[-1].built.prompt == "City? Tokyo is in Japan."


def test_agent_option_replaces_the_files_agents(tmp_path: Path) -> None:
    path = eval_file(tmp_path)
    assert EvalConfig.from_eval(load(path), path.parent, ["other"]).agents == ["other"]


def test_semantic_errors_are_checked_for_every_rendered_item(tmp_path: Path) -> None:
    path = eval_file(
        tmp_path,
        commission={
            **COMMISSION,
            "skills": [
                {"name": "guide", "files": {"SKILL.md": "---\nname: {item.id}\n---\n"}},
            ],
        },
    )
    found = problems(path)
    assert len(found) == 2
    assert "item paris" in found[0] and "'paris'" in found[0]
    assert "item tokyo" in found[1] and "'tokyo'" in found[1]


def test_agents_are_required(tmp_path: Path) -> None:
    path = eval_file(tmp_path, agents=None)
    assert problems(path) == ["no agents: the eval names none, and none were given"]
    assert problems(path, ["pd"]) == []


def test_the_scorer_is_the_built_in_callable(tmp_path: Path) -> None:
    path = eval_file(tmp_path, scorer={"name": "fixed", "value": 0.5})
    config = EvalConfig.from_eval(load(path), path.parent)
    assert config.scorer_config == {"value": 0.5}
    run = Run(
        id="r",
        agent="pd",
        commission="inline-1",
        exit_code=0,
        trajectory=None,
        invalid_trajectory=[],
        item=config.dataset[0],
    )
    score = asyncio.run(call(config.scorer, ScorerInput(run=run, config=config.scorer_config)))
    assert score == Score(value=0.5, passed=False)


@pytest.mark.parametrize(
    ("scorer", "expected"),
    [
        (
            {"name": "exact"},
            ["scorer.name: no scorer named 'exact' (the scorers: command, fixed, match)"],
        ),
        (
            {"name": "fixed", "value": "high"},
            ["scorer.value: Input should be a valid number, unable to parse string as a number"],
        ),
        ({"name": "fixed", "extra": 1}, ["scorer.extra: Extra inputs are not permitted"]),
    ],
)
def test_the_scorers_fields_are_checked(tmp_path: Path, scorer: dict, expected: list[str]) -> None:
    assert problems(eval_file(tmp_path, scorer=scorer)) == expected


def test_scorer_placeholders_are_checked_against_every_item(tmp_path: Path) -> None:
    dataset: list[JsonValue] = [*DATASET, {"id": "lima", "text": "Lima is in Peru."}]
    scorer: JsonValue = {
        "name": "fixed",
        "expected": "{item.answer.city}",
        "whole": {"$item": "answer"},
        "text": "{item.answer}",
        "output": "{run.output}",
        "via_run": "{run.item.answer.city}",
        "typo": "{run.outptu}",
    }
    path = eval_file(tmp_path, dataset=dataset, scorer=scorer)
    found = problems(path)
    # `fixed` takes no such fields; the placeholders are checked all the same.
    assert [p for p in found if "Extra inputs" not in p] == [
        "item lima, scorer.expected: item has no field 'answer.city'",
        "item lima, scorer.whole: item has no field 'answer'",
        "item paris, scorer.text: item.answer isn't text; insert it whole with"
        ' {"$item": "answer"}',
        "item tokyo, scorer.text: item.answer isn't text; insert it whole with"
        ' {"$item": "answer"}',
        "item lima, scorer.text: item has no field 'answer'",
        "item lima, scorer.via_run: item has no field 'answer.city'",
        "scorer.typo: run has no field 'outptu'",
    ]


def test_a_malformed_whole_value_placeholder(tmp_path: Path) -> None:
    path = eval_file(tmp_path, scorer={"name": "fixed", "x": {"$item": "a", "b": 1}})
    assert "scorer.x: $item must be the only key, with a field's path" in problems(path)


def test_commission_problems_and_scorer_problems_together(tmp_path: Path) -> None:
    path = eval_file(tmp_path, commission={**COMMISSION, "prompt": "{item.country}"}, agents=None)
    assert problems(path, None) == [
        "no agents: the eval names none, and none were given",
        "item paris, commission.inline-1.prompt: item has no field 'country'",
        "item tokyo, commission.inline-1.prompt: item has no field 'country'",
    ]


def test_conformance_builds_an_eval_config_directly() -> None:
    def case(input: ScorerInput) -> Score:
        return Score(value=1, passed=True)

    config = EvalConfig(
        name="conformance",
        agents=["pd"],
        commissions={"agents-without-entry": {**COMMISSION, "agents": {"other": {}}}},
        dataset=[Item(id="case", text="x")],
        scorer=case,
    )
    [(name, agent, item, built)] = list(config)
    assert built.run_id.endswith("-agents-without-entry-pd-case")
    assert (name, agent, item.id) == (
        "agents-without-entry",
        "pd",
        "case",
    )
