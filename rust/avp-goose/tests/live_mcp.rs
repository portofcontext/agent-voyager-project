//! Live MCP dispatch (gated).
//!
//! A real model is told to use the bundled MCP server's `echo` tool; the run
//! must dispatch through the server and the trajectory must reflect it. This
//! exercises the full connector path end to end: Commission -> Goose agent plus
//! a live stdio MCP server -> AVP trajectory. It is the live confirmation of the
//! MCP connect + dispatch path that unit and connect tests cannot give.
//!
//! `#[ignore]`d: it spawns the `uv` server AND calls a real model (costs money).
//! Run with provider creds available (defaults to anthropic from the keychain):
//!
//!     cargo test -p avp-goose --test live_mcp -- --ignored
//!
//! Override the model with AVP_TEST_MODEL and provider with GOOSE_PROVIDER.

mod common;

use common::{test_mcp_command, CapturingSink, TEST_MCP_ID};
use serde_json::json;

#[tokio::test]
#[ignore = "live: spawns the uv MCP server and calls a real model (needs provider creds)"]
async fn model_dispatches_to_mcp_server_tool() {
    let token = "avp-mcp-roundtrip-7421";
    let model = std::env::var("AVP_TEST_MODEL").unwrap_or_else(|_| "claude-sonnet-4-6".to_string());
    let commission: avp::Commission = serde_json::from_value(json!({
        "schema_version": "0.1",
        "run_id": format!("live-mcp-{}", std::process::id()),
        "model": model,
        "prompt": format!(
            "Use the echo tool to echo exactly this string, then tell me what it returned: {token}"
        ),
        "mcp_servers": [{ "type": "stdio", "id": TEST_MCP_ID, "command": test_mcp_command() }],
    }))
    .unwrap();

    let sink = CapturingSink::default();
    avp_goose::runner::run(&commission, sink.clone())
        .await
        .expect("connector run");

    let t = sink.trajectory();
    t.assert_schema_valid();

    // The MCP server is recorded on the descriptor (mcp_server_connected events
    // were removed; identity + status now ride on agent_described's descriptor).
    let descriptor = &t.find("avp.agent_described")["data"]["avp.descriptor"];
    let servers = descriptor["mcp_servers"].as_array().cloned().unwrap_or_default();
    assert!(
        servers.iter().any(|s| s["id"] == TEST_MCP_ID),
        "no {TEST_MCP_ID} in descriptor mcp_servers: {servers:?}"
    );
    // ... and at least one tool is attributed to it via avp.mcp_server_id.
    let tools = descriptor["tools"].as_array().cloned().unwrap_or_default();
    assert!(
        tools.iter().any(|t| t["avp.mcp_server_id"] == TEST_MCP_ID),
        "no tool attributed to {TEST_MCP_ID} in descriptor tools"
    );

    // The model dispatched at least one tool to the MCP server (this is the
    // assertion that confirms our dispatch_target classification on a real
    // MCP tool call).
    let invoked = t.find_all("avp.tool_invoked");
    let targets: Vec<&serde_json::Value> = invoked
        .iter()
        .map(|e| &e["data"]["avp.tool.dispatch_target"])
        .collect();
    assert!(
        invoked
            .iter()
            .any(|e| e["data"]["avp.tool.dispatch_target"] == "mcp_server"),
        "no tool dispatched to an mcp_server; tool_invoked targets were {targets:?}"
    );

    // A tool returned successfully, and the echoed token round-tripped.
    let returned = t.find_all("avp.tool_returned");
    assert!(
        returned
            .iter()
            .any(|e| e["data"]["avp.tool.is_error"] != json!(true)),
        "no successful tool_returned"
    );
    let blob = serde_json::to_string(&t.0).unwrap();
    assert!(
        blob.contains(token),
        "echoed token {token:?} not found anywhere in the trajectory"
    );

    // The run converged.
    assert_eq!(
        t.find("avp.agent_stopped")["data"]["avp.reason"],
        "converged"
    );
}
