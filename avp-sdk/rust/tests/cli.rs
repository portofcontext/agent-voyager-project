use std::{
    fs,
    path::PathBuf,
    process::{Command, Stdio},
    sync::OnceLock,
    thread,
    time::{Duration, Instant},
};

use serde_json::{Value, json};

fn agent() -> &'static PathBuf {
    static AGENT: OnceLock<PathBuf> = OnceLock::new();
    AGENT.get_or_init(|| {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        assert!(
            Command::new(env!("CARGO"))
                .args(["build", "--offline", "--quiet", "--example", "cli-fixture"])
                .current_dir(&root)
                .status()
                .unwrap()
                .success()
        );
        let metadata: Value = serde_json::from_slice(
            &Command::new(env!("CARGO"))
                .args([
                    "metadata",
                    "--offline",
                    "--format-version",
                    "1",
                    "--no-deps",
                ])
                .current_dir(root)
                .output()
                .unwrap()
                .stdout,
        )
        .unwrap();
        PathBuf::from(metadata["target_directory"].as_str().unwrap())
            .join("debug/examples/cli-fixture")
    })
}

fn commission(prompt: &str) -> String {
    json!({"avp_version": "0.1", "run_id": "r", "prompt": prompt, "model": {"provider": "p", "id": "m"}}).to_string()
}

fn events(text: &[u8]) -> Vec<Value> {
    String::from_utf8_lossy(text)
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
}

#[test]
fn ping_describe_and_complete_or_refused_runs() {
    let output = Command::new(agent()).arg("ping").output().unwrap();
    assert!(output.status.success());
    assert_eq!(
        serde_json::from_slice::<Value>(&output.stdout).unwrap(),
        json!({"type": "pong", "avp_version": "0.1"})
    );
    let dir = tempfile::tempdir().unwrap();
    let descriptor_path = dir.path().join("descriptor.json");
    assert!(
        Command::new(agent())
            .args(["describe", "--out"])
            .arg(&descriptor_path)
            .status()
            .unwrap()
            .success()
    );
    let descriptor: avp::descriptor::AgentDescriptor =
        serde_json::from_slice(&fs::read(descriptor_path).unwrap()).unwrap();
    assert_eq!(descriptor.agent_name.as_str(), "example");
    let path = dir.path().join("commission.json");
    fs::write(&path, commission("hi")).unwrap();
    let out = dir.path().join("run.ndjson");
    fs::write(&out, "old contents").unwrap();
    let output = Command::new(agent())
        .args(["run", "--commission"])
        .arg(&path)
        .arg("--out")
        .arg(&out)
        .output()
        .unwrap();
    assert!(output.status.success(), "{:?}", output);
    let written = events(&fs::read(out).unwrap());
    assert_eq!(
        written
            .iter()
            .map(|e| e["type"].as_str().unwrap())
            .collect::<Vec<_>>(),
        [
            "run_requested",
            "agent_described",
            "agent_started",
            "assistant_message",
            "agent_stopped"
        ]
    );
    for event in written {
        assert!(
            avp::trajectory::parse_trajectory_event(event)
                .unwrap()
                .is_some()
        );
    }
    fs::write(&path, "not JSON").unwrap();
    let output = Command::new(agent())
        .args(["run", "--commission"])
        .arg(path)
        .args(["--out", "-"])
        .output()
        .unwrap();
    assert!(output.status.success());
    let written = events(&output.stdout);
    assert_eq!(written.last().unwrap()["type"], "error_occurred");
    assert_eq!(written[0]["data"]["commission"], "not JSON");
}

#[test]
fn crashes_and_missing_arguments_exit_nonzero() {
    let output = Command::new(agent())
        .args(["run", "--commission", &commission("crash"), "--out", "-"])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr).contains("example crash"));
    assert_eq!(
        Command::new(agent())
            .args(["run", "--out", "-"])
            .output()
            .unwrap()
            .status
            .code(),
        Some(2)
    );
}

#[test]
fn ping_does_not_load_the_agent_and_ndjson_reopens_each_event() {
    let dir = tempfile::tempdir().unwrap();
    let pong = dir.path().join("pong.json");
    assert_eq!(
        avp::agent_cli::main(
            |_, _, _| panic!("ping called run"),
            || panic!("ping called describe"),
            Some(vec![
                "agent".into(),
                "ping".into(),
                "--out".into(),
                pong.into_os_string()
            ])
        ),
        0
    );
    let path = dir.path().join("events.ndjson");
    let sink = avp::agent_cli::NdjsonSink::new(Some(&path)).unwrap();
    let mut rec = avp::recorder::Recorder::new(sink);
    rec.start(
        serde_json::from_value(json!({"prompt": "Hi", "model": {"provider": "p", "id": "m"}}))
            .unwrap(),
        None,
    )
    .unwrap();
    let archived = dir.path().join("archived.ndjson");
    fs::rename(&path, &archived).unwrap();
    rec.stop(avp::trajectory::StopReason::Converged, Value::Null)
        .unwrap();
    assert_eq!(
        events(&fs::read(archived).unwrap())[0]["type"],
        "agent_started"
    );
    assert_eq!(events(&fs::read(path).unwrap())[0]["type"], "agent_stopped");
}

#[cfg(unix)]
#[test]
fn both_signals_end_the_trajectory_and_exit_130() {
    for signal in ["-INT", "-TERM"] {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("live.ndjson");
        let mut child = Command::new(agent())
            .args(["run", "--commission", &commission("wait"), "--out"])
            .arg(&path)
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(10);
        while !fs::read_to_string(&path)
            .unwrap_or_default()
            .contains("agent_started")
        {
            if Instant::now() > deadline {
                let _ = child.kill();
                panic!("agent did not start")
            }
            thread::sleep(Duration::from_millis(10));
        }
        assert!(
            Command::new("kill")
                .args([signal, &child.id().to_string()])
                .status()
                .unwrap()
                .success()
        );
        while child.try_wait().unwrap().is_none() {
            if Instant::now() > deadline {
                let _ = child.kill();
                panic!("agent did not stop")
            }
            thread::sleep(Duration::from_millis(10));
        }
        assert_eq!(child.wait().unwrap().code(), Some(130));
        let written = events(&fs::read(path).unwrap());
        assert_eq!(written.last().unwrap()["data"]["reason"], "interrupted");
    }
}
