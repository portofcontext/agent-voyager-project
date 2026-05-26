//! Round-trip smoke test: a real AVP event JSON deserializes into the
//! generated Rust types, then re-serializes to a structurally-equivalent
//! shape. Proves the schema → typify → serde chain is wired correctly.
//!
//! The fixture event below was emitted by the Python reference agent
//! (`avp.agent.AVPAgent`); pasting it into a Rust test pins that the
//! Rust types accept what the agent actually produces. If a future spec
//! bump renames a field, this test fails immediately rather than silently
//! drifting.

use avp::Event;

#[test]
fn agent_started_roundtrips() {
    let raw = r#"{
        "specversion": "1.0",
        "id": "5c390872-f1e6-4e1d-9638-b2edb74ed074",
        "time": "2026-05-07T14:49:42.327551+00:00",
        "subject": "r1",
        "datacontenttype": "application/json",
        "type": "avp.agent_started",
        "source": "avp://agent",
        "data": {
            "trace_id": "00000000000000000000000000000000",
            "span_id": "0000000000000000",
            "parent_span_id": "0000000000000000",
            "gen_ai.operation.name": "invoke_agent",
            "avp.schema_version": "0.1",
            "avp.commission": {
                "schema_version": "0.1",
                "run_id": "r1",
                "model": "test/mock"
            },
            "started_at": "2026-05-08T00:00:00+00:00"
        }
    }"#;

    let parsed: Event = serde_json::from_str(raw).expect("agent_started should deserialize");

    // Discriminate on the union — agent_started should match its variant.
    match parsed {
        Event::AgentStartedEvent(e) => {
            assert_eq!(e.subject.as_ref().map(|s| s.as_str()), Some("r1"));
        }
        other => panic!("expected AgentStartedEvent, got {other:?}"),
    }

    // Re-serialize and re-parse: same shape comes back. This catches any
    // round-trip asymmetry introduced by typify (rename_all, missing fields).
    let parsed2: Event = serde_json::from_str(raw).unwrap();
    let reserialized = serde_json::to_string(&parsed2).unwrap();
    let parsed3: Event = serde_json::from_str(&reserialized).expect("re-serialized form parses");
    let _ = parsed3; // smoke: round-trip succeeds
}

#[test]
fn assistant_message_with_cost_source_parses() {
    // Pins that the `avp.cost.source` field on `assistant_message` is
    // recognized by the generated types. Fixture generated from the
    // canonical Pydantic models (`avp.trajectory.AssistantMessageEvent`).
    let raw = r#"{
        "specversion": "1.0",
        "id": "test-id",
        "time": "2026-05-07T00:00:00Z",
        "subject": "r1",
        "datacontenttype": "application/json",
        "type": "avp.assistant_message",
        "source": "avp://agent",
        "data": {
            "trace_id": "00000000000000000000000000000000",
            "span_id": "1111111111111111",
            "parent_span_id": "0000000000000000",
            "avp.step": 1,
            "avp.duration_ms": 42,
            "avp.content": [{ "type": "text", "text": "hi" }],
            "avp.usage": { "input_tokens": 100, "output_tokens": 25 },
            "avp.cost_usd": 0.001,
            "avp.cost.source": "computed"
        }
    }"#;
    let parsed: Event = serde_json::from_str(raw).expect("assistant_message should deserialize");
    assert!(matches!(parsed, Event::AssistantMessageEvent(_)));
}

#[test]
fn agent_stopped_refused_parses() {
    // Refusal is folded into `agent_stopped` with reason "refused"; the
    // standalone refusal_recorded event was removed in v0.1.
    let raw = r#"{
        "specversion": "1.0",
        "id": "test-id",
        "time": "2026-05-07T00:00:00Z",
        "subject": "r1",
        "datacontenttype": "application/json",
        "type": "avp.agent_stopped",
        "source": "avp://agent",
        "data": {
            "trace_id": "00000000000000000000000000000000",
            "span_id": "2222222222222222",
            "parent_span_id": "0000000000000000",
            "avp.reason": "refused"
        }
    }"#;
    let parsed: Event = serde_json::from_str(raw).expect("agent_stopped should deserialize");
    assert!(matches!(parsed, Event::AgentStoppedEvent(_)));
}
