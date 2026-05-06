"""Tests for parse_event / parse_supervisor_message — the wire-decode seam.

Pins:
  - Known event types validate against their Pydantic models
  - Unknown event types pass through as plain dicts (SPEC.md §12: consumers
    MUST pass them through without error)
  - Unknown types missing required CloudEvents envelope fields raise
  - Supervisor messages are restricted to the v0.1-allowed types
  - The envelope round-trips through model_dump(by_alias=True) into the
    canonical CloudEvents wire form

This is the layer where consumer code (supervisors, analyzers, other tooling)
talks to the wire. If parse_event is wrong, every consumer is wrong.
"""

from __future__ import annotations

import pytest

from aep import parse_event, parse_supervisor_message
from aep.types import (
    SOURCE_RUNNER,
    SOURCE_SUPERVISOR,
    ZERO_SPAN_ID,
    AgentStartedEvent,
    JsonRpcResponsePayload,
    ToolExecResolvedEvent,
    event_to_wire,
    new_event_id,
    new_span_id,
    new_trace_id,
)


def _envelope(type_: str, source: str, run_id: str, data: dict) -> dict:
    return {
        "specversion": "1.0",
        "id": new_event_id(),
        "source": source,
        "type": type_,
        "subject": run_id,
        "time": "2026-05-04T18:00:00Z",
        "datacontenttype": "application/json",
        "data": data,
    }


def _span() -> dict:
    return {
        "trace_id": new_trace_id(),
        "span_id": new_span_id(),
        "parent_span_id": ZERO_SPAN_ID,
    }


def test_known_event_type_returns_pydantic_model() -> None:
    payload = _envelope(
        "aep.agent_started",
        SOURCE_RUNNER,
        "r1",
        {
            **_span(),
            "gen_ai.request.model": "claude-sonnet-4-6",
            "gen_ai.provider.name": "anthropic",
            "aep.schema_version": "0.1",
        },
    )
    ev = parse_event(payload)
    assert isinstance(ev, AgentStartedEvent)
    assert ev.subject == "r1"
    assert ev.data.gen_ai_request_model == "claude-sonnet-4-6"
    assert ev.data.gen_ai_provider_name == "anthropic"


def test_unknown_event_type_passes_through_as_dict() -> None:
    """SPEC.md §12: custom event types MUST pass through. Implementations
    SHOULD use reverse-DNS types like 'com.example.something' to avoid
    future conflicts with `aep.*`. Consumers MUST NOT raise on unknown types."""
    payload = _envelope(
        "com.example.verifier_result",
        SOURCE_RUNNER,
        "r1",
        {"rule_name": "no-secrets", "passed": False, "hits": 3},
    )
    ev = parse_event(payload)
    assert isinstance(ev, dict)
    assert ev["type"] == "com.example.verifier_result"
    assert ev["data"] == {"rule_name": "no-secrets", "passed": False, "hits": 3}


def test_unknown_event_missing_envelope_fields_raises() -> None:
    """A custom event MUST still carry the CloudEvents-required envelope
    fields. Otherwise it isn't a valid AEP event and parse_event raises so
    consumers don't silently treat it as one."""
    payload = {
        "type": "com.example.something",
        "source": SOURCE_RUNNER,
        # missing specversion, id, time, data
    }
    with pytest.raises(ValueError, match="missing required CloudEvents field"):
        parse_event(payload)


def test_event_payload_missing_type_raises() -> None:
    with pytest.raises(ValueError, match="missing required 'type'"):
        parse_event(
            {
                "specversion": "1.0",
                "id": "x",
                "source": SOURCE_RUNNER,
                "time": "2026-05-04T18:00:00Z",
                "data": {},
            }
        )


def test_supervisor_message_tool_exec_resolved_validates() -> None:
    payload = _envelope(
        "aep.tool_exec_resolved",
        SOURCE_SUPERVISOR,
        "r1",
        {
            **_span(),
            "aep.request_id": "req-1",
            "rpc": {"jsonrpc": "2.0", "id": "req-1", "result": "ok"},
        },
    )
    msg = parse_supervisor_message(payload)
    assert isinstance(msg, ToolExecResolvedEvent)
    assert msg.data.aep_request_id == "req-1"
    assert isinstance(msg.data.rpc, JsonRpcResponsePayload)
    assert msg.data.rpc.result == "ok"


def test_supervisor_message_tool_exec_resolved_from_mcp_server() -> None:
    """tool_exec_resolved.source MAY be aep://mcp/<server_id>."""
    payload = _envelope(
        "aep.tool_exec_resolved",
        "aep://mcp/github",
        "r1",
        {
            **_span(),
            "aep.request_id": "req-2",
            "rpc": {"jsonrpc": "2.0", "id": "req-2", "result": {"ok": True}},
        },
    )
    msg = parse_supervisor_message(payload)
    assert isinstance(msg, ToolExecResolvedEvent)
    assert msg.source == "aep://mcp/github"


def test_supervisor_message_invalid_source_rejected() -> None:
    payload = _envelope(
        "aep.tool_exec_resolved",
        "aep://runner",  # wrong: must be supervisor or aep://mcp/...
        "r1",
        {
            **_span(),
            "aep.request_id": "req-1",
            "rpc": {"jsonrpc": "2.0", "id": "req-1", "result": "ok"},
        },
    )
    with pytest.raises(ValueError, match=r"tool_exec_resolved\.source"):
        parse_supervisor_message(payload)


def test_supervisor_message_runner_event_type_rejected() -> None:
    """The supervisor channel carries ONLY tool_exec_resolved in v0.1.
    A runner event type sent on this channel is malformed."""
    payload = _envelope(
        "aep.agent_stopped",
        SOURCE_RUNNER,
        "r1",
        {
            **_span(),
            "aep.reason": "converged",
            "aep.state": {"total_cost_usd": 0.0, "total_tokens": 0, "total_turns": 0},
        },
    )
    with pytest.raises(ValueError, match="unknown or unsupported supervisor message type"):
        parse_supervisor_message(payload)


def test_supervisor_message_unknown_type_rejected() -> None:
    payload = _envelope(
        "com.example.fake_message",
        SOURCE_SUPERVISOR,
        "r1",
        {},
    )
    with pytest.raises(ValueError, match="unknown or unsupported supervisor message type"):
        parse_supervisor_message(payload)


def test_event_round_trips_to_wire_form_with_dotted_aliases() -> None:
    """A parsed event serialized via event_to_wire MUST emit dotted aliases
    (the OTel/AEP wire form), not Python attribute names."""
    payload = _envelope(
        "aep.agent_started",
        SOURCE_RUNNER,
        "r1",
        {
            **_span(),
            "gen_ai.request.model": "claude-sonnet-4-6",
            "gen_ai.provider.name": "anthropic",
            "aep.schema_version": "0.1",
            "aep.thread_id": "t-1",
        },
    )
    ev = parse_event(payload)
    assert isinstance(ev, AgentStartedEvent)
    wire = event_to_wire(ev)
    assert "gen_ai.request.model" in wire["data"]
    assert "gen_ai.provider.name" in wire["data"]
    assert "aep.thread_id" in wire["data"]
    assert "aep.schema_version" in wire["data"]
    # Python attribute names MUST NOT leak through
    assert "gen_ai_request_model" not in wire["data"]
    assert "aep_thread_id" not in wire["data"]
