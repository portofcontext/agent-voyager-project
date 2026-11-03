"""The eval file's top-level fields."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from avp_cli.eval.schemas import CommissionFile, Eval, NamedCommission

VALID = {
    "eval_version": "0.1",
    "name": "capitals",
    "agents": ["pd"],
    "commission": ["baseline.json", "commissions/terse.json"],
    "dataset": [{"id": "paris", "text": "Paris is in France."}],
    "scorer": {"name": "match", "expected": "{item.text}"},
}


COMMISSION = {
    "avp_version": "0.1",
    "run_id": "r",
    "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
    "prompt": "{item.text}",
}


def test_valid_eval() -> None:
    assert Eval.model_validate(VALID).name == "capitals"


@pytest.mark.parametrize(
    ("given", "name", "source"),
    [
        ("terse", "terse", NamedCommission("terse")),
        ("terse.json", "terse", CommissionFile(Path("terse.json"))),
        ("commissions/terse", "terse", CommissionFile(Path("commissions/terse"))),
        (COMMISSION, "inline-1", COMMISSION),
        ({"avp_version": "0.1"}, "inline-1", {"avp_version": "0.1"}),
    ],
    ids=["name", "file", "path", "inline", "invalid-inline"],
)
def test_one_commission(given: object, name: str, source: object) -> None:
    parsed = Eval.model_validate({**VALID, "commission": given})
    assert parsed.commissions == {name: source}
    assert parsed.model_dump(mode="json")["commission"] == [given]


def test_a_list_of_commissions_by_name() -> None:
    parsed = Eval.model_validate({**VALID, "commission": ["baseline.json", COMMISSION, "terse"]})
    assert list(parsed.commissions) == ["baseline", "inline-2", "terse"]


@pytest.mark.parametrize(
    ("given", "message"),
    [
        ("Base Line", "neither a saved Commission's name"),
        ("commissions/Terse.json", "Commission files need lowercase names: Terse"),
        (["a/terse.json", "b/terse.json"], "Commission names repeat: terse"),
        (None, "an inline Commission must be a JSON object"),
        (3, "an inline Commission must be a JSON object"),
        ([["nested"]], "an inline Commission must be a JSON object"),
    ],
    ids=["not-a-name-or-path", "file-name", "repeated-name", "null", "number", "array"],
)
def test_invalid_commission(given: object, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Eval.model_validate({**VALID, "commission": given})


def test_agents_may_come_from_the_command_line() -> None:
    assert Eval.model_validate({**VALID, "agents": None}).agents is None


def test_one_agent_without_a_list() -> None:
    assert Eval.model_validate({**VALID, "agents": "pd"}).agents == ["pd"]


def test_items_keep_their_fields() -> None:
    [item] = Eval.model_validate(VALID).dataset
    assert item.model_dump(mode="json") == {"id": "paris", "text": "Paris is in France."}


@pytest.mark.parametrize(
    "change",
    [
        {"eval_version": "0.2"},
        {"name": "Capitals"},
        {"agents": []},
        {"commission": []},
        {"commissions": ["baseline.json"]},
        {"unknown": 1},
        {"dataset": []},
        {"dataset": [{"text": "no id"}]},
        {"dataset": [{"id": "Paris"}]},
        {"dataset": [{"id": "a"}, {"id": "a"}]},
        {"dataset": ["not an object"]},
    ],
    ids=[
        "version",
        "name",
        "no-agents",
        "no-commissions",
        "commissions-field",
        "unknown-field",
        "no-items",
        "item-without-id",
        "item-id",
        "repeated-item-id",
        "item-not-an-object",
    ],
)
def test_invalid_eval(change: dict) -> None:
    with pytest.raises(ValidationError):
        Eval.model_validate({**VALID, **change})


def test_the_scorer_keeps_its_fields_as_config() -> None:
    scorer = Eval.model_validate(VALID).scorer
    assert scorer.name == "match"
    assert scorer.config == {"expected": "{item.text}"}


def test_a_scorer_needs_a_name() -> None:
    with pytest.raises(ValidationError):
        Eval.model_validate({**VALID, "scorer": {"expected": "x"}})


@pytest.mark.parametrize("missing", ["eval_version", "name", "commission", "dataset", "scorer"])
def test_required_field(missing: str) -> None:
    with pytest.raises(ValidationError):
        Eval.model_validate({k: v for k, v in VALID.items() if k != missing})
