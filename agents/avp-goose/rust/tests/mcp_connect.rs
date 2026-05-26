//! Deterministic MCP connection test.
//!
//! Stands up the bundled stdio MCP server (`tests/fixtures/avp_test_mcp.py`)
//! through Goose, using the connector's own Commission-to-extension mapping,
//! and confirms its tools are discovered. No model and no API key: extension
//! loading and `list_tools` do not touch the provider. It does spawn a
//! subprocess and, on first run, fetch the server's dependency via `uv`, so it
//! is `#[ignore]`d out of the default suite; run it with:
//!
//!     cargo test -p avp-goose --test mcp_connect -- --ignored
//!
//! Requires `uv` on PATH.

mod common;

use std::sync::Arc;

use avp_goose::commission::from_commission;
use common::{test_mcp_command, TEST_MCP_ID};
use goose::agents::Agent;
use goose::config::GooseMode;
use goose::session::session_manager::SessionType;
use serde_json::json;

#[tokio::test]
#[ignore = "spawns the uv-run MCP server fixture; needs `uv` on PATH"]
async fn stdio_mcp_server_connects_and_exposes_its_tools() {
    // Isolate Goose state, like the runner does, so the test never touches the
    // user's real session store.
    let tmp = std::env::temp_dir().join(format!("avp-goose-mcp-connect-{}", std::process::id()));
    std::fs::create_dir_all(&tmp).unwrap();
    std::env::set_var("GOOSE_PATH_ROOT", &tmp);

    // Build the extension config through the connector's own mapping, so this
    // exercises from_commission, not a hand-built ExtensionConfig.
    let commission: avp::Commission = serde_json::from_value(json!({
        "schema_version": "0.1",
        "run_id": "mcp-connect",
        "model": "claude-opus-4-7",
        "mcp_servers": [{ "type": "stdio", "id": TEST_MCP_ID, "command": test_mcp_command() }],
    }))
    .unwrap();
    let cfg = from_commission(&commission);

    let agent = Arc::new(Agent::new());
    let working_dir = std::env::current_dir().unwrap();
    let session = agent
        .config
        .session_manager
        .create_session(
            working_dir,
            "mcp-connect".to_string(),
            SessionType::User,
            GooseMode::Auto,
        )
        .await
        .unwrap();
    let session_id = session.id.clone();

    // Real stdio MCP handshake: spawns `uv run avp_test_mcp.py`, initializes,
    // and lists tools.
    let load = agent
        .add_extensions_bulk(cfg.extensions, &session_id)
        .await
        .unwrap();
    assert!(!load.is_empty(), "expected an extension load result");

    let tools = agent.list_tools(&session_id, None).await;
    let names: Vec<String> = tools
        .iter()
        .filter_map(|t| serde_json::to_value(t).ok())
        .filter_map(|v| v.get("name").and_then(|n| n.as_str()).map(str::to_string))
        .collect();

    // The server's two tools surface through Goose (Goose namespaces extension
    // tools, and arcade title-cases them, so match on substring, not exact).
    let lower: Vec<String> = names.iter().map(|n| n.to_lowercase()).collect();
    assert!(
        lower.iter().any(|n| n.contains("echo")),
        "expected an echo tool, got: {names:?}"
    );
    assert!(
        lower.iter().any(|n| n.contains("add")),
        "expected an add tool, got: {names:?}"
    );
}
