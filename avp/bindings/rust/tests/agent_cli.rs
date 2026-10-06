//! Seam test for the stock agent command line: argv in, Commission through the
//! agent's `run`, NDJSON trajectory out (and `ping` / `describe`).

use avp::agent_cli::{dispatch, BoxError};
use avp::recorder::{AssistantOpts, Recorder, RecorderOptions, StartInfo};
use avp::trajectory::{AgentDescriptor, AvpContentItem, StopReason, Usage};
use avp::{Commission, FileSink};
use serde_json::{json, Value};

fn descriptor() -> AgentDescriptor {
    serde_json::from_value(
        json!({"agent_name": "echo", "agent_version": "0.0.1", "spec_version": "0.1"}),
    )
    .unwrap()
}

fn describe() -> Result<AgentDescriptor, BoxError> {
    Ok(descriptor())
}

/// A one-turn agent that echoes its system prompt and prompt.
fn run(commission: Commission, sink: FileSink) -> Result<(), BoxError> {
    let mut rec = Recorder::new(
        sink,
        RecorderOptions {
            run_id: Some(commission.run_id.to_string()),
            ..Default::default()
        },
    );
    rec.prelude(Some(&commission), &descriptor())?;
    rec.start(StartInfo {
        prompt: commission.prompt.clone(),
        ..Default::default()
    })?;
    let text = format!(
        "{}|{}",
        commission.system_prompt.clone().unwrap_or_default(),
        commission.prompt.clone().unwrap_or_default()
    );
    let block: AvpContentItem = serde_json::from_value(json!({"type": "text", "text": text}))?;
    let usage = Usage {
        input_tokens: 3,
        output_tokens: 1,
        cache_read_input_tokens: None,
        cache_creation_input_tokens: None,
        reasoning_output_tokens: None,
    };
    rec.assistant(vec![block], Some(usage), AssistantOpts::default())?;
    rec.stop(StopReason::Converged, Some(Value::String(text)))?;
    Ok(())
}

fn args(v: &[&str]) -> Vec<String> {
    v.iter().map(|s| s.to_string()).collect()
}

fn tmp(name: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!("avp-agent-cli-{}-{name}", std::process::id()))
}

#[test]
fn ping_writes_pong() {
    let out = tmp("pong.json");
    dispatch(
        &args(&["ping", "--out", out.to_str().unwrap()]),
        describe,
        run,
    )
    .unwrap();
    let v: Value = serde_json::from_str(&std::fs::read_to_string(&out).unwrap()).unwrap();
    assert_eq!(v, json!({"type": "pong"}));
}

#[test]
fn describe_writes_descriptor() {
    let out = tmp("d.json");
    dispatch(
        &args(&["describe", &format!("--out={}", out.display())]),
        describe,
        run,
    )
    .unwrap();
    let v: Value = serde_json::from_str(&std::fs::read_to_string(&out).unwrap()).unwrap();
    assert_eq!(v["agent_name"], "echo");
}

#[test]
fn run_streams_trajectory_and_seeds_built_ins() {
    let commission = tmp("c.json");
    std::fs::write(
        &commission,
        json!({"schema_version": "0.1", "run_id": "r1", "model": "x/m", "prompt": "hi"})
            .to_string(),
    )
    .unwrap();
    let built_in =
        json!({"system_prompt": "be brief", "prompt": "ignored: commission wins"}).to_string();
    let out = tmp("t.jsonl");
    let argv = args(&[
        "run",
        "--commission",
        commission.to_str().unwrap(),
        "--built-in",
        &built_in,
        "--out",
        out.to_str().unwrap(),
    ]);
    dispatch(&argv, describe, run).unwrap();
    let events: Vec<Value> = std::fs::read_to_string(&out)
        .unwrap()
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect();
    let types: Vec<&str> = events.iter().map(|e| e["type"].as_str().unwrap()).collect();
    assert_eq!(
        types,
        [
            "avp.run_requested",
            "avp.agent_described",
            "avp.agent_started",
            "avp.assistant_message",
            "avp.agent_stopped"
        ]
    );
    assert_eq!(events[4]["data"]["avp.output"], "be brief|hi");
    assert!(events.iter().all(|e| e["subject"] == "r1"));
}

#[test]
fn unknown_command_is_a_usage_error() {
    let err = dispatch(&args(&["fly"]), describe, run).unwrap_err();
    assert!(matches!(err, avp::agent_cli::CliError::Usage(_)));
}
