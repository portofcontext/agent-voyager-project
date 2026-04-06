"""AEP stream validator — protocol compliance checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .events import (
    AepEvent,
    AgentStart,
    AgentStop,
    HookRequest,
    HookVerdictApplied,
    ToolCall,
    ToolCallFailed,
    ToolResult,
    RunError,
    VALID_STOP_REASONS,
    VALID_ERROR_CODES,
    VALID_REJECTION_REASONS,
)

VALID_VERDICTS = frozenset({"continue", "stop", "inject"})


@dataclass
class Violation:
    """A single protocol violation found in an AEP stream."""

    code: str
    message: str
    event_index: int | None = None

    def __str__(self) -> str:
        loc = f"event {self.event_index}" if self.event_index is not None else "stream"
        return f"[{self.code}] {loc}: {self.message}"


def validate(events: list[AepEvent]) -> list[Violation]:
    """Check a list of AEP events for protocol compliance.

    Returns a list of Violation objects (empty = valid).
    """
    violations: list[Violation] = []

    if not events:
        violations.append(Violation("EMPTY_STREAM", "stream contains no events"))
        return violations

    # Must start with agent_start
    if not isinstance(events[0], AgentStart):
        violations.append(
            Violation(
                "MISSING_AGENT_START",
                f"first event must be agent_start, got {_type(events[0])!r}",
                event_index=0,
            )
        )

    # Must end with agent_stop
    if not isinstance(events[-1], AgentStop):
        violations.append(
            Violation(
                "MISSING_AGENT_STOP",
                f"last event must be agent_stop, got {_type(events[-1])!r}",
                event_index=len(events) - 1,
            )
        )

    # All events must share the same run_id
    run_id = _run_id(events[0])
    for i, event in enumerate(events[1:], start=1):
        event_run_id = _run_id(event)
        if event_run_id != run_id:
            violations.append(
                Violation(
                    "RUN_ID_MISMATCH",
                    f"expected run_id {run_id!r}, got {event_run_id!r}",
                    event_index=i,
                )
            )

    # Timestamps must be non-decreasing
    prev_ts = _ts(events[0])
    for i, event in enumerate(events[1:], start=1):
        event_ts = _ts(event)
        if event_ts is not None and prev_ts is not None and event_ts < prev_ts:
            violations.append(
                Violation(
                    "TIMESTAMP_REGRESSION",
                    f"{_type(event)} ts {event_ts!r} is before previous ts {prev_ts!r}",
                    event_index=i,
                )
            )
        if event_ts is not None:
            prev_ts = event_ts

    # Tool calls must be resolved (each tool_call → tool_result or tool_call_failed)
    open_calls: dict[str, int] = {}  # call_id → event_index
    for i, event in enumerate(events):
        if isinstance(event, ToolCall):
            if event.call_id in open_calls:
                violations.append(
                    Violation(
                        "DUPLICATE_CALL_ID",
                        f"call_id {event.call_id!r} already open from event {open_calls[event.call_id]}",
                        event_index=i,
                    )
                )
            open_calls[event.call_id] = i
        elif isinstance(event, (ToolResult, ToolCallFailed)):
            if event.call_id not in open_calls:
                violations.append(
                    Violation(
                        "UNMATCHED_TOOL_RESULT",
                        f"call_id {event.call_id!r} has no matching tool_call",
                        event_index=i,
                    )
                )
            else:
                del open_calls[event.call_id]

    for call_id, event_index in open_calls.items():
        violations.append(
            Violation(
                "UNCLOSED_TOOL_CALL",
                f"tool_call with call_id {call_id!r} was never resolved",
                event_index=event_index,
            )
        )

    # agent_stop reason must be a known value
    if isinstance(events[-1], AgentStop):
        stop = events[-1]
        if stop.reason not in VALID_STOP_REASONS:
            violations.append(
                Violation(
                    "INVALID_STOP_REASON",
                    f"agent_stop reason {stop.reason!r} is not one of {sorted(VALID_STOP_REASONS)}",
                    event_index=len(events) - 1,
                )
            )

    # error events must use known codes
    for i, event in enumerate(events):
        if isinstance(event, RunError) and event.code not in VALID_ERROR_CODES:
            violations.append(
                Violation(
                    "INVALID_ERROR_CODE",
                    f"error event code {event.code!r} is not one of {sorted(VALID_ERROR_CODES)}",
                    event_index=i,
                )
            )

    # tool_result rejection_reason must be a known value when present
    for i, event in enumerate(events):
        if isinstance(event, ToolResult):
            if (
                event.rejection_reason is not None
                and event.rejection_reason not in VALID_REJECTION_REASONS
            ):
                violations.append(
                    Violation(
                        "INVALID_REJECTION_REASON",
                        f"rejection_reason {event.rejection_reason!r} is not one of {sorted(VALID_REJECTION_REASONS)}",
                        event_index=i,
                    )
                )
            if event.rejection_reason is not None and not event.rejected:
                violations.append(
                    Violation(
                        "REJECTION_REASON_WITHOUT_REJECTED",
                        "rejection_reason is set but rejected is not true",
                        event_index=i,
                    )
                )

    # hook_verdict_applied must be preceded by a hook_request with matching request_id
    open_hooks: dict[str, int] = {}  # request_id → event_index
    for i, event in enumerate(events):
        if isinstance(event, HookRequest):
            if event.request_id in open_hooks:
                violations.append(
                    Violation(
                        "DUPLICATE_HOOK_REQUEST_ID",
                        f"request_id {event.request_id!r} already open from event {open_hooks[event.request_id]}",
                        event_index=i,
                    )
                )
            open_hooks[event.request_id] = i
        elif isinstance(event, HookVerdictApplied):
            if event.request_id not in open_hooks:
                violations.append(
                    Violation(
                        "UNMATCHED_HOOK_VERDICT_APPLIED",
                        f"hook_verdict_applied request_id {event.request_id!r} has no matching hook_request",
                        event_index=i,
                    )
                )
            else:
                del open_hooks[event.request_id]
            if event.verdict not in VALID_VERDICTS:
                violations.append(
                    Violation(
                        "INVALID_HOOK_VERDICT",
                        f"hook_verdict_applied verdict {event.verdict!r} is not one of {sorted(VALID_VERDICTS)}",
                        event_index=i,
                    )
                )

    for request_id, event_index in open_hooks.items():
        violations.append(
            Violation(
                "UNCLOSED_HOOK_REQUEST",
                f"hook_request with request_id {request_id!r} was never resolved by hook_verdict_applied",
                event_index=event_index,
            )
        )

    return violations


def _type(event) -> str:
    if isinstance(event, dict):
        return event.get("type", "<unknown>")
    return getattr(event, "type", type(event).__name__)


def _run_id(event) -> str:
    if isinstance(event, dict):
        return event.get("run_id", "")
    return getattr(event, "run_id", "")


def _ts(event) -> str | None:
    if isinstance(event, dict):
        return event.get("ts")
    return getattr(event, "ts", None)
