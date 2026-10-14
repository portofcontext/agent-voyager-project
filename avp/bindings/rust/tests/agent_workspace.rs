//! A separate process: cwd/env are global and must not race other CLI tests.
use avp::agent_cli::{dispatch, BoxError};
use serde_json::{json, Value};

#[test]
fn workspace_covers_callbacks_and_children_but_not_cli_paths() {
    let root = std::env::temp_dir().join(format!("avp-workspace-{}", std::process::id()));
    let workspace = root.join("workspace");
    std::fs::create_dir_all(&workspace).unwrap();
    let root = root.canonicalize().unwrap();
    let workspace = workspace.canonicalize().unwrap();
    let previous = std::env::current_dir().unwrap();
    std::env::set_current_dir(&root).unwrap();
    std::env::set_var("AVP_WORKSPACE", &workspace);
    std::fs::write(
        "c.json",
        r#"{"schema_version":"0.1","run_id":"r","model":"x/m"}"#,
    )
    .unwrap();
    let inspect = || -> Result<Value, BoxError> {
        assert_eq!(std::env::current_dir()?, workspace);
        let child = std::process::Command::new("pwd").output()?;
        assert_eq!(
            String::from_utf8(child.stdout)?.trim(),
            workspace.to_str().unwrap()
        );
        Ok(json!({"agent_name":"echo"}))
    };
    let argv = |args: &[&str]| args.iter().map(|s| s.to_string()).collect::<Vec<_>>();
    dispatch(&argv(&["describe", "--out", "d.json"]), inspect, |_, _| {
        Ok(())
    })
    .unwrap();
    assert!(root.join("d.json").exists());
    let result = dispatch(
        &argv(&["run", "--commission", "c.json", "--out", "t.jsonl"]),
        inspect,
        |_, _| {
            inspect()?;
            Err("scripted failure".into())
        },
    );
    assert!(result.is_err());
    assert_eq!(std::env::current_dir().unwrap(), root);
    assert!(root.join("t.jsonl").exists());
    assert_eq!(std::fs::read_dir(&workspace).unwrap().count(), 0);
    std::env::set_current_dir(previous).unwrap();
    std::fs::remove_dir_all(root).unwrap();
}
