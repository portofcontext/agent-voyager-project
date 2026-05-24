//! Band 2: completeness — error events, subagents, MCP lifecycle.
//!
//! All implemented at the emit level and schema-validated here. Live validation
//! of subagent and MCP-server runs is still a follow-up (see TECH_DEBT).

mod common;

use avp::trajectory::{ErrorCode, StopReason};
use common::*;
use serde_json::json;

// --- error_occurred (implemented) -------------------------------------------

#[test]
fn error_occurred_carries_code_and_message() {
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    em.start(None).unwrap();
    em.error(ErrorCode::RateLimit, "rate limited, backing off")
        .unwrap();
    em.stop(StopReason::Error, None).unwrap();

    let t = sink.trajectory();
    let e = t.find("avp.error_occurred");
    assert_eq!(e["data"]["avp.error.code"], "rate_limit");
    assert_eq!(e["data"]["avp.error.message"], "rate limited, backing off");
    t.assert_order(&[
        "avp.agent_started",
        "avp.error_occurred",
        "avp.agent_stopped",
    ]);
    t.assert_schema_valid();
}

// --- subagents (spec; pending) ----------------------------------------------

#[test]
fn summon_tool_call_emits_subagent_events_not_a_tool_call() {
    // A tool call to the `summon` extension delegates to a subagent. AVP should
    // see subagent_invoked/returned (paired by invocation id), not a plain
    // tool_invoked/tool_returned.
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    em.start(None).unwrap();
    em.on_assistant(
        &[tool_request(
            "s1",
            "summon__run",
            json!({ "recipe": "researcher" }),
            Some("summon"),
        )],
        usage_zero(),
        None,
    )
    .unwrap();
    em.on_tool_results(&[tool_response("s1", "subagent finished")])
        .unwrap();

    let t = sink.trajectory();
    assert_eq!(t.find_all("avp.subagent_invoked").len(), 1);
    assert_eq!(t.find_all("avp.subagent_returned").len(), 1);
    assert!(
        t.find_all("avp.tool_invoked").is_empty(),
        "summon must not be a plain tool call"
    );
    t.assert_schema_valid();
}

#[test]
fn summon_failure_emits_subagent_failed() {
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    em.start(None).unwrap();
    em.on_assistant(
        &[tool_request("s1", "summon__run", json!({}), Some("summon"))],
        usage_zero(),
        None,
    )
    .unwrap();
    em.on_tool_results(&[tool_response_error("s1", "subagent crashed")])
        .unwrap();

    let t = sink.trajectory();
    assert_eq!(t.find_all("avp.subagent_failed").len(), 1);
    t.assert_schema_valid();
}

// --- MCP lifecycle (spec; pending) ------------------------------------------

#[test]
fn mcp_server_connected_emitted_for_commission_mcp_servers() {
    // Loading an MCP-server extension should synthesize an mcp_server_connected
    // event in the prelude.
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &["gtmagent"]);
    em.prelude(
        &commission(json!({
            "mcp_servers": [{ "type": "stdio", "id": "gtmagent", "command": ["uv", "run"] }]
        })),
        &descriptor(json!({})),
    )
    .unwrap();

    let t = sink.trajectory();
    let connected = t.find_all("avp.mcp_server_connected");
    assert_eq!(connected.len(), 1);
    assert_eq!(connected[0]["data"]["avp.mcp.server_id"], "gtmagent");
    t.assert_schema_valid();
}
