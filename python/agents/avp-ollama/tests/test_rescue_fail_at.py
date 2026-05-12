from __future__ import annotations

import os
from unittest import mock

import pytest

from avp_ollama.translator import RescueFailAt


def test_unset_returns_none_mode():
    with mock.patch.dict(os.environ, {}, clear=True):
        fa = RescueFailAt.from_env()
    assert fa.mode == "none"
    assert fa.fire_before_turn(1) is False
    assert fa.fire_before_turn(7) is False


def test_now_mode():
    fa = RescueFailAt.from_env("now")
    assert fa.mode == "now"
    # `now` is checked pre-turn-loop; per-turn predicate stays false.
    assert fa.fire_before_turn(1) is False


def test_turn_mode_fires_only_on_match():
    fa = RescueFailAt.from_env("turn:2")
    assert fa.mode == "turn"
    assert fa.turn == 2
    assert fa.fire_before_turn(1) is False
    assert fa.fire_before_turn(2) is True
    assert fa.fire_before_turn(3) is False


def test_turn_mode_invalid_value_falls_back_to_none(caplog):
    fa = RescueFailAt.from_env("turn:not-a-number")
    assert fa.mode == "none"


def test_prob_mode_zero_never_fires():
    fa = RescueFailAt.from_env("prob:0.0")
    assert fa.mode == "prob"
    for n in range(1, 50):
        assert fa.fire_before_turn(n) is False


def test_prob_mode_one_always_fires():
    fa = RescueFailAt.from_env("prob:1.0")
    assert fa.mode == "prob"
    for n in range(1, 50):
        assert fa.fire_before_turn(n) is True


def test_prob_mode_clamps_out_of_range_to_none():
    fa = RescueFailAt.from_env("prob:1.5")
    assert fa.mode == "none"


def test_unrecognized_mode_warns_and_disables(caplog):
    fa = RescueFailAt.from_env("on-tuesday")
    assert fa.mode == "none"


@pytest.mark.parametrize("raw", ["NOW", "Turn:2", " prob:0.5 "])
def test_parsing_tolerates_case_and_whitespace(raw):
    fa = RescueFailAt.from_env(raw)
    assert fa.mode != "none"
