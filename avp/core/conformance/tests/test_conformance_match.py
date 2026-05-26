"""Unit tests for the conformance matcher (`avp_conformance._match`).

The matcher is the wire-shape judge: it decides whether an emitted
trajectory satisfies a case. Bugs here pass broken agents or fail correct
ones, so the orderings, partial-match semantics, forbidden events, and the
stream-folded `final_state` totals are pinned directly.
"""

from __future__ import annotations

from avp_conformance._match import _partial, match_case
from avp_conformance.case import EventMatcher, Expectations, FinalState

# A minimal but realistic trajectory: prelude, one assistant turn, stop.
TRAJECTORY = [
    {"type": "avp.run_requested", "source": "avp://agent", "data": {}},
    {"type": "avp.agent_described", "source": "avp://agent", "data": {}},
    {"type": "avp.agent_started", "source": "avp://agent", "data": {}},
    {
        "type": "avp.assistant_message",
        "source": "avp://agent",
        "data": {"avp.usage": {"input_tokens": 30, "output_tokens": 12}, "avp.cost_usd": 0.001},
    },
    {"type": "avp.agent_stopped", "source": "avp://agent", "data": {"avp.reason": "converged"}},
]


def _m(**match) -> EventMatcher:
    return EventMatcher(match=match)


# ── _partial ───────────────────────────────────────────────────────────────


def test_partial_subset_dict_ignores_extra_keys():
    assert _partial({"type": "x", "source": "a", "data": {"k": 1}}, {"type": "x"})
    assert _partial({"data": {"a": 1, "b": 2}}, {"data": {"a": 1}})


def test_partial_rejects_missing_key_or_mismatch():
    assert not _partial({"type": "x"}, {"type": "y"})
    assert not _partial({"type": "x"}, {"data": {"a": 1}})
    assert not _partial({"data": {"a": 2}}, {"data": {"a": 1}})


def test_partial_lists_are_exact_length_elementwise():
    assert _partial({"xs": [1, 2]}, {"xs": [1, 2]})
    assert not _partial({"xs": [1, 2, 3]}, {"xs": [1, 2]})


# ── orderings ────────────────────────────────────────────────────────────────


def test_subsequence_allows_gaps_in_order():
    exp = Expectations(
        ordering="in_order_subsequence",
        events=[_m(type="avp.run_requested"), _m(type="avp.agent_stopped")],
    )
    assert match_case(TRAJECTORY, exp).ok


def test_subsequence_fails_when_out_of_order():
    exp = Expectations(
        ordering="in_order_subsequence",
        events=[_m(type="avp.agent_stopped"), _m(type="avp.run_requested")],
    )
    result = match_case(TRAJECTORY, exp)
    assert not result.ok
    assert any("run_requested" in r for r in result.reasons)


def test_strict_requires_contiguous_block():
    contiguous = Expectations(
        ordering="in_order_strict",
        events=[
            _m(type="avp.run_requested"),
            _m(type="avp.agent_described"),
            _m(type="avp.agent_started"),
        ],
    )
    assert match_case(TRAJECTORY, contiguous).ok

    with_gap = Expectations(
        ordering="in_order_strict",
        events=[_m(type="avp.run_requested"), _m(type="avp.agent_started")],
    )
    assert not match_case(TRAJECTORY, with_gap).ok


def test_any_order_ignores_position():
    exp = Expectations(
        ordering="any_order",
        events=[_m(type="avp.agent_stopped"), _m(type="avp.run_requested")],
    )
    assert match_case(TRAJECTORY, exp).ok


# ── forbidden + final_state ──────────────────────────────────────────────────


def test_forbidden_event_present_fails():
    exp = Expectations(
        events=[_m(type="avp.run_requested")],
        forbidden_events=[_m(type="avp.agent_started")],
    )
    result = match_case(TRAJECTORY, exp)
    assert not result.ok
    assert any("forbidden" in r for r in result.reasons)


def test_final_state_stop_reason_and_folded_totals():
    exp = Expectations(
        events=[_m(type="avp.run_requested")],
        final_state=FinalState(
            stop_reason="converged",
            total_turns=1,
            min_total_tokens=40,
            max_total_tokens=42,
            max_total_cost_usd=0.01,
        ),
    )
    assert match_case(TRAJECTORY, exp).ok


def test_final_state_wrong_stop_reason_fails():
    exp = Expectations(
        events=[_m(type="avp.run_requested")],
        final_state=FinalState(stop_reason="error"),
    )
    result = match_case(TRAJECTORY, exp)
    assert not result.ok
    assert any("stop_reason" in r for r in result.reasons)


def test_final_state_token_bound_violation_fails():
    exp = Expectations(
        events=[_m(type="avp.run_requested")],
        final_state=FinalState(min_total_tokens=1000),
    )
    result = match_case(TRAJECTORY, exp)
    assert not result.ok
    assert any("min_total_tokens" in r for r in result.reasons)
