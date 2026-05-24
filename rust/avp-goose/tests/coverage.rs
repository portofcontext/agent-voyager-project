//! Conformance coverage: a single run that exercises every event type the
//! connector emits, asserting each appears and the whole trajectory validates
//! against the canonical AVP schema. This is the connector's "we emit our full
//! event surface, conformantly" certification.

mod common;

use avp::trajectory::{ErrorCode, StopReason};
use common::*;
use serde_json::json;

/// Every trajectory-event type the connector can produce.
const ALL_EVENT_TYPES: &[&str] = &[
    "avp.run_requested",
    "avp.agent_described",
    "avp.agent_started",
    "avp.assistant_message",
    "avp.tool_invoked",
    "avp.tool_returned",
    "avp.subagent_invoked",
    "avp.subagent_returned",
    "avp.error_occurred",
    "avp.agent_stopped",
];

#[test]
fn full_event_surface_is_emitted_and_schema_valid() {
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[TEST_MCP_ID]);

    em.prelude(
        &commission(json!({ "mcp_servers": [test_mcp_server()] })),
        &descriptor(json!({
            "tools": [{ "name": "avptest__echo", "description": "echo",
                        "inputSchema": { "type": "object" } }]
        })),
    )
    .unwrap();
    em.start(Some("claude-opus-4-7")).unwrap();

    // One assistant turn requesting a plain tool and two subagents.
    em.on_assistant(
        &[
            text("working on it"),
            tool_request(
                "c1",
                "developer__shell",
                json!({ "command": "ls" }),
                Some("developer"),
            ),
            tool_request(
                "s1",
                "delegate",
                json!({ "source": "researcher" }),
                Some("summon"),
            ),
            tool_request(
                "s2",
                "delegate",
                json!({ "source": "broken" }),
                Some("summon"),
            ),
        ],
        usage_zero(),
        Some("claude-opus-4-7".to_string()),
    )
    .unwrap();

    // Results: tool returns, one subagent succeeds, one fails.
    em.on_tool_results(&[
        tool_response("c1", "a\nb"),
        tool_response("s1", "research complete"),
        tool_response_error("s2", "subagent crashed"),
    ])
    .unwrap();

    em.error(ErrorCode::RateLimit, "rate limited mid-run")
        .unwrap();
    em.stop(StopReason::Converged, None).unwrap();

    let t = sink.trajectory();
    t.assert_schema_valid();
    let types = t.types();
    for expected in ALL_EVENT_TYPES {
        assert!(
            types.contains(&expected.to_string()),
            "missing event type `{expected}` in {types:?}"
        );
    }
}
