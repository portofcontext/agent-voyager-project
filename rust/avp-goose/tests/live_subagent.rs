//! Live subagent delegation (gated).
//!
//! Goose's `summon` extension delegates to subagent recipes scanned from the
//! run's working dir (`.agents/recipes`). The AVP Commission carries subagent
//! *names* (`enabled_builtin_subagents`), not inline definitions, so this test
//! provisions a recipe file into the run's isolated workspace, then asks a real
//! model to delegate to it. The trajectory must dual-fire: `tool_invoked` +
//! `subagent_invoked` (named for the delegated recipe, not the `delegate` tool),
//! then `tool_returned` + `subagent_returned`.
//!
//! `#[ignore]`d: calls a real model (costs money). Run with provider creds
//! (defaults to anthropic from the keychain):
//!
//!     cargo test -p avp-goose --test live_subagent -- --ignored
//!
//! Override the model with AVP_TEST_MODEL and provider with GOOSE_PROVIDER.

mod common;

use common::CapturingSink;
use serde_json::json;

// A minimal subagent recipe: returns a fixed token so the round-trip is
// deterministic to assert.
const RECIPE_YAML: &str = "version: \"1.0.0\"\n\
title: echoer\n\
description: A subagent that returns a fixed confirmation token. Use when asked to delegate an echo task.\n\
instructions: You are a subagent. Reply with exactly this and nothing else - SUBAGENT-OK\n\
prompt: Reply with exactly this and nothing else - SUBAGENT-OK\n";

#[tokio::test]
#[ignore = "live: calls a real model to exercise subagent delegation (needs provider creds)"]
async fn model_delegates_to_a_subagent_recipe() {
    let run_id = format!("live-subagent-{}", std::process::id());

    // Provision the recipe into the run's isolated workspace, where the runner
    // points Goose's working dir (so the summon extension scans it).
    let recipes = std::env::temp_dir()
        .join(format!("avp-goose-{run_id}"))
        .join("workspace/.agents/recipes");
    std::fs::create_dir_all(&recipes).unwrap();
    std::fs::write(recipes.join("echoer.yaml"), RECIPE_YAML).unwrap();

    let model = std::env::var("AVP_TEST_MODEL").unwrap_or_else(|_| "claude-sonnet-4-6".to_string());
    let commission: avp::Commission = serde_json::from_value(json!({
        "schema_version": "0.1",
        "run_id": run_id,
        "model": model,
        "prompt": "Use the delegate tool to run the echoer subagent, then tell me exactly what it returned.",
        "enabled_builtin_subagents": ["echoer"],
    }))
    .unwrap();

    let sink = CapturingSink::default();
    avp_goose::runner::run(&commission, sink.clone()).await.expect("connector run");

    let t = sink.trajectory();
    t.assert_schema_valid();

    // The delegate surfaces on both axes.
    let invoked = t.find_all("avp.subagent_invoked");
    assert_eq!(invoked.len(), 1, "expected one subagent_invoked; types: {:?}", t.types());
    // Named for the delegated recipe (`source`), not the `delegate` tool.
    assert_eq!(invoked[0]["data"]["avp.subagent.name"], "echoer");
    assert!(
        t.find_all("avp.tool_invoked")
            .iter()
            .any(|e| e["data"]["avp.tool.name"] == "delegate"),
        "expected a paired tool_invoked for the delegate call"
    );

    let returned = t.find_all("avp.subagent_returned");
    assert_eq!(returned.len(), 1);
    assert_eq!(returned[0]["data"]["avp.subagent.name"], "echoer");
    assert_eq!(returned[0]["data"]["avp.subagent.reason"], "converged");

    // The subagent ran its recipe and the token round-tripped.
    let blob = serde_json::to_string(&t.0).unwrap();
    assert!(blob.contains("SUBAGENT-OK"), "subagent token not found in trajectory");

    assert_eq!(t.find("avp.agent_stopped")["data"]["avp.reason"], "converged");
}
