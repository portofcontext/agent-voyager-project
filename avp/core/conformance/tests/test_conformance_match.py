"""Unit tests for the conformance matcher (`avp_conformance._match`).

The matcher is the wire-shape judge: it decides whether an emitted
trajectory satisfies a case. Bugs here pass broken agents or fail correct
ones, so the orderings, partial-match semantics, forbidden events, and the
stream-folded `final_state` totals are pinned directly.
"""

from __future__ import annotations

from avp_conformance._match import _check_structure, _partial, match_case
from avp_conformance.case import EventMatcher, Expectations, FinalState

# A minimal but realistic trajectory: prelude at the root, one assistant turn
# parented under the agent span, stop. Span ids are well-formed (16 hex) and
# share one trace_id so the universal structure check passes.
_TRACE = "a" * 32
_ZERO = "0" * 16
_AGENT = "3" * 16


def _span(span_id: str, parent: str) -> dict:
    return {"trace_id": _TRACE, "span_id": span_id, "parent_span_id": parent}


TRAJECTORY = [
    {"type": "avp.run_requested", "source": "avp://agent", "data": _span("1" * 16, _ZERO)},
    {"type": "avp.agent_described", "source": "avp://agent", "data": _span("2" * 16, _ZERO)},
    {"type": "avp.agent_started", "source": "avp://agent", "data": _span(_AGENT, _ZERO)},
    {
        "type": "avp.assistant_message",
        "source": "avp://agent",
        "data": {
            **_span("4" * 16, _AGENT),
            "avp.usage": {"input_tokens": 30, "output_tokens": 12},
            "avp.cost_usd": 0.001,
        },
    },
    {
        "type": "avp.agent_stopped",
        "source": "avp://agent",
        "data": {**_span("5" * 16, _AGENT), "avp.reason": "converged"},
    },
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


def test_partial_contains_operator_matches_element_in_list():
    content = [{"type": "thinking"}, {"type": "text", "text": "hi"}]
    assert _partial(content, {"$contains": {"type": "text"}})
    assert _partial({"avp.content": content}, {"avp.content": {"$contains": {"type": "text"}}})
    # No matching element, or a non-list value.
    assert not _partial(content, {"$contains": {"type": "image"}})
    assert not _partial("notalist", {"$contains": {"type": "text"}})


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


# ── structure (universal span-tree invariants) ───────────────────────────────


def test_structure_accepts_well_formed_trajectory():
    assert _check_structure(TRAJECTORY) == []


def test_structure_flags_multiple_trace_ids():
    bad = [
        {"type": "avp.run_requested", "source": "avp://agent", "data": _span("1" * 16, _ZERO)},
        {
            "type": "avp.agent_started",
            "source": "avp://agent",
            "data": {"trace_id": "b" * 32, "span_id": _AGENT, "parent_span_id": _ZERO},
        },
    ]
    reasons = _check_structure(bad)
    assert any("multiple trace_ids" in r for r in reasons)


def test_structure_flags_malformed_and_zero_span_id():
    bad = [
        {"type": "avp.run_requested", "source": "avp://agent", "data": _span("nothex", _ZERO)},
        {"type": "avp.agent_started", "source": "avp://agent", "data": _span(_ZERO, _ZERO)},
    ]
    reasons = _check_structure(bad)
    assert any("malformed span_id" in r for r in reasons)
    assert any("zero span_id" in r for r in reasons)


def test_structure_flags_prelude_not_at_root():
    bad = [{"type": "avp.agent_started", "source": "avp://agent", "data": _span(_AGENT, "9" * 16)}]
    reasons = _check_structure(bad)
    assert any("must be root" in r for r in reasons)


def test_structure_flags_dangling_parent():
    # assistant_message parents under a span no event emitted.
    bad = [
        {"type": "avp.agent_started", "source": "avp://agent", "data": _span(_AGENT, _ZERO)},
        {
            "type": "avp.assistant_message",
            "source": "avp://agent",
            "data": _span("4" * 16, "f" * 16),
        },
    ]
    reasons = _check_structure(bad)
    assert any("resolves to no emitted span" in r for r in reasons)


def test_structure_empty_trajectory_flagged():
    assert _check_structure([]) == ["structure: empty trajectory"]


def test_match_case_surfaces_structure_failure():
    bad = [{"type": "avp.run_requested", "source": "avp://agent", "data": {}}]
    result = match_case(bad, Expectations(events=[_m(type="avp.run_requested")]))
    assert not result.ok
    assert any(r.startswith("structure:") for r in result.reasons)
