"""Tests for parse_event / parse_supervisor_message — the wire-decode seam.

Pins:
  - Known event types validate against their Pydantic models
  - Unknown event types pass through as plain dicts (SPEC.md §12: consumers
    MUST pass them through without error)
  - Unknown types missing required EventBase fields raise (so a malformed
    custom event isn't silently accepted)
  - Supervisor messages are restricted to the v0.1-allowed types

This is the layer where consumer code (supervisors, analyzers, other tooling)
talks to the wire. If parse_event is wrong, every consumer is wrong.
"""

from __future__ import annotations

import pytest

from aep import parse_event, parse_supervisor_message
from aep.types import AgentStartedEvent, ToolExecResolvedEvent


def test_known_event_type_returns_pydantic_model() -> None:
    payload = {
        "type": "agent_started",
        "source": "runner",
        "run_id": "r1",
        "ts": "2026-05-04T18:00:00Z",
        "model": "claude-sonnet-4-6",
    }
    ev = parse_event(payload)
    assert isinstance(ev, AgentStartedEvent)
    assert ev.run_id == "r1"
    assert ev.model == "claude-sonnet-4-6"


def test_unknown_event_type_passes_through_as_dict() -> None:
    """SPEC.md §12: custom event types MUST pass through. Implementations
    SHOULD use dot-namespaced types like 'myframework.something' to avoid
    future conflicts. Consumers MUST NOT raise on unknown types."""
    payload = {
        "type": "myframework.verifier_result",
        "source": "runner",
        "run_id": "r1",
        "ts": "2026-05-04T18:00:00Z",
        "rule_name": "no-secrets",
        "passed": False,
        "data": {"hits": 3},
    }
    ev = parse_event(payload)
    assert isinstance(ev, dict)
    assert ev["type"] == "myframework.verifier_result"
    # Custom fields preserved verbatim
    assert ev["rule_name"] == "no-secrets"
    assert ev["passed"] is False
    assert ev["data"] == {"hits": 3}


def test_unknown_event_missing_eventbase_fields_raises() -> None:
    """A custom event MUST still carry the EventBase fields (type, source,
    run_id, ts). Otherwise it isn't a valid AEP event and parse_event raises
    so consumers don't silently treat it as one."""
    payload = {
        "type": "myframework.something",
        "source": "runner",
        # missing run_id and ts
    }
    with pytest.raises(ValueError, match="missing required EventBase field"):
        parse_event(payload)


def test_event_payload_missing_type_raises() -> None:
    with pytest.raises(ValueError, match="missing required 'type'"):
        parse_event({"source": "runner", "run_id": "r1", "ts": "2026-05-04T18:00:00Z"})


def test_supervisor_message_tool_exec_resolved_validates() -> None:
    payload = {
        "type": "tool_exec_resolved",
        "source": "supervisor",
        "run_id": "r1",
        "ts": "2026-05-04T18:00:00Z",
        "request_id": "req-1",
        "output": "ok",
    }
    msg = parse_supervisor_message(payload)
    assert isinstance(msg, ToolExecResolvedEvent)
    assert msg.request_id == "req-1"


def test_supervisor_message_runner_event_type_rejected() -> None:
    """The supervisor channel carries ONLY tool_exec_resolved in v0.1.
    A runner event type sent on this channel is malformed."""
    payload = {
        "type": "agent_stopped",
        "source": "runner",
        "run_id": "r1",
        "ts": "2026-05-04T18:00:00Z",
        "reason": "converged",
        "state": {"total_cost_usd": 0.0, "total_tokens": 0, "total_turns": 0},
    }
    with pytest.raises(ValueError, match="unknown or unsupported supervisor message type"):
        parse_supervisor_message(payload)


def test_supervisor_message_unknown_type_rejected() -> None:
    payload = {
        "type": "myframework.fake_message",
        "source": "supervisor",
        "run_id": "r1",
        "ts": "2026-05-04T18:00:00Z",
    }
    with pytest.raises(ValueError, match="unknown or unsupported supervisor message type"):
        parse_supervisor_message(payload)


def test_known_event_with_extensions_envelope_preserved() -> None:
    """Per SPEC.md §12: non-spec FIELDS within a known event type MUST go
    through the `extensions` envelope. The envelope MUST round-trip."""
    payload = {
        "type": "agent_started",
        "source": "runner",
        "run_id": "r1",
        "ts": "2026-05-04T18:00:00Z",
        "model": "x",
        "extensions": {"vendor.priority": "high", "vendor.tags": ["a", "b"]},
    }
    ev = parse_event(payload)
    assert isinstance(ev, AgentStartedEvent)
    assert ev.extensions == {"vendor.priority": "high", "vendor.tags": ["a", "b"]}
