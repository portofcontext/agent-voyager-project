"""Tests for parse_event — the wire-decode seam.

Pins:
  - Known event types validate against their Pydantic models
  - Unknown event types pass through as plain dicts (SPEC.md §12: consumers
    MUST pass them through without error)
  - Unknown types missing required CloudEvents envelope fields raise
  - The envelope round-trips through model_dump(by_alias=True) into the
    canonical CloudEvents wire form

This is the layer where consumer code (supervisors, analyzers, other tooling)
talks to the wire. If parse_event is wrong, every consumer is wrong.
"""

from __future__ import annotations

import pytest

from avp import parse_event
from avp.types import (
    SOURCE_RUNNER,
    ZERO_SPAN_ID,
    AgentStartedEvent,
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
        "avp.agent_started",
        SOURCE_RUNNER,
        "r1",
        {
            **_span(),
            "gen_ai.request.model": "claude-sonnet-4-6",
            "gen_ai.provider.name": "anthropic",
            "avp.schema_version": "0.1",
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
    future conflicts with `avp.*`. Consumers MUST NOT raise on unknown types."""
    payload = _envelope(
        "com.example.deploy_completed",
        SOURCE_RUNNER,
        "r1",
        {"environment": "staging", "build_id": "abc123", "duration_ms": 4200},
    )
    ev = parse_event(payload)
    assert isinstance(ev, dict)
    assert ev["type"] == "com.example.deploy_completed"
    assert ev["data"] == {"environment": "staging", "build_id": "abc123", "duration_ms": 4200}


def test_unknown_event_missing_envelope_fields_raises() -> None:
    """A custom event MUST still carry the CloudEvents-required envelope
    fields. Otherwise it isn't a valid AVP event and parse_event raises so
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


def test_event_round_trips_to_wire_form_with_dotted_aliases() -> None:
    """A parsed event serialized via event_to_wire MUST emit dotted aliases
    (the OTel/AVP wire form), not Python attribute names."""
    payload = _envelope(
        "avp.agent_started",
        SOURCE_RUNNER,
        "r1",
        {
            **_span(),
            "gen_ai.request.model": "claude-sonnet-4-6",
            "gen_ai.provider.name": "anthropic",
            "avp.schema_version": "0.1",
            "avp.thread_id": "t-1",
        },
    )
    ev = parse_event(payload)
    assert isinstance(ev, AgentStartedEvent)
    wire = event_to_wire(ev)
    assert "gen_ai.request.model" in wire["data"]
    assert "gen_ai.provider.name" in wire["data"]
    assert "avp.thread_id" in wire["data"]
    assert "avp.schema_version" in wire["data"]
    # Python attribute names MUST NOT leak through
    assert "gen_ai_request_model" not in wire["data"]
    assert "avp_thread_id" not in wire["data"]
