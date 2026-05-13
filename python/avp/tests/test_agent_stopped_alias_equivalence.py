"""spec/v0.1/trajectory.md §7.1: agent_stopped's top-level convenience aliases
(`avp.total_tokens`, `avp.total_cost_usd`, `avp.total_turns`,
`avp.duration_ms`) MUST equal the matching fields inside `avp.state`
when populated. Pydantic's model_validator enforces this at
construction time so drift is caught at the agent, not at the
supervisor.

These fields are scheduled for removal in v0.2; until then the
contract is "either match the snapshot or leave None."
"""

from __future__ import annotations

import pytest

from avp.enums import StopReason
from avp.trajectory import AgentStoppedData, RunStateSnapshot


def _span_kwargs() -> dict:
    return {
        "trace_id": "0" * 32,
        "span_id": "0" * 16,
        "parent_span_id": "0" * 16,
    }


def _snap(**overrides) -> RunStateSnapshot:
    fields = {"total_cost_usd": 0.5, "total_tokens": 1000, "total_turns": 3, "duration_ms": 4500}
    fields.update(overrides)
    return RunStateSnapshot(**fields)


def test_matching_top_level_and_snapshot_construct_cleanly() -> None:
    """The agent stamps both with the same values — happy path."""
    AgentStoppedData(
        **_span_kwargs(),
        **{
            "avp.reason": StopReason.converged,
            "avp.state": _snap(),
            "avp.total_cost_usd": 0.5,
            "avp.total_tokens": 1000,
            "avp.total_turns": 3,
            "avp.duration_ms": 4500,
        },
    )


def test_top_level_none_with_snapshot_present_is_allowed() -> None:
    """The convenience fields are optional; an agent that wants to skip
    them entirely can do so. SPEC: 'when non-null these MUST equal'."""
    AgentStoppedData(
        **_span_kwargs(),
        **{
            "avp.reason": StopReason.converged,
            "avp.state": _snap(),
            # All top-level fields left None.
        },
    )


def test_disagreeing_total_cost_raises_at_construction() -> None:
    with pytest.raises(ValueError, match=r"avp\.total_cost_usd"):
        AgentStoppedData(
            **_span_kwargs(),
            **{
                "avp.reason": StopReason.converged,
                "avp.state": _snap(total_cost_usd=0.5),
                "avp.total_cost_usd": 0.42,  # <-- disagrees with snapshot
            },
        )


def test_disagreeing_total_tokens_raises_at_construction() -> None:
    with pytest.raises(ValueError, match=r"avp\.total_tokens"):
        AgentStoppedData(
            **_span_kwargs(),
            **{
                "avp.reason": StopReason.converged,
                "avp.state": _snap(total_tokens=1000),
                "avp.total_tokens": 999,
            },
        )


def test_disagreeing_total_turns_raises_at_construction() -> None:
    with pytest.raises(ValueError, match=r"avp\.total_turns"):
        AgentStoppedData(
            **_span_kwargs(),
            **{
                "avp.reason": StopReason.converged,
                "avp.state": _snap(total_turns=3),
                "avp.total_turns": 4,
            },
        )


def test_disagreeing_duration_ms_raises_at_construction() -> None:
    with pytest.raises(ValueError, match=r"avp\.duration_ms"):
        AgentStoppedData(
            **_span_kwargs(),
            **{
                "avp.reason": StopReason.converged,
                "avp.state": _snap(duration_ms=4500),
                "avp.duration_ms": 4501,
            },
        )


def test_snapshot_optional_field_none_means_equivalence_skipped() -> None:
    """`RunStateSnapshot.duration_ms` is optional. If the snapshot side
    is None, the equivalence check is skipped (top-level can be set or
    not). Pins that the validator doesn't false-positive on the
    asymmetric-nullability case."""
    AgentStoppedData(
        **_span_kwargs(),
        **{
            "avp.reason": StopReason.converged,
            "avp.state": _snap(duration_ms=None),
            "avp.duration_ms": 4500,  # snapshot side is None — no comparison
        },
    )
