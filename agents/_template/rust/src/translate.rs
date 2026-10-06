//! Native harness data -> AVP wire shapes. REPLACE the bodies.
//!
//! Only translation lives here. Ordering, spans, steps, tool pairing, and cost
//! are the Recorder's job.

use avp::trajectory::{AvpContentItem, StopReason, Usage};
use serde_json::{json, Value};

/// The model's output for one inference. Tool calls MUST appear as `tool_use`
/// blocks: the Recorder derives `tool_invoked` from them.
pub fn content(message: &Value) -> Vec<AvpContentItem> {
    let mut blocks = Vec::new();
    if let Some(text) = message["text"].as_str().filter(|t| !t.is_empty()) {
        blocks.push(json!({"type": "text", "text": text}));
    }
    for call in message["tool_calls"].as_array().into_iter().flatten() {
        blocks.push(json!({"type": "tool_use", "id": call["id"], "name": call["name"], "input": call["args"]}));
    }
    blocks
        .into_iter()
        .map(|b| serde_json::from_value(b).expect("valid block"))
        .collect()
}

/// `input_tokens` counts the whole prompt, cache reads and writes included.
pub fn usage(native: &Value) -> Usage {
    Usage {
        input_tokens: native["prompt_tokens"].as_u64().unwrap_or(0),
        output_tokens: native["completion_tokens"].as_u64().unwrap_or(0),
        cache_read_input_tokens: None,
        cache_creation_input_tokens: None,
        reasoning_output_tokens: None,
    }
}

pub fn stop_reason(status: &str) -> StopReason {
    match status {
        "completed" => StopReason::Converged,
        "cancelled" => StopReason::Interrupted,
        _ => StopReason::Error,
    }
}
