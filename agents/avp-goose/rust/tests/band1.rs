//! Band 1: a conformant trajectory — prelude, real usage/cost, stop reasons.

mod common;

use avp::trajectory::StopReason;
use avp_goose::emit::classify_stop;
use avp_goose::translate;
use common::*;
use serde_json::json;

// --- prelude ----------------------------------------------------------------

#[test]
fn prelude_emits_run_requested_then_agent_described() {
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    em.prelude(
        &commission(json!({ "prompt": "hi" })),
        &descriptor(json!({})),
    )
    .unwrap();

    let t = sink.trajectory();
    t.assert_order(&["avp.run_requested", "avp.agent_described"]);
    let rr = t.find("avp.run_requested");
    assert_eq!(rr["data"]["avp.commission"]["run_id"], "r1");
    assert_eq!(rr["data"]["avp.commission"]["model"], "anthropic/claude-opus-4-7");
    assert_eq!(
        t.find("avp.agent_described")["data"]["avp.descriptor"]["agent_name"],
        "goose"
    );
    t.assert_schema_valid();
}

#[test]
fn full_lifecycle_is_ordered_and_conformant() {
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    em.prelude(&commission(json!({})), &descriptor(json!({})))
        .unwrap();
    em.start(Some("claude-opus-4-7")).unwrap();
    em.on_assistant(
        &[text("hi")],
        usage_zero(),
        Some("claude-opus-4-7".to_string()),
    )
    .unwrap();
    em.stop(StopReason::Converged, None).unwrap();

    let t = sink.trajectory();
    t.assert_order(&[
        "avp.run_requested",
        "avp.agent_described",
        "avp.agent_started",
        "avp.assistant_message",
        "avp.agent_stopped",
    ]);
    t.assert_schema_valid();
}

#[test]
fn descriptor_carries_tools() {
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    let d = descriptor(json!({
        "tools": [{ "name": "developer__shell", "description": "run shell",
                    "inputSchema": { "type": "object" } }]
    }));
    em.prelude(&commission(json!({})), &d).unwrap();

    let t = sink.trajectory();
    assert_eq!(
        t.find("avp.agent_described")["data"]["avp.descriptor"]["tools"][0]["name"],
        "developer__shell"
    );
    t.assert_schema_valid();
}

// --- usage / cost -----------------------------------------------------------

#[test]
fn usage_folds_cache_tokens_into_input() {
    // AVP convention: `input_tokens` is the total prompt size with cache reads
    // and writes included.
    let u = translate::usage(&json!({
        "input_tokens": 700, "output_tokens": 500,
        "cache_read_input_tokens": 200, "cache_creation_input_tokens": 100
    }));
    assert_eq!(u.input_tokens, 1000);
    assert_eq!(u.output_tokens, 500);
    assert_eq!(u.cache_read_input_tokens, Some(200));
    assert_eq!(u.cache_creation_input_tokens, Some(100));
}

#[test]
fn usage_accepts_cache_write_spelling() {
    let u = translate::usage(&json!({
        "input_tokens": 10, "output_tokens": 5, "cache_write_input_tokens": 3
    }));
    assert_eq!(u.input_tokens, 13);
    assert_eq!(u.cache_creation_input_tokens, Some(3));
}

#[test]
fn usage_drives_computed_cost_on_assistant_message() {
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    em.start(Some("claude-opus-4-7")).unwrap();
    let u = translate::usage(&json!({
        "input_tokens": 700, "output_tokens": 500,
        "cache_read_input_tokens": 200, "cache_creation_input_tokens": 100
    }));
    em.on_assistant(&[text("hi")], u, Some("claude-opus-4-7".to_string()))
        .unwrap();
    em.stop(StopReason::Converged, None).unwrap();

    let t = sink.trajectory();
    let am = t.find("avp.assistant_message");
    assert_eq!(am["data"]["avp.cost.source"], "computed");
    // fresh=700 -> 700*5 + 200*0.5 + 100*6.25 + 500*25 = 16725 (per 1e6).
    let cost = am["data"]["avp.cost_usd"].as_f64().unwrap();
    assert!((cost - 0.016725).abs() < 1e-9, "cost {cost}");
    assert_eq!(am["data"]["avp.usage"]["input_tokens"], 1000);
    t.assert_schema_valid();
}

#[test]
fn unknown_model_reports_unknown_cost() {
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    em.start(None).unwrap();
    em.on_assistant(
        &[text("hi")],
        usage_zero(),
        Some("mystery/model".to_string()),
    )
    .unwrap();
    em.stop(StopReason::Converged, None).unwrap();

    let t = sink.trajectory();
    let am = t.find("avp.assistant_message");
    assert_eq!(am["data"]["avp.cost.source"], "unknown");
    assert_eq!(am["data"]["avp.cost_usd"], 0.0);
}

// --- stop reasons -----------------------------------------------------------

#[test]
fn classify_stop_has_correct_precedence() {
    assert_eq!(classify_stop(true, false, false), StopReason::Converged);
    assert_eq!(classify_stop(false, false, false), StopReason::Error);
    assert_eq!(classify_stop(true, true, false), StopReason::Interrupted);
    assert_eq!(classify_stop(true, false, true), StopReason::Refused);
    // Refusal outranks interruption and error.
    assert_eq!(classify_stop(false, true, true), StopReason::Refused);
}

#[test]
fn stop_emits_each_reason_on_the_wire() {
    for (reason, wire) in [
        (StopReason::Converged, "converged"),
        (StopReason::Error, "error"),
        (StopReason::Interrupted, "interrupted"),
        (StopReason::Refused, "refused"),
        (StopReason::Abandoned, "abandoned"),
    ] {
        let sink = CapturingSink::default();
        let mut em = emitter(sink.clone(), &[]);
        em.start(None).unwrap();
        em.stop(reason, None).unwrap();
        let t = sink.trajectory();
        assert_eq!(t.find("avp.agent_stopped")["data"]["avp.reason"], wire);
        t.assert_schema_valid();
    }
}

#[test]
fn zero_usage_reports_unknown_even_for_known_model() {
    // No observed usage on a turn reports `unknown`, not a misleading
    // `computed $0` (the intermediate-turn case under the usage-lumping limit).
    let sink = CapturingSink::default();
    let mut em = emitter(sink.clone(), &[]);
    em.start(Some("claude-opus-4-7")).unwrap();
    em.on_assistant(
        &[text("hi")],
        usage_zero(),
        Some("claude-opus-4-7".to_string()),
    )
    .unwrap();
    em.stop(StopReason::Converged, None).unwrap();
    let t = sink.trajectory();
    let am = t.find("avp.assistant_message");
    assert_eq!(am["data"]["avp.cost.source"], "unknown");
    assert_eq!(am["data"]["avp.cost_usd"], 0.0);
    t.assert_schema_valid();
}
