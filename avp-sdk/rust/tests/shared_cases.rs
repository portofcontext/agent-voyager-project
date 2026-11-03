use std::{
    cell::{Cell, RefCell},
    collections::HashSet,
    fs,
    path::Path,
    rc::Rc,
};

use avp::{
    recorder::{Recorder, RecorderError, RecorderOptions, ResponseOptions},
    trajectory::Event,
    utils::{preflight::check_commission, pricing::Prices, run_plan::plan_run},
};
use chrono::{DateTime, Duration, Utc};
use serde::de::DeserializeOwned;
use serde_json::{Value, json};

fn decode<T: DeserializeOwned>(value: &Value) -> T {
    serde_json::from_value(value.clone()).unwrap()
}
fn optional<T: DeserializeOwned>(call: &Value, field: &str) -> Option<T> {
    call.get(field).filter(|v| !v.is_null()).map(decode)
}
fn text<'a>(call: &'a Value, field: &str) -> &'a str {
    call[field].as_str().unwrap()
}

fn call<S: avp::recorder::EventSink>(rec: &mut Recorder<S>, call: &Value) -> avp::Result<()> {
    match text(call, "call") {
        "begin" => {
            rec.begin(call["received"].clone(), decode(&call["descriptor"]))?;
        }
        "start" => rec.start(decode(&call["started"]), optional(call, "meta"))?,
        "response" => rec.response(
            decode(&call["content"]),
            ResponseOptions {
                usage: optional(call, "usage"),
                model: optional(call, "model"),
                response_model: optional(call, "response_model"),
                finish_reasons: optional(call, "finish_reasons"),
                duration_ms: optional(call, "duration_ms"),
                subagent_invocation_id: optional(call, "subagent_invocation_id"),
                key: optional(call, "key"),
                meta: optional(call, "meta"),
            },
        )?,
        "usage" => rec.usage(
            decode(&call["usage"]),
            call.get("key").and_then(Value::as_str),
        )?,
        "close_response" => rec.close_response()?,
        "tool_returned" => rec.tool_returned(
            text(call, "call_id"),
            decode(&call["content"]),
            optional(call, "is_error"),
            optional(call, "structured_content"),
        )?,
        "subagent_invoked" => rec.subagent_invoked(
            text(call, "invocation_id"),
            text(call, "name"),
            optional(call, "subagent_input"),
            optional(call, "subagent_invocation_id"),
        )?,
        "subagent_returned" => rec.subagent_returned(
            text(call, "invocation_id"),
            text(call, "text"),
            optional(call, "reason").unwrap_or(avp::trajectory::StopReason::Converged),
            optional(call, "usage"),
        )?,
        "error" => rec.error(
            text(call, "code"),
            text(call, "message"),
            call.get("subagent_invocation_id").and_then(Value::as_str),
        )?,
        "stop" => rec.stop(decode(&call["reason"]), call["output"].clone())?,
        name => panic!("unknown call {name}"),
    }
    Ok(())
}

fn same(actual: &Value, expected: &Value) {
    if expected == "<any>" {
        assert!(actual.is_string());
        return;
    }
    match (actual, expected) {
        (Value::Number(a), Value::Number(e)) => {
            let (a, e) = (a.as_f64().unwrap(), e.as_f64().unwrap());
            assert!(
                (a - e).abs() <= 1e-12_f64.max(1e-9 * a.abs().max(e.abs())),
                "{a} != {e}"
            );
        }
        (Value::Object(a), Value::Object(e)) => {
            assert_eq!(
                a.keys().collect::<Vec<_>>(),
                e.keys().collect::<Vec<_>>(),
                "{actual}"
            );
            for (key, value) in e {
                same(&a[key], value);
            }
        }
        (Value::Array(a), Value::Array(e)) => {
            assert_eq!(a.len(), e.len(), "{actual}");
            for (a, e) in a.iter().zip(e) {
                same(a, e);
            }
        }
        _ => assert_eq!(actual, expected),
    }
}

#[test]
fn every_shared_recorder_case() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../testdata/recorder");
    for entry in fs::read_dir(root).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().is_none_or(|e| e != "json") {
            continue;
        }
        eprintln!("{}", path.display());
        let case: Value = serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        let start: DateTime<Utc> = "2026-01-01T00:00:00Z".parse().unwrap();
        let clock = Rc::new(Cell::new(start));
        let clock_fn = clock.clone();
        let events: Rc<RefCell<Vec<Event>>> = Rc::new(RefCell::new(Vec::new()));
        let sink_events = events.clone();
        let mut n = 0;
        let mut rec = Recorder::with_options(
            move |event| {
                sink_events.borrow_mut().push(event);
                Ok(())
            },
            RecorderOptions {
                run_id: Some("run-0".into()),
                prices: Some(decode::<Prices>(
                    &json!({"fetched": start, "models": case.get("prices").unwrap_or(&json!({}))}),
                )),
                now: Some(Box::new(move || clock_fn.get())),
                new_id: Some(Box::new(move || {
                    n += 1;
                    format!("event-{n}")
                })),
            },
        );
        for command in case["calls"].as_array().unwrap() {
            clock.set(start + Duration::milliseconds(command["t"].as_i64().unwrap()));
            let written = events.borrow().len();
            let result = call(&mut rec, command);
            if command["raises"] == true {
                assert!(result.unwrap_err().is::<RecorderError>(), "{}", command);
                assert_eq!(events.borrow().len(), written);
            } else {
                result.unwrap();
            }
        }
        let mut ids = HashSet::new();
        let actual: Vec<Value> = events
            .borrow()
            .iter()
            .map(|event| {
                let mut value = serde_json::to_value(event).unwrap();
                assert!(ids.insert(value["id"].clone().to_string()));
                value.as_object_mut().unwrap().remove("id");
                let time: DateTime<Utc> = value["time"].as_str().unwrap().parse().unwrap();
                value.as_object_mut().unwrap().remove("time");
                value["t"] = json!((time - start).num_milliseconds());
                value
            })
            .collect();
        same(&json!(actual), &case["events"]);
    }
}

#[test]
fn every_shared_run_plan_case() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../testdata/run_plan");
    for entry in fs::read_dir(root).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().is_none_or(|e| e != "json") {
            continue;
        }
        let case: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
        let (commission, descriptor) = (decode(&case["commission"]), decode(&case["descriptor"]));
        assert_eq!(check_commission(&commission, &descriptor), None);
        same(
            &serde_json::to_value(plan_run(&commission, &descriptor)).unwrap(),
            &case["plan"],
        );
    }
}

#[test]
fn empty_values_follow_the_python_recorder() {
    let events = Rc::new(RefCell::new(Vec::new()));
    let written = events.clone();
    let mut next_id = 0;
    let mut rec = Recorder::with_options(
        move |event| {
            written.borrow_mut().push(serde_json::to_value(event)?);
            Ok(())
        },
        RecorderOptions {
            run_id: Some(String::new()),
            new_id: Some(Box::new(move || {
                next_id += 1;
                format!("id-{next_id}")
            })),
            ..Default::default()
        },
    );
    assert_eq!(rec.run_id, "id-1");
    rec.start(
        decode(&json!({"prompt": "Hi", "model": {"provider": "p", "id": "m"}})),
        None,
    )
    .unwrap();
    rec.response(
        decode(&json!([{"type": "text", "text": "Hi"}])),
        ResponseOptions {
            meta: Some(Default::default()),
            ..Default::default()
        },
    )
    .unwrap();
    rec.subagent_invoked("s", "helper", None, Some(String::new()))
        .unwrap();
    rec.stop(avp::trajectory::StopReason::Converged, Value::Null)
        .unwrap();
    let events = events.borrow();
    assert!(events[1].get("meta").is_none());
    assert_eq!(events[2]["data"]["subagent_invocation_id"], "");
}
