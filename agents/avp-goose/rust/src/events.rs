//! Constructors for AVP trajectory events. These hide the generated
//! CloudEvents envelope and the validated string-newtype plumbing (`SpanId`,
//! `Id`, per-event `*Subject`, ...) behind plain arguments. Shared by the
//! run-state drain and the event emitter.
//!
//! Inputs come from inside the agent (generated ids, known-valid span/trace
//! hex), so the newtype parses are infallible in practice; a panic here means
//! a malformed id was threaded in, which is a bug to surface, not swallow.

use avp::ids::{new_event_id, now_iso, SOURCE_AGENT};
use avp::trajectory::{
    AgentDescribedData, AgentDescribedEvent, AgentDescriptor, AgentStartedData,
    AgentStartedDataAvpOperationName, AgentStartedEvent, AgentStoppedData, AgentStoppedEvent,
    AssistantMessageData, AssistantMessageDataAvpCostSource, AssistantMessageEvent, AvpContentItem,
    Content, ErrorCode, ErrorOccurredData, ErrorOccurredEvent, RunRequestedData, RunRequestedEvent,
    StopReason, SubagentInvokedData, SubagentInvokedEvent, SubagentReturnedData,
    SubagentReturnedEvent, ToolInvokedData, ToolInvokedDataAvpToolDispatchTarget, ToolInvokedEvent,
    ToolResultBlock, ToolReturnedData, ToolReturnedEvent, Usage,
};
use avp::Event;
use serde_json::{Map, Value};

/// Shared CloudEvents envelope construction. Each event type has its own
/// generated `subject` newtype, so the envelope fields are filled per-call;
/// this captures the invariant pieces.
macro_rules! event {
    ($variant:ident, $type:literal, $run_id:expr, $data:expr) => {
        Event::$variant($variant {
            specversion: "1.0".to_string(),
            id: Some(new_event_id().parse().expect("uuid is a valid id")),
            time: Some(now_iso()),
            subject: Some($run_id.parse().expect("non-empty run id")),
            datacontenttype: Some("application/json".to_string()),
            dataschema: None,
            avp_correlation_id: None,
            source: SOURCE_AGENT.to_string(),
            type_: $type.to_string(),
            data: $data,
        })
    };
}

/// Build the `run_requested` event (the run's anchor; carries the Commission).
pub fn run_requested(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    commission: &avp::Commission,
) -> Event {
    // The trajectory schema embeds the Commission as its own generated type;
    // bridge the standalone Commission over via the shared wire form.
    let embedded: avp::trajectory::Commission =
        serde_json::from_value(serde_json::to_value(commission).expect("commission serializes"))
            .expect("commission round-trips to embedded form");
    let (sup_name, sup_version) = match &commission.supervisor {
        Some(s) => (Some(s.name.to_string()), s.version.clone()),
        None => (None, None),
    };
    let data = RunRequestedData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_commission: Some(embedded),
        avp_supervisor_name: sup_name.map(|n| n.parse().expect("valid supervisor name")),
        avp_supervisor_version: sup_version,
    };
    event!(RunRequestedEvent, "avp.run_requested", run_id, data)
}

/// Build the `agent_described` event (the agent's static self-description).
pub fn agent_described(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    descriptor: &AgentDescriptor,
) -> Event {
    let data = AgentDescribedData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_descriptor: descriptor.clone(),
    };
    event!(AgentDescribedEvent, "avp.agent_described", run_id, data)
}

/// Build an `assistant_message` event for one completed turn.
#[allow(clippy::too_many_arguments)]
pub fn assistant_message(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    step: u64,
    duration_ms: u64,
    content: Vec<AvpContentItem>,
    usage: Usage,
    cost_usd: f64,
    cost_source: AssistantMessageDataAvpCostSource,
    provider: Option<&str>,
    response_model: Option<&str>,
) -> Event {
    let data = AssistantMessageData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_step: step,
        avp_duration_ms: duration_ms,
        avp_content: content,
        avp_usage: usage,
        avp_cost_usd: cost_usd,
        avp_cost_source: Some(cost_source),
        avp_provider_name: provider.map(str::to_string),
        avp_request_model: response_model.map(str::to_string),
        avp_response_model: response_model.map(str::to_string),
        avp_response_finish_reasons: None,
        avp_response_time_to_first_chunk: None,
        avp_refusal_category: None,
    };
    Event::AssistantMessageEvent(AssistantMessageEvent {
        specversion: "1.0".to_string(),
        id: Some(new_event_id().parse().expect("uuid is a valid id")),
        time: Some(now_iso()),
        subject: Some(run_id.parse().expect("non-empty run id")),
        datacontenttype: Some("application/json".to_string()),
        dataschema: None,
        avp_correlation_id: None,
        source: SOURCE_AGENT.to_string(),
        type_: "avp.assistant_message".to_string(),
        data,
    })
}

/// Build a `tool_invoked` event.
#[allow(clippy::too_many_arguments)]
pub fn tool_invoked(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    step: u64,
    call_id: &str,
    name: &str,
    input: Map<String, Value>,
    dispatch_target: Option<ToolInvokedDataAvpToolDispatchTarget>,
) -> Event {
    let data = ToolInvokedData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_step: step,
        avp_tool_call_id: call_id.parse().expect("valid tool call id"),
        avp_tool_name: name.to_string(),
        avp_tool_input: input,
        avp_tool_dispatch_target: dispatch_target,
    };
    Event::ToolInvokedEvent(ToolInvokedEvent {
        specversion: "1.0".to_string(),
        id: Some(new_event_id().parse().expect("uuid is a valid id")),
        time: Some(now_iso()),
        subject: Some(run_id.parse().expect("non-empty run id")),
        datacontenttype: Some("application/json".to_string()),
        dataschema: None,
        avp_correlation_id: None,
        source: SOURCE_AGENT.to_string(),
        type_: "avp.tool_invoked".to_string(),
        data,
    })
}

/// Build an AVP `ToolResultBlock` from a tool's raw output and error flag. The
/// human-readable text becomes `content`; the full payload (when an object) is
/// preserved as `structured_content`.
pub fn tool_result_block(call_id: &str, output: &Value, is_error: bool) -> ToolResultBlock {
    let text = result_text(output);
    ToolResultBlock {
        content: Content::String(text),
        is_error: Some(is_error),
        structured_content: output.as_object().cloned(),
        tool_use_id: call_id.to_string(),
        type_: "tool_result".to_string(),
    }
}

fn result_text(output: &Value) -> String {
    if let Some(s) = output.as_str() {
        return s.to_string();
    }
    // rmcp CallToolResult: concatenate the text content items.
    if let Some(items) = output.get("content").and_then(Value::as_array) {
        let mut out = String::new();
        for item in items {
            if item.get("type").and_then(Value::as_str) == Some("text") {
                if let Some(t) = item.get("text").and_then(Value::as_str) {
                    out.push_str(t);
                }
            }
        }
        return out;
    }
    output.to_string()
}

/// Build a `tool_returned` event.
#[allow(clippy::too_many_arguments)]
pub fn tool_returned(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    step: u64,
    call_id: &str,
    name: &str,
    duration_ms: u64,
    result: ToolResultBlock,
) -> Event {
    let data = ToolReturnedData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_step: step,
        avp_duration_ms: duration_ms,
        avp_tool_call_id: call_id.parse().expect("valid tool call id"),
        avp_tool_name: name.to_string(),
        avp_tool_result: result,
    };
    Event::ToolReturnedEvent(ToolReturnedEvent {
        specversion: "1.0".to_string(),
        id: Some(new_event_id().parse().expect("uuid is a valid id")),
        time: Some(now_iso()),
        subject: Some(run_id.parse().expect("non-empty run id")),
        datacontenttype: Some("application/json".to_string()),
        dataschema: None,
        avp_correlation_id: None,
        source: SOURCE_AGENT.to_string(),
        type_: "avp.tool_returned".to_string(),
        data,
    })
}

/// Build a minimal `agent_started` event (loop entry). Descriptor surfaces
/// (tools / subagents / skills / mcp_servers) are filled by the runner once the
/// agent's registry is introspected; here we carry the operation, provider,
/// and model.
pub fn agent_started(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    provider: Option<&str>,
    model: Option<&str>,
) -> Event {
    let data = AgentStartedData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_operation_name: Some(AgentStartedDataAvpOperationName::InvokeAgent),
        avp_provider_name: provider.map(str::to_string),
        avp_request_model: model.map(str::to_string),
        avp_prompt: None,
        avp_system_prompt: None,
        avp_tools: None,
        avp_subagents: None,
        avp_mcp_servers: None,
        avp_skills: None,
        avp_thread_id: None,
        avp_session_id: None,
        avp_tags: None,
    };
    Event::AgentStartedEvent(AgentStartedEvent {
        specversion: "1.0".to_string(),
        id: Some(new_event_id().parse().expect("uuid is a valid id")),
        time: Some(now_iso()),
        subject: Some(run_id.parse().expect("non-empty run id")),
        datacontenttype: Some("application/json".to_string()),
        dataschema: None,
        avp_correlation_id: None,
        source: SOURCE_AGENT.to_string(),
        type_: "avp.agent_started".to_string(),
        data,
    })
}

/// Build the terminal `agent_stopped` event.
pub fn agent_stopped(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    reason: StopReason,
    output: Option<Value>,
) -> Event {
    let data = AgentStoppedData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_reason: reason,
        avp_output: output,
    };
    Event::AgentStoppedEvent(AgentStoppedEvent {
        specversion: "1.0".to_string(),
        id: Some(new_event_id().parse().expect("uuid is a valid id")),
        time: Some(now_iso()),
        subject: Some(run_id.parse().expect("non-empty run id")),
        datacontenttype: Some("application/json".to_string()),
        dataschema: None,
        avp_correlation_id: None,
        source: SOURCE_AGENT.to_string(),
        type_: "avp.agent_stopped".to_string(),
        data,
    })
}

/// Build a non-terminal `error_occurred` event.
pub fn error_occurred(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    code: ErrorCode,
    message: &str,
) -> Event {
    let data = ErrorOccurredData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_error_code: code,
        avp_error_message: message.to_string(),
    };
    event!(ErrorOccurredEvent, "avp.error_occurred", run_id, data)
}

/// Build a `subagent_invoked` event (model delegated to a subagent).
#[allow(clippy::too_many_arguments)]
pub fn subagent_invoked(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    step: u64,
    invocation_id: &str,
    name: &str,
    input: Map<String, Value>,
) -> Event {
    let data = SubagentInvokedData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_step: step,
        avp_subagent_description: None,
        avp_subagent_input: input,
        avp_subagent_invocation_id: invocation_id.parse().expect("valid invocation id"),
        avp_subagent_name: name.to_string(),
        avp_subagent_run_id: None,
    };
    event!(SubagentInvokedEvent, "avp.subagent_invoked", run_id, data)
}

/// Build a `subagent_returned` event. `result` is the subagent's raw tool
/// result; its text becomes the result text. Token usage is omitted (optional;
/// see TECH_DEBT — subagent token attribution).
#[allow(clippy::too_many_arguments)]
pub fn subagent_returned(
    run_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: &str,
    step: u64,
    invocation_id: &str,
    name: &str,
    duration_ms: u64,
    result: &Value,
    reason: StopReason,
) -> Event {
    let data = SubagentReturnedData {
        trace_id: trace_id.parse().expect("valid trace id"),
        span_id: span_id.parse().expect("valid span id"),
        parent_span_id: parent_span_id.parse().expect("valid parent span id"),
        avp_meta: None,
        avp_step: step,
        avp_duration_ms: duration_ms,
        avp_subagent_invocation_id: invocation_id.parse().expect("valid invocation id"),
        avp_subagent_name: name.to_string(),
        avp_subagent_reason: reason,
        avp_subagent_result_text: result_text(result),
        avp_subagent_result_structured: result.as_object().map(|_| result.clone()),
        avp_subagent_usage: None,
    };
    event!(SubagentReturnedEvent, "avp.subagent_returned", run_id, data)
}

// `subagent_failed` was collapsed into `subagent_returned` (reason = error)
// in the v0.1 spec sweep; the error string rides on `avp.subagent.result.text`.
// `mcp_server_connected` / `_disconnected` were removed entirely: MCP server
// identity + dial status now live on the descriptor's `mcp_servers[]`, and each
// MCP-surfaced tool carries `avp.mcp_server_id` in the descriptor's `tools[]`.
