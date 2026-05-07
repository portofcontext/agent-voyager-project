"""Strict-greater boundary algorithm from SPEC.md §10.2.

Two checks. Both compare with `>` (strict greater-than).

  check_consumption  — fires AFTER each model_turn_ended and tool_returned.
                       cost / tokens MAY overshoot a max by one final event.

  check_step_projection — fires BEFORE starting a new turn, against the
                          PROJECTED next-turn count (state.total_turns + 1).
                          A max_steps=N run completes EXACTLY N turns.
"""

from __future__ import annotations

from dataclasses import dataclass

from aep.enums import StopReason
from aep.types import Boundary, RunStateSnapshot


@dataclass(frozen=True)
class BoundaryDecision:
    stop: bool
    reason: StopReason | None = None


def check_consumption(state: RunStateSnapshot, boundary: Boundary | None) -> BoundaryDecision:
    if boundary is None:
        return BoundaryDecision(stop=False)
    if boundary.max_cost_usd is not None and state.total_cost_usd > boundary.max_cost_usd:
        return BoundaryDecision(stop=True, reason=StopReason.budget_exhausted)
    if boundary.max_tokens is not None and state.total_tokens > boundary.max_tokens:
        return BoundaryDecision(stop=True, reason=StopReason.token_limit)
    if (
        boundary.max_duration_seconds is not None
        and state.duration_ms is not None
        and state.duration_ms > boundary.max_duration_seconds * 1000
    ):
        return BoundaryDecision(stop=True, reason=StopReason.duration_limit)
    return BoundaryDecision(stop=False)


def check_step_projection(state: RunStateSnapshot, boundary: Boundary | None) -> BoundaryDecision:
    if boundary is None or boundary.max_steps is None:
        return BoundaryDecision(stop=False)
    projected = state.total_turns + 1
    if projected > boundary.max_steps:
        return BoundaryDecision(stop=True, reason=StopReason.turn_limit)
    return BoundaryDecision(stop=False)
