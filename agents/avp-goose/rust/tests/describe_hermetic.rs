//! The launcher supplies state; describe must preserve the caller's context.
//! One test per process because Goose initializes global config/session stores.

#[tokio::test]
async fn describe_lists_only_builtin_skills() {
    let fake_home = std::env::temp_dir().join(format!("avp-goose-hermetic-{}", std::process::id()));
    let home = fake_home.join("home");
    let state = fake_home.join("state");
    let workspace = fake_home.join("workspace");
    for dir in [&home, &state, &workspace] {
        std::fs::create_dir_all(dir).unwrap();
    }
    std::env::set_var("HOME", &home);
    std::env::set_var("GOOSE_PATH_ROOT", &state);
    let previous = std::env::current_dir().unwrap();
    std::env::set_current_dir(&workspace).unwrap();
    // No key: the probe must inject its own throwaway for provider
    // construction instead of degrading to the identity-only fallback.
    std::env::remove_var("ANTHROPIC_API_KEY");

    let descriptor = avp_goose::runner::describe().await.expect("describe");
    let v = serde_json::to_value(&descriptor).unwrap();

    // The probe must have produced the full surface; the identity-only
    // fallback would make the skill assertions below pass vacuously.
    let tools = v["tools"].as_array().cloned().unwrap_or_default();
    assert!(
        !tools.is_empty(),
        "describe fell back to the identity-only descriptor"
    );

    let skills = v["skills"].as_array().cloned().unwrap_or_default();
    assert!(
        !skills.is_empty(),
        "expected goose's bundled builtin skills"
    );
    for skill in &skills {
        let source = skill["avp.source"].as_str().unwrap_or("");
        assert!(
            source.starts_with("builtin://"),
            "non-builtin skill source leaked into describe: {} ({})",
            skill["name"],
            source
        );
    }
    assert!(
        !skills
            .iter()
            .any(|s| s["name"] == "avp-planted-local-skill"),
        "host-home skill leaked into describe"
    );

    assert_eq!(std::env::var_os("HOME").unwrap(), home.as_os_str());
    assert_eq!(
        std::env::var_os("GOOSE_PATH_ROOT").unwrap(),
        state.as_os_str()
    );
    assert!(state.exists(), "adapter must not clean up caller state");
    std::env::set_current_dir(previous).unwrap();
    let _ = std::fs::remove_dir_all(&fake_home);
}
