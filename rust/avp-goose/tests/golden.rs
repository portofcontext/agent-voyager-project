//! Golden tests: `translate` against real Goose session content.
//!
//! Fixtures under `tests/fixtures/` are verbatim `content_json` arrays pulled
//! from a live Goose sessions database (`~/.local/share/goose/sessions/`). They
//! pin the projection to what Goose actually emits, not hand-built shapes. This
//! is the layer that caught the `tool_call` vs `toolCall` wire-name bug.

use avp_goose::translate::{as_tool_call, as_tool_return, GooseContent};

const TOOL_REQUEST: &str = include_str!("fixtures/real_tool_request.json");
const TOOL_RESPONSE_ERROR: &str = include_str!("fixtures/real_tool_response_error.json");

fn parse(raw: &str) -> Vec<GooseContent> {
    serde_json::from_str(raw).expect("real content_json deserializes as GooseContent")
}

#[test]
fn real_tool_request_projects() {
    let content = parse(TOOL_REQUEST);
    let call = content.iter().find_map(as_tool_call).expect("a tool call");
    assert_eq!(call.id, "toolu_vrtx_01Dahw11h1Tbv76fCpenUcLy");
    assert_eq!(call.name, "code_navigator__list_tree_sitter_tools");
    // No `arguments` on the wire -> empty input; no `_meta` -> extension from
    // the name prefix.
    assert!(call.input.is_empty());
    assert_eq!(call.extension.as_deref(), Some("code_navigator"));
}

#[test]
fn real_tool_response_error_flags_error() {
    let content = parse(TOOL_RESPONSE_ERROR);
    let ret = content
        .iter()
        .find_map(as_tool_return)
        .expect("a tool return");
    assert_eq!(ret.id, "toolu_vrtx_01UaerKr6kqohXbYPNf8MjMj");
    assert!(ret.is_error);
    assert_eq!(
        ret.output,
        serde_json::json!("-32602: Unsupported file type: ")
    );
}
