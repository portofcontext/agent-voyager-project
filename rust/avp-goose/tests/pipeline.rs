//! Full-pipeline golden test: drive the emitter through a real Goose session
//! round captured verbatim from a live sessions DB.
//!
//! `fixtures/real_session_round.json` is a 5-message slice (user prompt ->
//! assistant text -> assistant tool request -> user tool response -> assistant
//! text) pulled from `~/.local/share/goose/sessions/`. This exercises
//! `translate -> runstate -> emit` end to end on data Goose actually produced,
//! including a real pattern: Goose split the assistant's text and its tool call
//! into two separate messages.

mod common;

use avp::trajectory::StopReason;
use avp_goose::translate::GooseContent;
use common::*;
use serde::Deserialize;

#[derive(Deserialize)]
struct SessionMessage {
    role: String,
    content: Vec<GooseContent>,
}

const ROUND: &str = include_str!("fixtures/real_session_round.json");

#[test]
fn real_session_round_drives_full_pipeline() {
    let messages: Vec<SessionMessage> =
        serde_json::from_str(ROUND).expect("real session round deserializes");

    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    em.start(Some("claude-opus-4-7")).unwrap();
    for m in &messages {
        match m.role.as_str() {
            "assistant" => em
                .on_assistant(
                    &m.content,
                    usage_zero(),
                    Some("claude-opus-4-7".to_string()),
                )
                .unwrap(),
            // User messages carry tool responses (or, for the prompt, nothing
            // the emitter projects -> a no-op).
            _ => em.on_tool_results(&m.content).unwrap(),
        }
    }
    em.stop(StopReason::Converged, None).unwrap();

    let t = sink.trajectory();

    // Goose split the assistant's text and its tool call into separate messages,
    // so the turn maps to two assistant_messages; the tool result arrives later
    // and pairs back across the message boundary.
    t.assert_order(&[
        "avp.agent_started",
        "avp.assistant_message",
        "avp.assistant_message",
        "avp.tool_invoked",
        "avp.tool_returned",
        "avp.assistant_message",
        "avp.agent_stopped",
    ]);
    t.assert_schema_valid();

    let invoked = t.find("avp.tool_invoked");
    let returned = t.find("avp.tool_returned");
    assert_eq!(
        invoked["data"]["avp.tool.call_id"],
        "toolu_01HyJZo9q4RNj19s3CzjxtJk"
    );
    assert_eq!(invoked["data"]["avp.tool.name"], "list_functions");
    assert_eq!(
        returned["data"]["avp.tool.call_id"],
        "toolu_01HyJZo9q4RNj19s3CzjxtJk"
    );
    assert_eq!(
        returned["data"]["parent_span_id"],
        invoked["data"]["span_id"]
    );
    assert_eq!(returned["data"]["avp.tool_result"]["is_error"], false);

    // First assistant turn carries the model's real text.
    let messages = t.find_all("avp.assistant_message");
    assert!(messages[0]["data"]["avp.content"][0]["text"]
        .as_str()
        .unwrap()
        .contains("GTM"));

    // Three turns, each parented to the agent span, steps 1..3.
    let agent_span = span(t.find("avp.agent_started"));
    let steps: Vec<i64> = messages
        .iter()
        .map(|e| {
            assert_eq!(parent(e), agent_span);
            e["data"]["avp.step"].as_i64().unwrap()
        })
        .collect();
    assert_eq!(steps, vec![1, 2, 3]);
}
