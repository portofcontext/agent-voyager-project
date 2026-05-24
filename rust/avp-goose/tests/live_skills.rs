//! Live skills discovery (gated).
//!
//! A Commission ships an inline skill; the connector materializes its SKILL.md
//! and enables Goose's `skills` platform extension. A real model is then asked
//! to use the skill, and the trajectory must show Goose discovering it (the
//! `load_skill` tool), loading it, and the model following it. This is the live
//! confirmation of the skills path that unit/schema tests can't give.
//!
//! `#[ignore]`d: spawns nothing extra but calls a real model (costs money). Run
//! with provider creds (defaults to anthropic from the keychain):
//!
//!     cargo test -p avp-goose --test live_skills -- --ignored
//!
//! Override the model with AVP_TEST_MODEL and provider with GOOSE_PROVIDER.

mod common;

use common::CapturingSink;
use serde_json::json;

const SKILL_MD: &str = "---\n\
name: avp-greeter\n\
description: Use this skill whenever the user asks to greet someone; it defines the exact greeting format.\n\
---\n\
When asked to greet a person, reply with exactly this and nothing else:\n\
AVP-GREETING::<name>\n";

#[tokio::test]
#[ignore = "live: calls a real model to exercise skill discovery (needs provider creds)"]
async fn model_discovers_and_uses_an_inline_skill() {
    let model = std::env::var("AVP_TEST_MODEL").unwrap_or_else(|_| "claude-sonnet-4-6".to_string());
    let commission: avp::Commission = serde_json::from_value(json!({
        "schema_version": "0.1",
        "run_id": format!("live-skill-{}", std::process::id()),
        "model": model,
        "prompt": "Use your greeter skill to greet someone named Bob.",
        "skills": [{ "id": "avp-greeter", "files": { "SKILL.md": SKILL_MD } }],
    }))
    .unwrap();

    let sink = CapturingSink::default();
    avp_goose::runner::run(&commission, sink.clone()).await.expect("connector run");

    let t = sink.trajectory();
    t.assert_schema_valid();

    // The descriptor enumerates the inline skill.
    let descriptor = &t.find("avp.agent_described")["data"]["avp.descriptor"];
    let skills = descriptor["skills"].as_array().cloned().unwrap_or_default();
    assert!(
        skills.iter().any(|s| s["name"] == "avp-greeter"),
        "avp-greeter not in descriptor skills: {skills:?}"
    );

    // Goose surfaces skills via a `load_skill` tool; the model invoked it for
    // our skill, and it returned without error.
    let invoked = t.find_all("avp.tool_invoked");
    assert!(
        invoked.iter().any(|e| e["data"]["avp.tool.name"] == "load_skill"),
        "no load_skill tool_invoked; tools were {:?}",
        invoked.iter().map(|e| &e["data"]["avp.tool.name"]).collect::<Vec<_>>()
    );
    assert!(
        t.find_all("avp.tool_returned")
            .iter()
            .any(|e| e["data"]["avp.tool_result"]["is_error"] != json!(true)),
        "no successful tool_returned"
    );

    // The model followed the skill's instruction.
    let blob = serde_json::to_string(&t.0).unwrap();
    assert!(
        blob.contains("AVP-GREETING::Bob"),
        "model did not follow the skill (expected AVP-GREETING::Bob)"
    );

    assert_eq!(t.find("avp.agent_stopped")["data"]["avp.reason"], "converged");
}
