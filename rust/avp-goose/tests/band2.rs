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
fn summon_tool_call_emits_both_tool_and_subagent_events() {
    // A tool call to the `summon` extension delegates to a subagent. Per spec,
    // a subagent started via a tool call surfaces on BOTH axes: tool_invoked +
    // subagent_invoked, then tool_returned + subagent_returned.
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
    assert_eq!(t.find_all("avp.tool_invoked").len(), 1);
    assert_eq!(t.find_all("avp.subagent_invoked").len(), 1);
    assert_eq!(t.find_all("avp.tool_returned").len(), 1);
    let returned = t.find_all("avp.subagent_returned");
    assert_eq!(returned.len(), 1);
    // Success path: reason converged. The subagent frame is one span: returned
    // reuses the invoked span.
    assert_eq!(returned[0]["data"]["avp.subagent.reason"], "converged");
    assert_eq!(
        t.find("avp.subagent_invoked")["data"]["span_id"],
        returned[0]["data"]["span_id"],
        "subagent_returned reuses the subagent_invoked frame span"
    );
    t.assert_schema_valid();
}

#[test]
fn summon_failure_emits_subagent_returned_with_error_reason() {
    // subagent_failed was collapsed into subagent_returned(reason=error); the
    // paired tool_returned mirrors it with is_error=true.
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
    assert!(t.find_all("avp.subagent_failed").is_empty(), "subagent_failed is gone");
    let returned = t.find_all("avp.subagent_returned");
    assert_eq!(returned.len(), 1);
    assert_eq!(returned[0]["data"]["avp.subagent.reason"], "error");
    // Paired tool_returned carries the error discriminator.
    let tool_returned = t.find("avp.tool_returned");
    assert_eq!(tool_returned["data"]["avp.tool_result"]["is_error"], true);
    t.assert_schema_valid();
}
