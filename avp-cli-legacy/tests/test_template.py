"""The eval format's single substitution rule (template.render): the grammar,
algorithm, and per-context strictness any implementation must reproduce."""

from __future__ import annotations

import pytest

from avp_cli.eval.template import TemplateError, render, variables_in


def test_defined_token_substitutes_everywhere() -> None:
    assert render("{q} and again {q}", {"q": "x"}) == "x and again x"


def test_undefined_tokens_are_literal_text() -> None:
    # The brace-safety property prompts depend on: JSON examples survive.
    out = render('Return JSON {"city": {city}}: {input}', {"input": "Paris is..."})
    assert out == 'Return JSON {"city": {city}}: Paris is...'


def test_non_token_braces_are_never_syntax() -> None:
    # Spaces, colons, format specs, attribute access: none of it is a token.
    t = "{two words} {x:>10} {a.b} {a[0]} {{escaped-looking}}"
    assert render(t, {"x": "v", "a": "v"}) == t


def test_single_pass_replacement_is_not_rescanned() -> None:
    assert render("{input}", {"input": "literal {input} inside"}) == "literal {input} inside"


def test_non_string_values_render_as_json() -> None:
    # json encoding, not the host language's str(): portable across runners.
    out = render("{n} {b} {nul} {obj}", {"n": 2, "b": True, "nul": None, "obj": {"a": 1}})
    assert out == '2 true null {"a": 1}'


def test_strict_rejects_unknown_names_with_the_available_set() -> None:
    with pytest.raises(TemplateError, match=r"unknown name\(s\) quesiton; available: question"):
        render("{quesiton}", {"question": "?"}, strict=True)


def test_strict_still_ignores_non_token_braces() -> None:
    assert render("{not a token} {pdf}", {"pdf": "u"}, strict=True) == "{not a token} u"


def test_variables_in_lists_tokens_in_order() -> None:
    assert variables_in("{a} {not a token} {b} {a}") == ["a", "b", "a"]
