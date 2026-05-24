//! Live-capture conformance: a real trajectory produced by driving a live Goose
//! `Agent` (developer-tool round), captured verbatim from `avp-goose-run`. This
//! turns a paid live run into a permanent, free regression test: the captured
//! output must keep validating against the canonical AVP schema.

mod common;

use common::*;
use serde_json::Value;

const LIVE_TOOL_ROUND: &str = include_str!("fixtures/live_tool_round.ndjson");

#[test]
fn captured_live_tool_round_is_conformant() {
    let events: Vec<Value> = LIVE_TOOL_ROUND
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| serde_json::from_str(l).expect("ndjson event"))
        .collect();
    let t = Trajectory(events);

    // Every captured event validates against the canonical schema.
    t.assert_schema_valid();

    // The run anchored and terminated cleanly.
    assert_eq!(ty(&t.0[0]), "avp.run_requested");
    assert_eq!(
        t.find("avp.agent_stopped")["data"]["avp.reason"],
        "converged"
    );

    // It exercised a real developer (local) tool round.
    let invoked = t.find("avp.tool_invoked");
    assert_eq!(invoked["data"]["avp.tool.name"], "shell");
    assert_eq!(invoked["data"]["avp.tool.dispatch_target"], "local");
    assert_eq!(
        t.find("avp.tool_returned")["data"]["avp.tool_result"]["is_error"],
        false
    );

    // The run's real cost landed on an assistant_message (run total is exact;
    // per-turn distribution is a known telemetry limitation — see TECH_DEBT).
    let costed = t
        .find_all("avp.assistant_message")
        .iter()
        .any(|m| m["data"]["avp.cost_usd"].as_f64().unwrap_or(0.0) > 0.0);
    assert!(costed, "a turn carries real computed cost");
}
