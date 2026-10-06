//! Stand-in for the harness you are adapting. DELETE this file.
//!
//! It mimics what an agent SDK hands an observer: a stream of native events.
//! A real adapter iterates the SDK's own stream (or hooks) instead. The
//! scripted "model" calls the `echo` tool once when the prompt mentions a
//! tool, then answers.

use serde_json::{json, Value};

use crate::commission::HarnessConfig;

pub fn stream(config: &HarnessConfig) -> Vec<Value> {
    let usage = json!({"prompt_tokens": 120, "completion_tokens": 8});
    let mut events = Vec::new();
    if config.prompt.contains("tool") && config.tools.iter().any(|t| t == "echo") {
        events.push(
            json!({"kind": "message", "id": "msg_1", "text": "Calling echo.", "usage": usage,
            "tool_calls": [{"id": "call_1", "name": "echo", "args": {"text": config.prompt}}]}),
        );
        events.push(json!({"kind": "tool_result", "call_id": "call_1", "output": config.prompt, "error": false}));
    }
    events.push(
        json!({"kind": "message", "id": "msg_2", "text": "DONE", "tool_calls": [], "usage": usage}),
    );
    events.push(json!({"kind": "done", "status": "completed", "output": "DONE"}));
    events
}
