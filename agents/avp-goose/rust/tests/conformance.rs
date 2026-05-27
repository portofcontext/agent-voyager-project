//! Conformance: a representative end-to-end trajectory must validate against
//! the canonical AVP schema, in the right order.

mod common;

use avp::trajectory::StopReason;
use common::*;
use serde_json::json;

#[test]
fn representative_trajectory_is_schema_valid_and_ordered() {
    let sink = CapturingSink::default();
    // No MCP server in this representative trajectory (developer tools are local).
    let mut em = emitter(sink.clone(), &[]);

    em.prelude(
        &commission(json!({ "prompt": "list files" })),
        &descriptor(json!({
            "default_model": "claude-opus-4-7",
            "tools": [{ "name": "developer__shell", "description": "shell",
                        "inputSchema": { "type": "object" } }]
        })),
    )
    .unwrap();
    em.start(Some("claude-opus-4-7")).unwrap();
    em.on_assistant(
        &[
            text("let me check"),
            tool_request(
                "c1",
                "developer__shell",
                json!({ "command": "ls" }),
                Some("developer"),
            ),
        ],
        usage_zero(),
        Some("claude-opus-4-7".to_string()),
    )
    .unwrap();
    em.on_tool_results(&[tool_response("c1", "a\nb")]).unwrap();
    em.on_assistant(
        &[text("done")],
        usage_zero(),
        Some("claude-opus-4-7".to_string()),
    )
    .unwrap();
    em.stop(StopReason::Converged, None).unwrap();

    let t = sink.trajectory();
    t.assert_order(&[
        "avp.run_requested",
        "avp.agent_described",
        "avp.agent_started",
        "avp.assistant_message",
        "avp.tool_invoked",
        "avp.tool_returned",
        "avp.assistant_message",
        "avp.agent_stopped",
    ]);
    t.assert_schema_valid();
}
