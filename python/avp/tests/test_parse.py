"""Tests for parse_event — the wire-decode seam.

Pins:
  - Known event types validate against their Pydantic models
  - Unknown event types validate as `UnknownEvent` (envelope + span triple
    enforced; the rest of `data` is opaque). Per spec/v0.1/README.md §4,
    consumers MUST pass them through without error.
  - Known event types with malformed payloads raise `ValidationError`
    (they do NOT silently degrade to `UnknownEvent`)
  - Unknown types missing required CloudEvents envelope fields raise
  - The envelope round-trips through model_dump(by_alias=True) into the
    canonical CloudEvents wire form

This is the layer where consumer code (supervisors, analyzers, other tooling)
talks to the wire. If parse_event is wrong, every consumer is wrong.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from avp.trajectory import (
    SOURCE_AGENT,
    ZERO_SPAN_ID,
    AgentStartedEvent,
    UnknownEvent,
    event_to_wire,
    new_event_id,
    new_span_id,
    new_trace_id,
    parse_event,
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
        SOURCE_AGENT,
        "r1",
        {
            **_span(),
            "avp.request.model": "claude-sonnet-4-6",
            "avp.provider.name": "anthropic",
            "avp.schema_version": "0.1",
        },
    )
    ev = parse_event(payload)
    assert isinstance(ev, AgentStartedEvent)
    assert ev.subject == "r1"
    assert ev.data.request_model == "claude-sonnet-4-6"
    assert ev.data.provider_name == "anthropic"


def test_unknown_event_type_returns_unknown_event() -> None:
    """spec/v0.1/README.md §4: custom event types MUST pass through.
    Implementations SHOULD use reverse-DNS types like 'com.example.something'
    to avoid future conflicts with `avp.*`. Consumers MUST NOT raise on
    unknown types. The envelope + span triple are still enforced — every
    event's `data` carries an OTel span triple per spec §2."""
    payload = _envelope(
        "com.example.deploy_completed",
        "com.example://deployer",
        "r1",
        {
            **_span(),
            "environment": "staging",
            "build_id": "abc123",
            "duration_ms": 4200,
        },
    )
    ev = parse_event(payload)
    assert isinstance(ev, UnknownEvent)
    assert ev.type == "com.example.deploy_completed"
    assert ev.subject == "r1"
    # Vendor data round-trips verbatim via `extra="allow"` on _SpanData.
    wire = event_to_wire(ev)
    assert wire["data"]["environment"] == "staging"
    assert wire["data"]["build_id"] == "abc123"


def test_unknown_event_missing_envelope_fields_raises() -> None:
    """A custom event MUST still carry the CloudEvents-required envelope
    fields. Otherwise it isn't a valid AVP event and parse_event raises so
    consumers don't silently treat it as one."""
    payload = {
        "type": "com.example.something",
        "source": SOURCE_AGENT,
        # missing specversion, id, time, data
    }
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_unknown_event_missing_span_triple_raises() -> None:
    """`data` MUST carry the OTel span triple on every event, including
    unknown ones (spec §2). UnknownEvent validates this so malformed
    custom events don't slip through."""
    payload = _envelope(
        "com.example.no_span",
        "com.example://x",
        "r1",
        {"hello": "world"},  # no trace_id / span_id / parent_span_id
    )
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_event_payload_missing_type_raises() -> None:
    """A payload with no `type` field can't be discriminated as a known
    event or as an UnknownEvent. parse_event must surface the error."""
    with pytest.raises(ValidationError):
        parse_event(
            {
                "specversion": "1.0",
                "id": "x",
                "source": SOURCE_AGENT,
                "time": "2026-05-04T18:00:00Z",
                "data": _span(),
            }
        )


def test_known_event_with_malformed_data_raises() -> None:
    """Known event types validate strictly. A payload whose `type` IS in
    the union but whose `data` is invalid MUST NOT silently fall back to
    UnknownEvent — that would mask producer bugs."""
    payload = _envelope(
        "avp.agent_stopped",
        SOURCE_AGENT,
        "r1",
        {**_span()},  # missing required `avp.reason`
    )
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_event_round_trips_to_wire_form_with_dotted_aliases() -> None:
    """A parsed event serialized via event_to_wire MUST emit dotted aliases
    (the AVP wire form), not Python attribute names."""
    payload = _envelope(
        "avp.agent_started",
        SOURCE_AGENT,
        "r1",
        {
            **_span(),
            "avp.request.model": "claude-sonnet-4-6",
            "avp.provider.name": "anthropic",
            "avp.schema_version": "0.1",
            "avp.thread_id": "t-1",
        },
    )
    ev = parse_event(payload)
    assert isinstance(ev, AgentStartedEvent)
    wire = event_to_wire(ev)
    assert "avp.request.model" in wire["data"]
    assert "avp.provider.name" in wire["data"]
    assert "avp.thread_id" in wire["data"]
    assert "avp.schema_version" in wire["data"]
    # Python attribute names MUST NOT leak through
    assert "request_model" not in wire["data"]
    assert "thread_id" not in wire["data"]
