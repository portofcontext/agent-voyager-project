"""Placeholders: `{item.x}` in a string and `{"$item": "x"}` as a whole value."""

import re

import pytest
from pydantic import JsonValue

from avp_cli.eval.template import Reference, TemplateError, references, render

ITEM: dict[str, JsonValue] = {
    "id": "paris",
    "city": "Paris",
    "population": 2.1,
    "capital": True,
    "answer": {"city": "Paris", "country": {"name": "France"}},
    "tags": ["europe"],
    "note": None,
}
SCOPE: dict[str, JsonValue] = {"item": ITEM}


@pytest.mark.parametrize(
    ("template", "filled"),
    [
        ("{item.city}", "Paris"),
        ("Read /data/{item.id}.pdf", "Read /data/paris.pdf"),
        ("{item.population} million, capital: {item.capital}", "2.1 million, capital: true"),
        ("In {item.answer.country.name}", "In France"),
        ({"$item": "answer"}, ITEM["answer"]),
        ({"$item": "answer.country.name"}, "France"),
        ({"$item": "tags"}, ["europe"]),
        ({"$item": "note"}, None),
        (
            {"schema": {"$item": "answer"}, "n": [1, "{item.id}"]},
            {"schema": ITEM["answer"], "n": [1, "paris"]},
        ),
        (
            'Reply as {"city": "..."} or {other.x} or {item}',
            'Reply as {"city": "..."} or {other.x} or {item}',
        ),
        ({"{item.id}": 1}, {"{item.id}": 1}),
        (3, 3),
    ],
    ids=[
        "text",
        "text-in-a-string",
        "number-and-boolean",
        "nested-text",
        "object",
        "nested-value",
        "array",
        "null",
        "inside-objects-and-arrays",
        "braces-that-are-not-placeholders",
        "keys-are-not-filled",
        "not-a-string",
    ],
)
def test_render(template: JsonValue, filled: JsonValue) -> None:
    assert render(template, SCOPE) == filled


def test_filled_text_is_not_read_again() -> None:
    assert render("{item.a}", {"item": {"a": "{item.b}", "b": "x"}}) == "{item.b}"


def test_a_whole_value_is_not_read_again() -> None:
    inserted: JsonValue = {"text": "{item.b}", "value": {"$item": "b"}}
    scope: dict[str, JsonValue] = {"item": {"a": inserted, "b": "x"}}
    assert render({"$item": "a"}, scope) == inserted


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ({"prompt": "{item.country}"}, "prompt: item has no field 'country'"),
        ({"prompt": "{item.city.name}"}, "prompt: item has no field 'city.name'"),
        (
            {"prompt": "{item.answer}"},
            'item.answer isn\'t text; insert it whole with {"$item": "answer"}',
        ),
        ({"prompt": "{item.note}"}, "item.note isn't text"),
        ({"x": {"$item": "answer", "other": 1}}, "x: $item must be the only key"),
        ({"x": {"$item": 1}}, "x: $item must be the only key"),
        ({"prompt": "{run.response}"}, "prompt: run isn't available here"),
        ({"x": [{"$run": "output"}]}, "x[0]: run isn't available here"),
    ],
    ids=[
        "missing",
        "missing-nested",
        "object-in-text",
        "null-in-text",
        "extra-key",
        "path-not-a-string",
        "run-text",
        "run-value",
    ],
)
def test_render_fails(template: JsonValue, message: str) -> None:
    with pytest.raises(TemplateError, match=re.escape(message)):
        render(template, SCOPE)


def test_run_where_it_is_available() -> None:
    scope: dict[str, JsonValue] = {**SCOPE, "run": {"response": "Paris"}}
    assert render("{run.response} vs {item.city}", scope) == "Paris vs Paris"


def test_references_lists_every_placeholder_and_where() -> None:
    value: JsonValue = {
        "prompt": "{item.city} and {run.output}",
        "schema": {"$item": "answer"},
        "args": ["x", "{item.id}"],
        "n": 1,
    }
    assert references(value, "scorer") == [
        Reference("item", "city", False, "scorer.prompt"),
        Reference("run", "output", False, "scorer.prompt"),
        Reference("item", "answer", True, "scorer.schema"),
        Reference("item", "id", False, "scorer.args[1]"),
    ]


def test_references_rejects_a_malformed_whole_value() -> None:
    with pytest.raises(TemplateError, match=r"^x: \$run must be the only key"):
        references({"x": {"$run": "output", "y": 1}})
