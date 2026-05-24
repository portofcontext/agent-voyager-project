//! Cross-provider AVP eval harness for the Goose connector.
//!
//! Runs a matrix of Commission setups across providers and scores the result.
//! Each case is a fresh `avp-goose-run` subprocess (Goose's `Config` /
//! `SessionManager` are process-global `LazyLock`s, so isolation has to be
//! per-process), with `GOOSE_PROVIDER` set for the target. The harness captures
//! the NDJSON trajectory, schema-validates every event against the canonical
//! AVP schema, runs declarative evals, and prints a pass/fail matrix with cost.
//!
//! Credentials come from the environment / OS keychain, same as the CLI:
//! Anthropic from the keychain, OpenRouter from `OPENROUTER_API_KEY` (export it
//! before running). Live runs cost real money; setups use tiny prompts.

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde_json::{json, Value};

/// Canonical AVP trajectory-event schema (source of truth for conformance).
const TRAJECTORY_SCHEMA: &str = include_str!("../../../../spec/v0.1/trajectory.schema.json");

/// A provider/model the matrix runs every setup against.
struct Target {
    label: &'static str,
    provider: &'static str,
    model: &'static str,
}

/// A Commission template plus the evals its trajectory must satisfy.
struct Setup {
    name: &'static str,
    prompt: &'static str,
    builtins: &'static [&'static str],
    output_schema: Option<Value>,
    evals: &'static [Eval],
}

/// A declarative assertion over a captured trajectory.
#[derive(Clone, Copy)]
enum Eval {
    /// Every event validates against the AVP trajectory schema.
    SchemaValid,
    /// At least one event of this `type` is present.
    HasEvent(&'static str),
    /// No `tool_returned` reports an error.
    NoToolErrors,
    /// The run ends `agent_stopped` with reason `converged`.
    StopConverged,
    /// Total computed cost across assistant turns is > 0.
    CostPositive,
    /// Some assistant message's text contains this substring (case-insensitive).
    AnswerContains(&'static str),
}

impl Eval {
    fn name(&self) -> String {
        match self {
            Eval::SchemaValid => "schema_valid".into(),
            Eval::HasEvent(t) => format!("has[{t}]"),
            Eval::NoToolErrors => "no_tool_errors".into(),
            Eval::StopConverged => "stop_converged".into(),
            Eval::CostPositive => "cost_positive".into(),
            Eval::AnswerContains(s) => format!("answer~\"{s}\""),
        }
    }
}

fn targets() -> Vec<Target> {
    vec![
        Target {
            label: "Sonnet · Anthropic",
            provider: "anthropic",
            model: "claude-sonnet-4-6",
        },
        Target {
            label: "GPT-4o · OpenRouter",
            provider: "openrouter",
            model: "openai/gpt-4o",
        },
    ]
}

fn setups() -> Vec<Setup> {
    vec![
        Setup {
            name: "simple",
            prompt: "Reply with exactly this and nothing else: AVP-WORKS",
            builtins: &[],
            output_schema: None,
            evals: &[
                Eval::SchemaValid,
                Eval::StopConverged,
                Eval::HasEvent("avp.assistant_message"),
                Eval::CostPositive,
                Eval::AnswerContains("AVP-WORKS"),
            ],
        },
        Setup {
            name: "tool",
            prompt: "Use the shell tool to run exactly: echo avp-tool-ok\n\
                     Then reply with exactly what it printed.",
            builtins: &["developer"],
            output_schema: None,
            evals: &[
                Eval::SchemaValid,
                Eval::HasEvent("avp.tool_invoked"),
                Eval::HasEvent("avp.tool_returned"),
                Eval::NoToolErrors,
                Eval::StopConverged,
                Eval::CostPositive,
                Eval::AnswerContains("avp-tool-ok"),
            ],
        },
        Setup {
            name: "structured",
            prompt: "The capital of France is Paris and it has roughly 2 million people. \
                     Return that as JSON.",
            builtins: &[],
            output_schema: Some(json!({
                "type": "object",
                "properties": {
                    "city": { "type": "string" },
                    "population_millions": { "type": "number" }
                },
                "required": ["city", "population_millions"],
                "additionalProperties": false
            })),
            evals: &[Eval::SchemaValid, Eval::StopConverged, Eval::CostPositive],
        },
    ]
}

fn build_commission(setup: &Setup, target: &Target, run_id: &str) -> Value {
    let mut c = json!({
        "schema_version": "0.1",
        "run_id": run_id,
        "model": target.model,
        "prompt": setup.prompt,
    });
    if !setup.builtins.is_empty() {
        c["enabled_builtin_tools"] = json!(setup.builtins);
    }
    if let Some(schema) = &setup.output_schema {
        c["output_schema"] = schema.clone();
    }
    c
}

/// Outcome of one (setup × target) live run.
struct CaseResult {
    setup: &'static str,
    target: &'static str,
    /// Subprocess error (missing key, provider failure); `None` if it ran.
    spawn_err: Option<String>,
    events: usize,
    turns: usize,
    cost: f64,
    in_tokens: u64,
    out_tokens: u64,
    stop: Option<String>,
    /// One (eval-name, pass/fail-reason) per declared eval.
    evals: Vec<(String, Result<(), String>)>,
}

impl CaseResult {
    fn passed(&self) -> bool {
        self.spawn_err.is_none() && self.evals.iter().all(|(_, r)| r.is_ok())
    }
    fn score(&self) -> (usize, usize) {
        (
            self.evals.iter().filter(|(_, r)| r.is_ok()).count(),
            self.evals.len(),
        )
    }
}

fn run_case(
    bin: &Path,
    setup: &Setup,
    target: &Target,
    out_dir: &Path,
    validator: &jsonschema::Validator,
) -> CaseResult {
    let run_id = format!("eval-{}-{}", setup.name, target.provider);
    let commission = build_commission(setup, target, &run_id);

    let fail = |err: String| CaseResult {
        setup: setup.name,
        target: target.label,
        spawn_err: Some(err),
        events: 0,
        turns: 0,
        cost: 0.0,
        in_tokens: 0,
        out_tokens: 0,
        stop: None,
        evals: Vec::new(),
    };

    let mut child = match Command::new(bin)
        .env("GOOSE_PROVIDER", target.provider)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => return fail(format!("spawn {}: {e}", bin.display())),
    };
    if let Err(e) = child
        .stdin
        .take()
        .expect("piped stdin")
        .write_all(commission.to_string().as_bytes())
    {
        return fail(format!("write stdin: {e}"));
    }
    let output = match child.wait_with_output() {
        Ok(o) => o,
        Err(e) => return fail(format!("wait: {e}")),
    };
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let tail = stderr.lines().rev().take(3).collect::<Vec<_>>();
        return fail(tail.into_iter().rev().collect::<Vec<_>>().join(" | "));
    }

    // Parse NDJSON and save the raw trajectory for inspection.
    let stdout = String::from_utf8_lossy(&output.stdout);
    let _ = std::fs::write(out_dir.join(format!("{run_id}.ndjson")), stdout.as_bytes());
    let events: Vec<Value> = stdout
        .lines()
        .filter(|l| !l.trim().is_empty())
        .filter_map(|l| serde_json::from_str(l).ok())
        .collect();

    let evals = setup
        .evals
        .iter()
        .map(|e| (e.name(), eval(e, &events, validator)))
        .collect::<Vec<_>>();

    CaseResult {
        setup: setup.name,
        target: target.label,
        spawn_err: None,
        events: events.len(),
        turns: count_type(&events, "avp.assistant_message"),
        cost: total_cost(&events),
        in_tokens: total_tokens(&events, "input_tokens"),
        out_tokens: total_tokens(&events, "output_tokens"),
        stop: stop_reason(&events),
        evals,
    }
}

fn eval(e: &Eval, events: &[Value], validator: &jsonschema::Validator) -> Result<(), String> {
    match e {
        Eval::SchemaValid => {
            for ev in events {
                if !validator.is_valid(ev) {
                    let errs: Vec<String> =
                        validator.iter_errors(ev).map(|e| e.to_string()).collect();
                    return Err(format!("{} invalid: {}", ty(ev), errs.join("; ")));
                }
            }
            Ok(())
        }
        Eval::HasEvent(t) => events
            .iter()
            .any(|ev| ty(ev) == *t)
            .then_some(())
            .ok_or_else(|| format!("no {t}")),
        Eval::NoToolErrors => {
            let bad = events.iter().any(|ev| {
                ty(ev) == "avp.tool_returned"
                    && ev["data"]["avp.tool.is_error"].as_bool() == Some(true)
            });
            (!bad)
                .then_some(())
                .ok_or_else(|| "a tool returned an error".into())
        }
        Eval::StopConverged => {
            let reason = stop_reason(events);
            (reason.as_deref() == Some("converged"))
                .then_some(())
                .ok_or_else(|| format!("stop reason {reason:?}"))
        }
        Eval::CostPositive => {
            let cost = total_cost(events);
            (cost > 0.0)
                .then_some(())
                .ok_or_else(|| format!("cost {cost}"))
        }
        Eval::AnswerContains(s) => {
            let needle = s.to_lowercase();
            let found = events
                .iter()
                .filter(|ev| ty(ev) == "avp.assistant_message")
                .any(|ev| {
                    ev["data"]["avp.content"]
                        .as_array()
                        .into_iter()
                        .flatten()
                        .filter_map(|b| b["text"].as_str())
                        .any(|t| t.to_lowercase().contains(&needle))
                });
            found
                .then_some(())
                .ok_or_else(|| format!("no answer contains {s:?}"))
        }
    }
}

fn ty(ev: &Value) -> &str {
    ev["type"].as_str().unwrap_or("")
}

fn count_type(events: &[Value], t: &str) -> usize {
    events.iter().filter(|ev| ty(ev) == t).count()
}

fn total_cost(events: &[Value]) -> f64 {
    events
        .iter()
        .filter(|ev| ty(ev) == "avp.assistant_message")
        .filter_map(|ev| ev["data"]["avp.cost_usd"].as_f64())
        .sum()
}

fn total_tokens(events: &[Value], field: &str) -> u64 {
    events
        .iter()
        .filter(|ev| ty(ev) == "avp.assistant_message")
        .filter_map(|ev| ev["data"]["avp.usage"][field].as_u64())
        .sum()
}

fn stop_reason(events: &[Value]) -> Option<String> {
    events
        .iter()
        .find(|ev| ty(ev) == "avp.agent_stopped")
        .and_then(|ev| ev["data"]["avp.reason"].as_str())
        .map(String::from)
}

/// Locate the sibling `avp-goose-run` built alongside this binary.
fn avp_goose_run_path() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("avp-goose-run")))
        .unwrap_or_else(|| PathBuf::from("avp-goose-run"))
}

fn print_case_line(r: &CaseResult) {
    if let Some(err) = &r.spawn_err {
        eprintln!("  FAIL (run error): {err}");
        return;
    }
    let (pass, total) = r.score();
    eprintln!(
        "  {} {pass}/{total} evals · {} events / {} turns · ${:.4} · {} in / {} out · stop={}",
        if r.passed() { "PASS" } else { "FAIL" },
        r.events,
        r.turns,
        r.cost,
        r.in_tokens,
        r.out_tokens,
        r.stop.as_deref().unwrap_or("?"),
    );
}

fn print_report(results: &[CaseResult], setups: &[Setup], targets: &[Target]) {
    println!("\n{:=<78}", "");
    println!("AVP × Goose cross-provider eval matrix");
    println!("{:=<78}", "");

    let col = 30;
    print!("{:<14}", "setup");
    for t in targets {
        print!("{:<col$}", t.label, col = col);
    }
    println!();
    for setup in setups {
        print!("{:<14}", setup.name);
        for target in targets {
            let r = results
                .iter()
                .find(|r| r.setup == setup.name && r.target == target.label)
                .expect("result present");
            let cell = if r.spawn_err.is_some() {
                "ERR (run failed)".to_string()
            } else {
                let (pass, total) = r.score();
                format!(
                    "{} {pass}/{total}  ${:.4}",
                    if r.passed() { "PASS" } else { "FAIL" },
                    r.cost
                )
            };
            print!("{cell:<col$}", col = col);
        }
        println!();
    }

    // Detail for anything that did not fully pass.
    let problems: Vec<&CaseResult> = results.iter().filter(|r| !r.passed()).collect();
    if !problems.is_empty() {
        println!("\n{:-<78}", "");
        println!("failures");
        println!("{:-<78}", "");
        for r in problems {
            println!("• {} × {}", r.setup, r.target);
            if let Some(err) = &r.spawn_err {
                println!("    run error: {err}");
            }
            for (name, res) in &r.evals {
                if let Err(why) = res {
                    println!("    {name}: {why}");
                }
            }
        }
    }

    let passed = results.iter().filter(|r| r.passed()).count();
    let total_cost: f64 = results.iter().map(|r| r.cost).sum();
    println!("\n{:=<78}", "");
    println!(
        "{}/{} cases passed · total spend ${:.4} · trajectories in {}/avp-eval/",
        passed,
        results.len(),
        total_cost,
        std::env::temp_dir().display()
    );
    println!("{:=<78}", "");
}

fn main() {
    let out_dir = std::env::temp_dir().join("avp-eval");
    if let Err(e) = std::fs::create_dir_all(&out_dir) {
        eprintln!("cannot create {}: {e}", out_dir.display());
        std::process::exit(1);
    }
    let bin = avp_goose_run_path();
    let schema: Value = serde_json::from_str(TRAJECTORY_SCHEMA).expect("schema parses");
    let validator = jsonschema::validator_for(&schema).expect("schema compiles");

    let targets = targets();
    let setups = setups();
    let mut results = Vec::new();
    for setup in &setups {
        for target in &targets {
            eprintln!("→ {} × {}", setup.name, target.label);
            let r = run_case(&bin, setup, target, &out_dir, &validator);
            print_case_line(&r);
            results.push(r);
        }
    }
    print_report(&results, &setups, &targets);
    if results.iter().any(|r| !r.passed()) {
        std::process::exit(1);
    }
}
