//! Run the shared recorder vectors against the Rust `Recorder`. Contract:
//! `avp/core/conformance/src/avp_conformance/recorder/v0.1/README.md`.

use std::cell::RefCell;
use std::collections::HashMap;
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::sync::Arc;

use avp::recorder::{AssistantOpts, Clock, Ids, Recorder, RecorderOptions, StartInfo};
use avp::sink::Sink;
use avp::trajectory::{
    AgentDescriptor, AvpContentItem, ErrorCode, StopReason, SubagentUsage, Usage,
};
use avp::{Commission, Event, ModelPrice, PriceTable};
use chrono::{DateTime, Duration, SecondsFormat, Utc};
use serde::de::DeserializeOwned;
use serde_json::{Map, Value};

const TRACE_ID: &str = "0af7651916cd43dd8448eb211c80319c";

fn vectors_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../core/conformance/src/avp_conformance/recorder/v0.1")
}

struct VectorClock(Arc<AtomicI64>);

impl Clock for VectorClock {
    fn now_iso(&self) -> String {
        let epoch: DateTime<Utc> = "2026-01-01T00:00:00Z".parse().unwrap();
        (epoch + Duration::milliseconds(self.0.load(Ordering::SeqCst)))
            .to_rfc3339_opts(SecondsFormat::Millis, true)
    }
    fn monotonic(&self) -> f64 {
        self.0.load(Ordering::SeqCst) as f64 / 1000.0
    }
}

#[derive(Default)]
struct VectorIds {
    spans: AtomicU64,
    events: AtomicU64,
}

impl Ids for VectorIds {
    fn trace_id(&self) -> String {
        TRACE_ID.to_string()
    }
    fn span_id(&self) -> String {
        format!("{:016x}", self.spans.fetch_add(1, Ordering::SeqCst) + 1)
    }
    fn event_id(&self) -> String {
        format!("evt-{}", self.events.fetch_add(1, Ordering::SeqCst) + 1)
    }
}

#[derive(Clone, Default)]
struct Capture(Rc<RefCell<Vec<Value>>>);

impl Sink for Capture {
    fn emit(&self, event: &Event) -> std::io::Result<()> {
        self.0
            .borrow_mut()
            .push(serde_json::to_value(event).unwrap());
        Ok(())
    }
}

fn opt<T: DeserializeOwned>(a: &Value, key: &str) -> Option<T> {
    a.get(key)
        .filter(|v| !v.is_null())
        .map(|v| serde_json::from_value(v.clone()).unwrap())
}

fn req<T: DeserializeOwned>(a: &Value, key: &str) -> T {
    opt(a, key).unwrap_or_else(|| panic!("missing {key}"))
}

fn apply(rec: &mut Recorder<Capture>, op: &str, a: &Value) {
    match op {
        "prelude" => {
            let commission: Option<Commission> = opt(a, "commission");
            let descriptor: AgentDescriptor = req(a, "descriptor");
            rec.prelude(commission.as_ref(), &descriptor).unwrap();
        }
        "start" => rec
            .start(StartInfo {
                request_model: opt(a, "request_model"),
                prompt: opt(a, "prompt"),
                system_prompt: opt(a, "system_prompt"),
                tools: opt(a, "tools"),
                mcp_servers: opt(a, "mcp_servers"),
                skills: opt(a, "skills"),
                subagents: opt(a, "subagents"),
                session_id: opt(a, "session_id"),
                thread_id: opt(a, "thread_id"),
                tags: opt(a, "tags"),
                meta: opt(a, "meta"),
            })
            .unwrap(),
        "assistant" => {
            let content: Vec<AvpContentItem> = req(a, "content");
            let usage: Option<Usage> = opt(a, "usage");
            rec.assistant(
                content,
                usage,
                AssistantOpts {
                    model: opt(a, "model"),
                    request_model: opt(a, "request_model"),
                    turn_key: opt(a, "turn_key"),
                    finish_reasons: opt(a, "finish_reasons"),
                    meta: opt(a, "meta"),
                    cost_usd: opt(a, "cost_usd"),
                    duration_ms: opt(a, "duration_ms"),
                },
            )
            .unwrap();
        }
        "usage" => {
            let usage: Usage = req(a, "usage");
            let key: Option<String> = opt(a, "turn_key");
            rec.usage(
                usage,
                key.as_deref(),
                opt(a, "cost_usd"),
                opt(a, "duration_ms"),
            );
        }
        "close_turn" => rec.close_turn().unwrap(),
        "tool_result" => {
            let call_id: String = req(a, "call_id");
            let is_error: Option<bool> = opt(a, "is_error");
            let structured: Option<Map<String, Value>> = opt(a, "structured_content");
            rec.tool_result(
                &call_id,
                a["content"].clone(),
                is_error.unwrap_or(false),
                structured,
            )
            .unwrap();
        }
        "subagent_start" => {
            let id: String = req(a, "invocation_id");
            let name: String = req(a, "name");
            let description: Option<String> = opt(a, "description");
            rec.subagent_start(&id, &name, opt(a, "input"), description.as_deref())
                .unwrap();
        }
        "subagent_result" => {
            let id: String = req(a, "invocation_id");
            let text: String = req(a, "text");
            let reason: StopReason = opt(a, "reason").unwrap_or(StopReason::Converged);
            let usage: Option<SubagentUsage> = opt(a, "usage");
            rec.subagent_result(&id, &text, reason, usage, opt(a, "structured"))
                .unwrap();
        }
        "error" => {
            let code: ErrorCode = req(a, "code");
            let message: String = req(a, "message");
            rec.error(code, &message).unwrap();
        }
        "stop" => {
            let reason: StopReason = req(a, "reason");
            rec.stop(reason, opt(a, "output")).unwrap();
        }
        other => panic!("unknown recorder op {other:?}"),
    }
}

/// Rename event ids and span ids by order of first appearance on the wire.
fn normalize(events: &[Value]) -> Vec<Value> {
    let mut names: HashMap<String, String> = HashMap::new();
    let mut counts: HashMap<&'static str, usize> = HashMap::new();
    let mut name = |value: &Value, prefix: &'static str| -> Value {
        let v = value.as_str().unwrap().to_string();
        if v == "0000000000000000" {
            return Value::String(v);
        }
        let n = names.entry(v).or_insert_with(|| {
            let c = counts.entry(prefix).or_default();
            *c += 1;
            format!("{prefix}-{c}")
        });
        Value::String(n.clone())
    };
    events
        .iter()
        .map(|e| {
            let mut e = e.clone();
            e["id"] = name(&e["id"], "evt");
            let span = name(&e["data"]["span_id"], "span");
            let parent = name(&e["data"]["parent_span_id"], "span");
            e["data"]["span_id"] = span;
            e["data"]["parent_span_id"] = parent;
            e
        })
        .collect()
}

fn same(got: &Value, want: &Value, path: &str) -> Result<(), String> {
    match (got, want) {
        (Value::Number(g), Value::Number(w)) => {
            let (g, w) = (g.as_f64().unwrap(), w.as_f64().unwrap());
            if (g - w).abs() <= 1e-12 {
                Ok(())
            } else {
                Err(format!("{path}: {g} != {w}"))
            }
        }
        (Value::Object(g), Value::Object(w)) => {
            let mut keys: Vec<&String> = g.keys().chain(w.keys()).collect();
            keys.sort();
            keys.dedup();
            for k in keys {
                match (g.get(k), w.get(k)) {
                    (Some(a), Some(b)) => same(a, b, &format!("{path}.{k}"))?,
                    (a, b) => return Err(format!("{path}.{k}: got {a:?}, want {b:?}")),
                }
            }
            Ok(())
        }
        (Value::Array(g), Value::Array(w)) if g.len() == w.len() => {
            for (i, (a, b)) in g.iter().zip(w).enumerate() {
                same(a, b, &format!("{path}[{i}]"))?;
            }
            Ok(())
        }
        _ if got == want => Ok(()),
        _ => Err(format!("{path}: got {got}, want {want}")),
    }
}

fn run(vector: &Value) -> Vec<Value> {
    let cfg = &vector["recorder"];
    let t = Arc::new(AtomicI64::new(0));
    let capture = Capture::default();
    let prices: PriceTable = cfg
        .get("prices")
        .map(|p| serde_json::from_value::<HashMap<String, ModelPrice>>(p.clone()).unwrap())
        .unwrap_or_default();
    let mut rec = Recorder::new(
        capture.clone(),
        RecorderOptions {
            run_id: opt(cfg, "run_id"),
            provider: opt(cfg, "provider"),
            prices,
            dispatch_target: None,
            clock: Some(Box::new(VectorClock(t.clone()))),
            ids: Some(Box::new(VectorIds::default())),
        },
    );
    for call in vector["calls"].as_array().unwrap() {
        t.store(call["t"].as_i64().unwrap(), Ordering::SeqCst);
        apply(&mut rec, call["op"].as_str().unwrap(), call);
    }
    let events = capture.0.borrow().clone();
    normalize(&events)
}

#[test]
fn recorder_vectors() {
    let mut paths: Vec<PathBuf> = std::fs::read_dir(vectors_dir())
        .expect("vectors dir")
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    paths.sort();
    assert!(
        paths.len() >= 10,
        "expected the shared vectors, found {}",
        paths.len()
    );
    let mut failures = Vec::new();
    for path in &paths {
        let vector: Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
        let name = vector["name"].as_str().unwrap().to_string();
        let got = run(&vector);
        let want = vector["expected"].as_array().unwrap();
        let types = |v: &[Value]| v.iter().map(|e| e["type"].to_string()).collect::<Vec<_>>();
        if types(&got) != types(want) {
            failures.push(format!(
                "{name}: types {:?} != {:?}",
                types(&got),
                types(want)
            ));
            continue;
        }
        for (i, (g, w)) in got.iter().zip(want).enumerate() {
            if let Err(e) = same(g, w, &format!("event[{i}]")) {
                failures.push(format!("{name}: {e}"));
                break;
            }
        }
    }
    assert!(
        failures.is_empty(),
        "{} vector(s) failed:\n{}",
        failures.len(),
        failures.join("\n")
    );
}
