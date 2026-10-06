//! The adapter: harness events in, Recorder calls out.
//!
//! `describe` and `run` are all the stock entrypoint (`avp::agent_cli`) needs.

use avp::preflight::{preflight, Offered};
use avp::recorder::{AssistantOpts, Recorder, RecorderOptions, StartInfo};
use avp::sink::Sink;
use avp::trajectory::{AgentDescriptor, StopReason, ToolDecl};
use avp::Commission;
use serde_json::json;

use crate::commission::{from_commission, AGENT_NAME, BUILTIN_TOOLS};
use crate::{harness, translate};

pub const AGENT_VERSION: &str = env!("CARGO_PKG_VERSION");
/// The provider bare model names resolve under in the price table.
const PROVIDER: &str = "openai";

fn tool_decls(names: &[String]) -> Vec<ToolDecl> {
    names
        .iter()
        .map(|n| serde_json::from_value(json!({"name": n})).expect("valid decl"))
        .collect()
}

/// What the agent ships with, before any Commission.
pub fn describe() -> AgentDescriptor {
    let tools: Vec<String> = BUILTIN_TOOLS.iter().map(|t| t.to_string()).collect();
    serde_json::from_value(json!({
        "agent_name": AGENT_NAME,
        "agent_version": AGENT_VERSION,
        "spec_version": "0.1",
        "tools": tool_decls(&tools),
    }))
    .expect("valid descriptor")
}

pub fn run<S: Sink>(commission: &Commission, sink: S) -> std::io::Result<()> {
    let mut rec = Recorder::new(
        sink,
        RecorderOptions {
            run_id: Some(commission.run_id.to_string()),
            provider: Some(PROVIDER.to_string()),
            prices: avp::load_default_prices(),
            ..Default::default()
        },
    );
    rec.prelude(Some(commission), &describe())?;
    // The spec's pre-turn Commission checks (version pin, allow-list keys and
    // names); add harness-specific refusals (unreachable provider/model) here.
    let tools: Vec<String> = BUILTIN_TOOLS.iter().map(|t| t.to_string()).collect();
    let offered = Offered {
        tools: Some(&tools),
        ..Default::default()
    };
    if let Some((code, message)) = preflight(commission, AGENT_NAME, AGENT_VERSION, offered) {
        rec.error(code, &message)?;
        return rec.stop(StopReason::Error, None);
    }
    let config = from_commission(commission);
    rec.start(StartInfo {
        request_model: Some(config.model.clone()),
        prompt: Some(config.prompt.clone()),
        system_prompt: config.system_prompt.clone(),
        tools: Some(tool_decls(&config.tools)),
        ..Default::default()
    })?;
    for event in harness::stream(&config) {
        match event["kind"].as_str() {
            Some("message") => rec.assistant(
                translate::content(&event),
                Some(translate::usage(&event["usage"])),
                AssistantOpts {
                    model: Some(config.model.clone()),
                    ..Default::default()
                },
            )?,
            Some("tool_result") => rec.tool_result(
                event["call_id"].as_str().unwrap_or_default(),
                event["output"].clone(),
                event["error"].as_bool().unwrap_or(false),
                None,
            )?,
            Some("done") => rec.stop(
                translate::stop_reason(event["status"].as_str().unwrap_or_default()),
                Some(event["output"].clone()),
            )?,
            _ => {}
        }
    }
    rec.stop(StopReason::Converged, None) // no-op when the harness already ended the run
}
