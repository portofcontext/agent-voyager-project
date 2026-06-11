//! Free seam test: the `describe` probe must be hermetic.
//!
//! Plain `describe` answers "what does this agent intrinsically ship". Runs
//! execute in a sandbox, so a skill discovered on the host filesystem
//! (~/.claude/skills, ~/.agents/skills) would advertise a source the run can
//! never load. The probe points GOOSE_PATH_ROOT and HOME at a throwaway
//! root; this test plants a skill in every home-anchored location goose
//! sweeps and asserts the descriptor carries `builtin://` skills only.
//!
//! Kept as the single test in this file: `describe` mutates process-global
//! env vars (GOOSE_PATH_ROOT, HOME), which would race parallel tests in the
//! same binary.

const PLANTED_SKILL: &str = "---\n\
name: avp-planted-local-skill\n\
description: Host-local skill that must never leak into the descriptor.\n\
---\n\
If this appears in a descriptor, describe is reading the host home.\n";

#[tokio::test]
async fn describe_lists_only_builtin_skills() {
    let fake_home =
        std::env::temp_dir().join(format!("avp-goose-hermetic-{}", std::process::id()));
    for root in [".claude", ".agents"] {
        let dir = fake_home.join(root).join("skills").join("avp-planted-local-skill");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("SKILL.md"), PLANTED_SKILL).unwrap();
    }
    std::env::set_var("HOME", &fake_home);
    // No key: the probe must inject its own throwaway for provider
    // construction instead of degrading to the identity-only fallback.
    std::env::remove_var("ANTHROPIC_API_KEY");

    let descriptor = avp_goose::runner::describe().await.expect("describe");
    let v = serde_json::to_value(&descriptor).unwrap();

    // The probe must have produced the full surface; the identity-only
    // fallback would make the skill assertions below pass vacuously.
    let tools = v["tools"].as_array().cloned().unwrap_or_default();
    assert!(!tools.is_empty(), "describe fell back to the identity-only descriptor");

    let skills = v["skills"].as_array().cloned().unwrap_or_default();
    assert!(!skills.is_empty(), "expected goose's bundled builtin skills");
    for skill in &skills {
        let source = skill["avp.source"].as_str().unwrap_or("");
        assert!(
            source.starts_with("builtin://"),
            "non-builtin skill source leaked into describe: {} ({})",
            skill["name"], source
        );
    }
    assert!(
        !skills.iter().any(|s| s["name"] == "avp-planted-local-skill"),
        "host-home skill leaked into describe"
    );

    let _ = std::fs::remove_dir_all(&fake_home);
}
