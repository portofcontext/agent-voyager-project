//! Shared harness for the avp-goose integration suite.
//!
//! One `CapturingSink`, one `Trajectory` assertion vocabulary, one set of input
//! builders, and schema-conformance baked in: every scenario can (and should)
//! assert its emitted trajectory validates against the canonical AVP schema.

#![allow(dead_code)] // helpers are shared across several test binaries

use std::collections::HashSet;
use std::sync::{Arc, Mutex};

use avp::sink::Sink;
use avp::Event;
use avp_goose::emit::Emitter;
use avp_goose::translate::GooseContent;
use serde_json::{json, Value};

/// Canonical AVP trajectory-event schema (the source of truth for conformance).
const TRAJECTORY_SCHEMA: &str =
    include_str!("../../../../../avp/core/spec/v0.1/trajectory.schema.json");

// --- sink + trajectory ------------------------------------------------------

/// Sink that captures emitted events as wire-form JSON.
#[derive(Clone, Default)]
pub struct CapturingSink {
    events: Arc<Mutex<Vec<Value>>>,
}

impl Sink for CapturingSink {
    fn emit(&self, event: &Event) -> std::io::Result<()> {
        self.events
            .lock()
            .unwrap()
            .push(serde_json::to_value(event).unwrap());
        Ok(())
    }
}

impl CapturingSink {
    pub fn trajectory(&self) -> Trajectory {
        Trajectory(self.events.lock().unwrap().clone())
    }
}

/// A captured trajectory plus the assertions tests reach for.
pub struct Trajectory(pub Vec<Value>);

impl Trajectory {
    pub fn types(&self) -> Vec<String> {
        self.0.iter().map(|e| ty(e).to_string()).collect()
    }

    /// First event of a type (panics if absent).
    pub fn find(&self, event_type: &str) -> &Value {
        self.0
            .iter()
            .find(|e| ty(e) == event_type)
            .unwrap_or_else(|| panic!("no `{event_type}` in trajectory: {:?}", self.types()))
    }

    pub fn find_all(&self, event_type: &str) -> Vec<&Value> {
        self.0.iter().filter(|e| ty(e) == event_type).collect()
    }

    /// Assert the exact ordered sequence of event types.
    pub fn assert_order(&self, expected: &[&str]) {
        assert_eq!(self.types(), expected, "trajectory event order");
    }

    /// Assert every event validates against the canonical AVP schema. This is
    /// the conformance floor: a scenario isn't done until its trajectory is
    /// spec-valid.
    pub fn assert_schema_valid(&self) {
        let schema: Value = serde_json::from_str(TRAJECTORY_SCHEMA).expect("schema parses");
        let validator = jsonschema::validator_for(&schema).expect("schema compiles");
        for event in &self.0 {
            if !validator.is_valid(event) {
                let errors: Vec<String> = validator
                    .iter_errors(event)
                    .map(|e| e.to_string())
                    .collect();
                panic!(
                    "`{}` failed schema validation:\n  {}",
                    ty(event),
                    errors.join("\n  ")
                );
            }
        }
    }
}

// --- event field accessors --------------------------------------------------

pub fn ty(event: &Value) -> &str {
    event["type"].as_str().expect("event has a type")
}
pub fn span(event: &Value) -> &str {
    event["data"]["span_id"]
        .as_str()
        .expect("event has span_id")
}
pub fn parent(event: &Value) -> &str {
    event["data"]["parent_span_id"]
        .as_str()
        .expect("event has parent_span_id")
}

// --- emitter + input builders -----------------------------------------------

/// An emitter wired to a capturing sink, with the given extension names treated
/// as MCP servers for dispatch classification.
pub fn emitter(sink: CapturingSink, mcp: &[&str]) -> Emitter<CapturingSink> {
    let mcp_servers: HashSet<String> = mcp.iter().map(|s| s.to_string()).collect();
    Emitter::new(
        sink,
        "r1",
        Some("anthropic".to_string()),
        mcp_servers,
        avp::load_default_prices(),
    )
}

fn content(value: Value) -> GooseContent {
    serde_json::from_value(value).expect("valid GooseContent")
}

pub fn text(s: &str) -> GooseContent {
    content(json!({ "type": "text", "text": s }))
}

pub fn thinking(thought: &str, signature: &str) -> GooseContent {
    content(json!({ "type": "thinking", "thinking": thought, "signature": signature }))
}

/// A successful tool request. `extension` (when set) is carried in `_meta`.
pub fn tool_request(id: &str, name: &str, args: Value, extension: Option<&str>) -> GooseContent {
    let mut obj = json!({
        "type": "toolRequest",
        "id": id,
        "toolCall": { "status": "success", "value": { "name": name, "arguments": args } }
    });
    if let Some(ext) = extension {
        obj["_meta"] = json!({ "goose_extension": ext });
    }
    content(obj)
}

pub fn tool_response(id: &str, text: &str) -> GooseContent {
    content(json!({
        "type": "toolResponse",
        "id": id,
        "toolResult": { "status": "success",
            "value": { "content": [{ "type": "text", "text": text }] } }
    }))
}

pub fn tool_response_error(id: &str, error: &str) -> GooseContent {
    content(json!({
        "type": "toolResponse",
        "id": id,
        "toolResult": { "status": "error", "error": error }
    }))
}

// --- MCP test-server fixture ------------------------------------------------

/// Extension id of the shared stdio MCP test server
/// (`<repo>/testing/mcp/avp_test_mcp.py`). A stable, self-contained replacement
/// for the old machine-specific `gtmagent` reference, shared across the repo's
/// test suites.
pub const TEST_MCP_ID: &str = "avptest";

/// The argv that launches the shared stdio MCP test server via `uv run` (deps
/// are declared inline in the script, so `uv` bootstraps them). The server
/// lives at the repo root (`testing/mcp/`) so every package can spawn it. Used
/// as a Commission `mcp_servers[].command`: emit-level tests carry it as data,
/// the live tests actually spawn it.
pub fn test_mcp_command() -> Vec<String> {
    // From `agents/avp-goose/rust` up to the repo root, then into the shared fixture.
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../testing/mcp/avp_test_mcp.py");
    vec![
        "uv".to_string(),
        "run".to_string(),
        "--quiet".to_string(),
        path.to_string_lossy().into_owned(),
    ]
}

/// A Commission `mcp_servers` stdio entry for the bundled test server.
pub fn test_mcp_server() -> Value {
    json!({ "type": "stdio", "id": TEST_MCP_ID, "command": test_mcp_command() })
}

// --- avp fixtures (built from the wire form to avoid field plumbing) ---------

pub fn commission(extra: Value) -> avp::Commission {
    let mut base = json!({ "schema_version": "0.1", "run_id": "r1", "model": "claude-opus-4-7" });
    merge(&mut base, extra);
    serde_json::from_value(base).expect("valid Commission")
}

pub fn descriptor(extra: Value) -> avp::trajectory::AgentDescriptor {
    let mut base = json!({
        "agent_name": "goose", "agent_version": "1.35.0", "spec_version": "0.1"
    });
    merge(&mut base, extra);
    serde_json::from_value(base).expect("valid AgentDescriptor")
}

fn merge(base: &mut Value, extra: Value) {
    if let (Some(b), Some(e)) = (base.as_object_mut(), extra.as_object()) {
        for (k, v) in e {
            b.insert(k.clone(), v.clone());
        }
    }
}

/// Zero usage, for turns where token counts are not under test.
pub fn usage_zero() -> avp::trajectory::Usage {
    avp::trajectory::Usage {
        input_tokens: 0,
        output_tokens: 0,
        cache_read_input_tokens: None,
        cache_creation_input_tokens: None,
        reasoning_output_tokens: None,
    }
}
