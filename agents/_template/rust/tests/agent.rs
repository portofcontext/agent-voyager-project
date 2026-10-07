//! Seam test: the agent's command line drives a run end to end and the
//! trajectory parses as AVP. Keep this test when you replace the harness;
//! point it at a recorded or stubbed SDK stream.

use avp::agent_cli::dispatch;
use serde_json::{json, Value};

fn run(commission: Value) -> Vec<Value> {
    let out = std::env::temp_dir().join(format!(
        "avp-template-{}-{}.jsonl",
        std::process::id(),
        commission["run_id"].as_str().unwrap()
    ));
    let argv: Vec<String> = [
        "run",
        "--commission",
        &commission.to_string(),
        "--out",
        out.to_str().unwrap(),
    ]
    .iter()
    .map(|s| s.to_string())
    .collect();
    dispatch(
        &argv,
        || Ok(avp_agent_template::agent::describe()),
        |c, sink| Ok(avp_agent_template::agent::run(&c, sink)?),
    )
    .unwrap();
    std::fs::read_to_string(&out)
        .unwrap()
        .lines()
        .map(|l| {
            let v: Value = serde_json::from_str(l).unwrap();
            let _: avp::Event = serde_json::from_value(v.clone()).expect("valid AVP event");
            v
        })
        .collect()
}

fn types(events: &[Value]) -> Vec<&str> {
    events.iter().map(|e| e["type"].as_str().unwrap()).collect()
}

#[test]
fn tool_round_trip() {
    let events = run(
        json!({"schema_version": "0.1", "run_id": "r1", "model": "openai/gpt-4o-mini", "prompt": "use a tool"}),
    );
    assert_eq!(
        types(&events),
        [
            "avp.run_requested",
            "avp.agent_described",
            "avp.agent_started",
            "avp.assistant_message",
            "avp.tool_invoked",
            "avp.tool_returned",
            "avp.assistant_message",
            "avp.agent_stopped"
        ]
    );
    assert_eq!(events[3]["data"]["avp.cost.source"], "computed");
}

#[test]
fn unknown_allowlisted_tool_fails_fast() {
    let events = run(
        json!({"schema_version": "0.1", "run_id": "r2", "model": "openai/gpt-4o-mini",
        "enabled_builtin_tools": {"avp-agent-template": ["nope"]}}),
    );
    assert_eq!(
        types(&events)[2..],
        ["avp.error_occurred", "avp.agent_stopped"]
    );
    assert_eq!(events[2]["data"]["avp.error.code"], "commission_collision");
}
