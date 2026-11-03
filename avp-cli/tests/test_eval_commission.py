"""From an eval file and its Commission files to each run's Commission."""

import json
from pathlib import Path

import pytest
from pydantic import JsonValue

from avp_cli.eval.commission import EvalError, build, check, load, read
from avp_cli.eval.schemas import Item, NamedCommission
from avp_cli.eval.template import TemplateError

TEMPLATE: dict[str, JsonValue] = {
    "avp_version": "0.1",
    "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
    "prompt": "Name the city in: {item.text}",
    "output_schema": {"$item": "schema"},
}
ITEMS = [
    {"id": "paris", "text": "Paris is in France.", "schema": {"type": "object"}},
    {"id": "tokyo", "text": "Tokyo is in Japan.", "schema": {"type": "object"}},
]


def write(directory: Path, commission: object, dataset: list = ITEMS) -> Path:
    (directory / "commissions").mkdir(exist_ok=True)
    (directory / "commissions" / "capitals.json").write_text(json.dumps(commission))
    path = directory / "capitals.eval.json"
    path.write_text(
        json.dumps(
            {
                "eval_version": "0.1",
                "name": "capitals",
                "commission": "commissions/capitals.json",
                "dataset": dataset,
                "scorer": {},
            }
        )
    )
    return path


def test_an_item_fills_the_commission_from_its_file(tmp_path: Path) -> None:
    path = write(tmp_path, TEMPLATE)
    ev = load(path)
    assert check(ev, path.parent) == []
    template = read(ev.commissions["capitals"], path.parent)
    commission = build(template, ev.dataset[0], "capitals-paris")
    assert commission.run_id == "capitals-paris"
    assert commission.prompt == "Name the city in: Paris is in France."
    assert commission.output_schema == {"type": "object"}
    assert commission.supervisor is not None
    assert commission.supervisor.name == "avp-cli"


def test_avp_replaces_the_files_run_id() -> None:
    item = Item(id="a", text="x", schema={"type": "object"})
    assert build({**TEMPLATE, "run_id": "from-the-file"}, item, "r").run_id == "r"


def test_a_commission_that_fills_to_a_non_object_fails() -> None:
    with pytest.raises(TemplateError, match="isn't a JSON object once filled"):
        build({"$item": "id"}, Item(id="a"), "r", "commission.x")


def test_check_reports_a_file_that_is_not_an_object(tmp_path: Path) -> None:
    path = write(tmp_path, [TEMPLATE])
    [problem] = check(load(path), path.parent)
    assert problem.endswith("capitals.json isn't a JSON object")


def test_check_reports_every_item_and_where(tmp_path: Path) -> None:
    template = {**TEMPLATE, "prompt": "{item.question}", "model": {"$item": "model"}}
    model = {"provider": "anthropic", "id": 1}
    items = [
        {"id": "paris", "question": "Where?", "model": model, "schema": {"type": "object"}},
        {"id": "tokyo"},
    ]
    path = write(tmp_path, template, items)
    assert check(load(path), path.parent) == [
        "item paris, commission.capitals.model.id: Input should be a valid string",
        "item tokyo, commission.capitals.model: item has no field 'model'",
    ]


def test_check_reports_a_missing_file(tmp_path: Path) -> None:
    path = write(tmp_path, TEMPLATE)
    (tmp_path / "commissions" / "capitals.json").unlink()
    [problem] = check(load(path), path.parent)
    assert problem.startswith("commission.capitals: can't read")


def test_saved_commissions_are_not_supported_yet(tmp_path: Path) -> None:
    ev = load(write(tmp_path, TEMPLATE))
    ev.commission = [NamedCommission("baseline")]
    [problem] = check(ev, tmp_path)
    assert "saved Commissions aren't supported yet" in problem


def test_load_reports_an_invalid_eval(tmp_path: Path) -> None:
    path = write(tmp_path, TEMPLATE, dataset=[])
    with pytest.raises(EvalError, match="isn't a valid eval"):
        load(path)
