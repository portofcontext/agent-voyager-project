use avp::{
    commission::Commission,
    descriptor::{AgentDescriptor, Tool},
    trajectory::{ErrorOccurred, Usage, parse_trajectory_event},
};
use serde_json::{Value, json};

fn commission() -> Value {
    json!({"avp_version": "0.1", "run_id": "r", "prompt": "Hi", "model": {"provider": "openai", "id": "m"}})
}

#[test]
fn commission_deserialization_checks_the_schema() {
    let mut invalid = Vec::new();
    let mut value = commission();
    value["extra"] = json!(1);
    invalid.push(value);
    let mut value = commission();
    value["avp_version"] = json!("0.2");
    invalid.push(value);
    let mut value = commission();
    value["model"]["provider"] = json!("Invalid/provider");
    invalid.push(value);
    let mut value = commission();
    value["output_schema"] = json!({"type": "array"});
    invalid.push(value);
    let mut value = commission();
    value["agents"] = json!({"Bad Name": {}});
    invalid.push(value);
    let mut value = commission();
    value["mcp_servers"] = json!([{"id": "s", "type": "stdio", "command": []}]);
    invalid.push(value);
    let mut value = commission();
    value["mcp_servers"] = json!([{"id": "s", "type": "stdio", "command": ["echo"], "env": {"KEY": {"proxy": "key"}}}]);
    invalid.push(value);
    let mut value = commission();
    value["skills"] = json!([{"name": "lint", "files": {}}]);
    invalid.push(value);
    let mut value = commission();
    value["skills"] = json!([{"name": "lint", "files": {"SKILL.md": 7}}]);
    invalid.push(value);
    for value in invalid {
        assert!(
            serde_json::from_value::<Commission>(value.clone()).is_err(),
            "{value}"
        );
    }
}

#[test]
fn open_wire_objects_keep_other_standards_fields() {
    let value = json!({"avp_version": "0.1", "agent_name": "demo", "agent_version": "1",
        "tools": [{"name": "read", "title": "Read", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
            "annotations": {"readOnlyHint": true}, "_meta": {"x": null}}],
        "skills": [{"name": "review", "description": "Review", "metadata": {"version": "1"}}]});
    let descriptor: AgentDescriptor = serde_json::from_value(value.clone()).unwrap();
    assert_eq!(serde_json::to_value(descriptor).unwrap(), value);
    assert!(serde_json::from_value::<Tool>(json!({"name": "bad", "inputSchema": {}})).is_err());
}

#[test]
fn events_validate_time_usage_and_content_and_skip_unknown_types() {
    let event = json!({"avp_version": "0.1", "id": "e", "run_id": "r", "time": "2026-01-01T00:00:00Z",
        "type": "assistant_message", "data": {"model": {"provider": "p", "id": "m"},
        "duration_ms": 0, "content": [{"type": "text", "text": "hi", "provider_field": {"x": true}}],
        "usage": {"input_tokens": 1, "output_tokens": 2, "cost_usd": 0.0, "cost_source": "unknown"}}});
    let parsed = parse_trajectory_event(event.clone()).unwrap().unwrap();
    assert_eq!(serde_json::to_value(parsed).unwrap(), event);
    for time in [
        "2026-01-01",
        "2026-01-01 00:00:00Z",
        "2026-01-01T00:00:00",
        "2026-02-30T00:00:00Z",
    ] {
        let mut bad = event.clone();
        bad["time"] = json!(time);
        assert!(parse_trajectory_event(bad).is_err(), "{time}");
    }
    let mut bad = event.clone();
    bad["data"]["usage"]["cost_usd"] = json!(-1);
    assert!(parse_trajectory_event(bad).is_err());
    let mut bad = event.clone();
    bad["data"]["duration_ms"] = json!(-1);
    assert!(parse_trajectory_event(bad).is_err());
    assert!(
        parse_trajectory_event(json!({"type": "future_event"}))
            .unwrap()
            .is_none()
    );
    assert!(parse_trajectory_event(json!({"type": "agent_started"})).is_err());
    assert!(serde_json::from_value::<Usage>(json!({"input_tokens": 0, "output_tokens": 0, "cost_usd": -1, "cost_source": "reported"})).is_err());
}

#[test]
fn future_error_codes_become_unknown() {
    let data = json!({"error_code": "future_code", "error_message": "new failure"});
    let parsed: ErrorOccurred = serde_json::from_value(data.clone()).unwrap();
    assert_eq!(
        serde_json::to_value(parsed).unwrap()["error_code"],
        "unknown"
    );
    let event = json!({"avp_version": "0.1", "id": "e", "run_id": "r", "time": "2026-01-01T00:00:00Z",
        "type": "error_occurred", "data": data});
    let parsed = parse_trajectory_event(event).unwrap().unwrap();
    assert_eq!(
        serde_json::to_value(parsed).unwrap()["data"]["error_code"],
        "unknown"
    );
}

#[test]
fn refused_commissions_remain_readable_in_run_requested() {
    for received in [
        json!("invalid JSON"),
        json!({"run_id": "r", "extra": null}),
        json!([1, 2]),
    ] {
        let event = json!({"avp_version": "0.1", "id": "e", "run_id": "r", "time": "2026-01-01T00:00:00Z",
            "type": "run_requested", "data": {"commission": received}});
        let parsed = parse_trajectory_event(event.clone()).unwrap().unwrap();
        assert_eq!(serde_json::to_value(parsed).unwrap(), event);
    }
}
