//! Pure projection: Goose `MessageContent` to AVP content blocks and tool
//! fields. No event lifecycle here (that is the emitter / run-state layer);
//! these are deterministic, fixture-testable transforms.
//!
//! `GooseContent` mirrors `goose::conversation::message::MessageContent` on the
//! wire (serde `tag = "type"`, camelCase). The field and shape conventions here
//! are validated against real session content captured from Goose (see
//! `tests/golden.rs`): tool fields are `toolCall` / `toolResult` carrying
//! Goose's `tool_result_serde` status envelope, `arguments` may be absent, and
//! the dispatching extension rides in `_meta.goose_extension` (older messages
//! omit it, so the `{extension}__{tool}` name prefix is the fallback). When the
//! connector is upstreamed in-process, deserialization is replaced by a match on
//! the real Goose enums; the AVP-construction logic below is unchanged.

use std::collections::HashSet;

use avp::trajectory::{
    AvpContentItem, TextBlock, ThinkingBlock, ToolInvokedDataAvpToolDispatchTarget, Usage,
};
use serde::Deserialize;
use serde_json::{Map, Value};

/// Map a Goose provider-usage object (token counts from a turn / token state)
/// to AVP `Usage`.
///
/// AVP convention: `input_tokens` is the *total* prompt size, cache reads and
/// writes INCLUDED (see `avp::pricing::compute_cost`, which subtracts them back
/// out for the fresh-token rate). Anthropic/Goose report fresh input separately
/// from cache tokens, so we fold the cache counts into the AVP input total and
/// also carry them in their own fields. Accepts either Goose's
/// `cache_write_input_tokens` or the `cache_creation_input_tokens` spelling.
pub fn usage(goose: &Value) -> Usage {
    let field = |k: &str| goose.get(k).and_then(Value::as_u64);
    let cache_read = field("cache_read_input_tokens");
    let cache_write =
        field("cache_write_input_tokens").or_else(|| field("cache_creation_input_tokens"));
    Usage {
        input_tokens: field("input_tokens").unwrap_or(0)
            + cache_read.unwrap_or(0)
            + cache_write.unwrap_or(0),
        output_tokens: field("output_tokens").unwrap_or(0),
        cache_read_input_tokens: cache_read,
        cache_creation_input_tokens: cache_write,
        reasoning_output_tokens: None,
    }
}

/// One item of a Goose `Message.content` array.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum GooseContent {
    Text {
        text: String,
    },
    Thinking {
        thinking: String,
        signature: String,
    },
    RedactedThinking {
        data: String,
    },
    ToolRequest {
        id: String,
        #[serde(rename = "toolCall")]
        tool_call: ToolOutcome,
        #[serde(rename = "_meta", default)]
        meta: ToolMeta,
    },
    ToolResponse {
        id: String,
        #[serde(rename = "toolResult")]
        tool_result: ToolOutcome,
    },
    FrontendToolRequest {
        id: String,
        #[serde(rename = "toolCall")]
        tool_call: ToolOutcome,
        #[serde(rename = "_meta", default)]
        meta: ToolMeta,
    },
    /// Recognized-but-unprojected (image, toolConfirmationRequest, ...) and any
    /// future content type. Keeps deserialization forward-compatible.
    #[serde(other)]
    Other,
}

/// Goose's `ToolResult<T>` wire form (`tool_result_serde`): a status-tagged
/// success/error envelope. `value` is the inner payload (a tool call's params,
/// or a tool result's content); we read it structurally.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "status", rename_all = "camelCase")]
pub enum ToolOutcome {
    Success { value: Value },
    Error { error: String },
}

/// Goose's per-content `_meta` bag. We only read the dispatching extension.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct ToolMeta {
    #[serde(default)]
    pub goose_extension: Option<String>,
}

/// A tool the model asked to run. `extension` is the owning Goose extension
/// (for dispatch-target classification): from `_meta.goose_extension`, falling
/// back to the `{extension}__{tool}` name prefix.
#[derive(Debug, Clone, PartialEq)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub input: Map<String, Value>,
    pub extension: Option<String>,
}

/// The result of running a tool.
#[derive(Debug, Clone, PartialEq)]
pub struct ToolReturn {
    pub id: String,
    pub output: Value,
    pub is_error: bool,
}

/// Project a Goose content item into an AVP assistant-message content block.
///
/// Returns `None` for items that are not assistant content (tool calls and
/// results, confirmations, and unrecognized types); those drive trajectory
/// events, handled by the emitter. Image content is deferred for v0.1.
pub fn to_content_block(content: &GooseContent) -> Option<AvpContentItem> {
    match content {
        GooseContent::Text { text } => Some(AvpContentItem::TextBlock(TextBlock {
            text: text.clone(),
            citations: None,
            type_: "text".to_string(),
        })),
        GooseContent::Thinking {
            thinking,
            signature,
        } => {
            Some(AvpContentItem::ThinkingBlock(ThinkingBlock {
                thinking: thinking.clone(),
                // Goose emits an empty signature when the provider gives none.
                signature: (!signature.is_empty()).then(|| signature.clone()),
                redacted: None,
                type_: "thinking".to_string(),
            }))
        }
        GooseContent::RedactedThinking { data } => {
            Some(AvpContentItem::ThinkingBlock(ThinkingBlock {
                // The redacted payload is opaque; carry it as the thinking body
                // with the redacted flag set so consumers do not render it raw.
                thinking: data.clone(),
                signature: None,
                redacted: Some(true),
                type_: "thinking".to_string(),
            }))
        }
        _ => None,
    }
}

/// Extract the tool the model invoked, if this item is a (frontend) tool
/// request. A request whose outcome is an error is treated as no call (the
/// emitter surfaces it as an error, not an invocation).
pub fn as_tool_call(content: &GooseContent) -> Option<ToolCall> {
    let (id, outcome, meta) = match content {
        GooseContent::ToolRequest {
            id,
            tool_call,
            meta,
        } => (id, tool_call, meta),
        GooseContent::FrontendToolRequest {
            id,
            tool_call,
            meta,
        } => (id, tool_call, meta),
        _ => return None,
    };
    let ToolOutcome::Success { value } = outcome else {
        return None;
    };
    let name = value.get("name")?.as_str()?.to_string();
    // `arguments` may be absent (a no-arg tool); treat as empty input.
    let input = value
        .get("arguments")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let extension = meta
        .goose_extension
        .clone()
        .or_else(|| name.split_once("__").map(|(ext, _)| ext.to_string()));
    Some(ToolCall {
        id: id.clone(),
        name,
        input,
        extension,
    })
}

/// Extract a tool result, if this item is a tool response. A Goose-level error
/// outcome maps to `is_error` with the error string as the output.
pub fn as_tool_return(content: &GooseContent) -> Option<ToolReturn> {
    let GooseContent::ToolResponse { id, tool_result } = content else {
        return None;
    };
    match tool_result {
        ToolOutcome::Success { value } => {
            // rmcp `CallToolResult` carries `isError` (camelCase); often absent
            // on success, in which case the result is not an error.
            let is_error = value
                .get("isError")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            Some(ToolReturn {
                id: id.clone(),
                output: value.clone(),
                is_error,
            })
        }
        ToolOutcome::Error { error } => Some(ToolReturn {
            id: id.clone(),
            output: Value::String(error.clone()),
            is_error: true,
        }),
    }
}

/// Append `incoming` content onto an accumulating assistant turn, merging
/// consecutive `Text` deltas into one block.
///
/// Goose's live `reply()` stream yields an assistant inference as incremental
/// message deltas (each carrying a partial `Text`, e.g. `"av"` then
/// `"p-tool-ok"`), not one complete message. A faithful turn-level trajectory
/// concatenates them into a single `assistant_message` rather than emitting one
/// per delta. Non-text blocks (thinking, tool calls) push as-is, so a text run
/// interrupted by another block does not merge across it.
pub fn append_coalescing(buf: &mut Vec<GooseContent>, incoming: Vec<GooseContent>) {
    for item in incoming {
        match (buf.last_mut(), &item) {
            (Some(GooseContent::Text { text: acc }), GooseContent::Text { text: more }) => {
                acc.push_str(more);
            }
            _ => buf.push(item),
        }
    }
}

/// Classify a tool's AVP dispatch target from its owning extension. A tool
/// whose extension is an MCP server (stdio / streamable-http / sse) is
/// `mcp_server`; everything else (builtin, platform, frontend, unknown) is
/// `local`. The caller supplies the set of MCP extension names.
pub fn dispatch_target(
    extension: Option<&str>,
    mcp_servers: &HashSet<String>,
) -> ToolInvokedDataAvpToolDispatchTarget {
    match extension {
        Some(ext) if mcp_servers.contains(ext) => ToolInvokedDataAvpToolDispatchTarget::McpServer,
        _ => ToolInvokedDataAvpToolDispatchTarget::Local,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn parse(raw: &str) -> GooseContent {
        serde_json::from_str(raw).expect("valid GooseContent")
    }

    fn wire(block: &AvpContentItem) -> Value {
        serde_json::to_value(block).expect("serializes")
    }

    #[test]
    fn text_projects_to_text_block() {
        let c = parse(r#"{"type":"text","text":"hello"}"#);
        assert_eq!(
            wire(&to_content_block(&c).unwrap()),
            json!({"type":"text","text":"hello"})
        );
    }

    #[test]
    fn thinking_carries_nonempty_signature() {
        let c = parse(r#"{"type":"thinking","thinking":"step","signature":"sig"}"#);
        assert_eq!(
            wire(&to_content_block(&c).unwrap()),
            json!({"type":"thinking","thinking":"step","signature":"sig"})
        );
    }

    #[test]
    fn thinking_empty_signature_is_omitted() {
        // Goose emits "" when the provider gives no signature.
        let c = parse(r#"{"type":"thinking","thinking":"step","signature":""}"#);
        assert_eq!(
            wire(&to_content_block(&c).unwrap()),
            json!({"type":"thinking","thinking":"step"})
        );
    }

    #[test]
    fn redacted_thinking_sets_flag() {
        let c = parse(r#"{"type":"redactedThinking","data":"opaque"}"#);
        assert_eq!(
            wire(&to_content_block(&c).unwrap()),
            json!({"type":"thinking","thinking":"opaque","redacted":true})
        );
    }

    #[test]
    fn tool_request_extracts_fields_and_extension_from_meta() {
        let c = parse(
            r#"{"type":"toolRequest","id":"call_1",
                "toolCall":{"status":"success",
                  "value":{"name":"execute_typescript","arguments":{"code":"x"}}},
                "_meta":{"goose_extension":"code_execution"}}"#,
        );
        let call = as_tool_call(&c).unwrap();
        assert_eq!(call.id, "call_1");
        assert_eq!(call.name, "execute_typescript");
        assert_eq!(call.input.get("code").unwrap(), "x");
        // Extension comes from _meta when present (tool name is not prefixed).
        assert_eq!(call.extension.as_deref(), Some("code_execution"));
        assert!(to_content_block(&c).is_none());
    }

    #[test]
    fn tool_request_extension_falls_back_to_name_prefix() {
        // No _meta; extension derived from the `{ext}__{tool}` name prefix.
        let c = parse(
            r#"{"type":"toolRequest","id":"call_2",
                "toolCall":{"status":"success","value":{"name":"gtmagent__search"}}}"#,
        );
        let call = as_tool_call(&c).unwrap();
        assert!(call.input.is_empty()); // arguments absent
        assert_eq!(call.extension.as_deref(), Some("gtmagent"));
    }

    #[test]
    fn tool_request_error_outcome_is_not_a_call() {
        let c = parse(
            r#"{"type":"toolRequest","id":"call_3",
                "toolCall":{"status":"error","error":"bad args"}}"#,
        );
        assert!(as_tool_call(&c).is_none());
    }

    #[test]
    fn tool_response_success_reads_is_error() {
        let c = parse(
            r#"{"type":"toolResponse","id":"call_1",
                "toolResult":{"status":"success",
                  "value":{"content":[{"type":"text","text":"ok"}],"isError":false}}}"#,
        );
        let ret = as_tool_return(&c).unwrap();
        assert_eq!(ret.id, "call_1");
        assert!(!ret.is_error);
        assert!(ret.output.get("content").is_some());
    }

    #[test]
    fn tool_response_error_outcome_flags_error() {
        let c = parse(
            r#"{"type":"toolResponse","id":"call_4",
                "toolResult":{"status":"error","error":"tool blew up"}}"#,
        );
        let ret = as_tool_return(&c).unwrap();
        assert!(ret.is_error);
        assert_eq!(ret.output, json!("tool blew up"));
    }

    #[test]
    fn dispatch_target_keys_on_mcp_extension_set() {
        let mcp: HashSet<String> = ["gtmagent".to_string()].into_iter().collect();
        assert_eq!(
            dispatch_target(Some("gtmagent"), &mcp),
            ToolInvokedDataAvpToolDispatchTarget::McpServer
        );
        assert_eq!(
            dispatch_target(Some("developer"), &mcp),
            ToolInvokedDataAvpToolDispatchTarget::Local
        );
        assert_eq!(
            dispatch_target(None, &mcp),
            ToolInvokedDataAvpToolDispatchTarget::Local
        );
    }

    #[test]
    fn append_coalescing_merges_consecutive_text_deltas() {
        let mut buf = Vec::new();
        append_coalescing(&mut buf, vec![parse(r#"{"type":"text","text":"av"}"#)]);
        append_coalescing(
            &mut buf,
            vec![parse(r#"{"type":"text","text":"p-tool-ok"}"#)],
        );
        assert_eq!(buf.len(), 1);
        match &buf[0] {
            GooseContent::Text { text } => assert_eq!(text, "avp-tool-ok"),
            other => panic!("expected merged text, got {other:?}"),
        }
    }

    #[test]
    fn append_coalescing_does_not_merge_across_a_nontext_block() {
        let mut buf = Vec::new();
        append_coalescing(&mut buf, vec![parse(r#"{"type":"text","text":"a"}"#)]);
        append_coalescing(
            &mut buf,
            vec![parse(
                r#"{"type":"thinking","thinking":"hm","signature":""}"#,
            )],
        );
        append_coalescing(&mut buf, vec![parse(r#"{"type":"text","text":"b"}"#)]);
        // text, thinking, text: the thinking breaks the run, so two text blocks.
        assert_eq!(buf.len(), 3);
        assert!(matches!(&buf[0], GooseContent::Text { text } if text == "a"));
        assert!(matches!(&buf[2], GooseContent::Text { text } if text == "b"));
    }

    #[test]
    fn unknown_content_type_deserializes_to_other() {
        let c = parse(r#"{"type":"someFutureBlock","whatever":1}"#);
        assert!(matches!(c, GooseContent::Other));
        assert!(to_content_block(&c).is_none());
    }
}
