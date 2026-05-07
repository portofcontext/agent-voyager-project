"""Enums and small helpers for AEP v0.1 model."""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Source(StrEnum):
    runner = "runner"
    supervisor = "supervisor"


class StopReason(StrEnum):
    converged = "converged"
    budget_exhausted = "budget_exhausted"
    token_limit = "token_limit"
    turn_limit = "turn_limit"
    duration_limit = "duration_limit"
    error = "error"
    interrupted = "interrupted"
    verifier_failed = "verifier_failed"
    refused = "refused"


class ErrorCode(StrEnum):
    rate_limit = "rate_limit"
    context_limit = "context_limit"
    auth_error = "auth_error"
    runner_crash = "runner_crash"
    accounting_reset = "accounting_reset"
    unknown = "unknown"


class OnFailure(StrEnum):
    halt = "halt"
    inject_correction = "inject_correction"
    continue_ = "continue"


class VerifierError(StrEnum):
    """Why a verifier failed for non-logic reasons. Distinguishes
    'environment broken' (script missing, timed out, crashed) from
    'rule legitimately failed' (passed=false with no error).
    """

    source_unavailable = "source_unavailable"
    source_timed_out = "source_timed_out"
    source_crashed = "source_crashed"


BUILT_IN_VERIFIER_TRIGGERS: Final[frozenset[str]] = frozenset(
    {"before_first_turn", "after_each_turn", "at_end"}
)


def is_on_tool_trigger(trigger: str) -> bool:
    """True if trigger matches the `on_tool:<name>` pattern — fires AFTER
    the named tool returns. Used to assert post-conditions ("the test
    suite still passes after every write_file")."""
    return trigger.startswith("on_tool:") and len(trigger) > len("on_tool:")


def is_pre_tool_trigger(trigger: str) -> bool:
    """True if trigger matches the `pre_tool:<name>` pattern — fires
    BEFORE the named tool dispatches. Used to gate dispatch ("run the
    test suite before deploy", or with an approval source: "ask a human
    before deploy"). The verifier's outcome decides whether the tool
    runs at all."""
    return trigger.startswith("pre_tool:") and len(trigger) > len("pre_tool:")


def tool_name_from_trigger(trigger: str) -> str | None:
    """Extract the tool name from `on_tool:<name>` or `pre_tool:<name>`,
    or None if the trigger isn't a tool-scoped trigger."""
    if is_on_tool_trigger(trigger):
        return trigger[len("on_tool:") :]
    if is_pre_tool_trigger(trigger):
        return trigger[len("pre_tool:") :]
    return None
