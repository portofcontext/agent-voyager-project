//! Drive a live Goose `Agent` from a Commission and emit its AVP trajectory.
//!
//! Builds an `Agent` from the Commission (provider/model, extensions, system
//! prompt, structured output), emits the prelude (`run_requested` +
//! `agent_described` from the live tool registry), then consumes the live
//! `reply()` stream into the `Emitter`. Events leave as Goose produces them;
//! there is no batching.

use std::collections::HashSet;
use std::sync::Arc;

use avp::commission::AvpV01CommissionMcpServersItem;
use avp::sink::Sink;
use avp::trajectory::Usage;
use avp::Commission;
use futures::StreamExt;
use goose::agents::{Agent, AgentEvent, SessionConfig};
use goose::config::GooseMode;
use goose::conversation::message::Message;
use goose::model::ModelConfig;
use goose::session::session_manager::SessionType;
use serde_json::{json, Value};

use crate::commission::{self, GooseRunConfig};
use crate::emit::{self, Emitter};
use crate::provider_tap::{self, UsageTap};
use crate::translate::{self, GooseContent};

/// Reported as the descriptor's `agent_version`. Derived from Cargo.lock by
/// `build.rs` so it tracks the resolved `goose` dependency.
const GOOSE_VERSION: &str = env!("GOOSE_VERSION");

/// Goose's internal structured-output tool; not a tool the agent offers, so it
/// is filtered out of the descriptor.
const FINAL_OUTPUT_TOOL: &str = "recipe__final_output";

/// Reshape rmcp tools (from `list_tools`) to the AVP `ToolDecl` wire shape,
/// keeping only `name`/`description`/`inputSchema` and dropping Goose-internal
/// tools.
fn tool_decls(raw: Vec<Value>) -> Vec<Value> {
    raw.into_iter()
        .filter_map(|v| {
            let name = v.get("name").and_then(Value::as_str)?.to_string();
            if name == FINAL_OUTPUT_TOOL {
                return None;
            }
            Some(json!({
                "name": name,
                "description": v.get("description").cloned().unwrap_or(Value::Null),
                "inputSchema": v.get("inputSchema").cloned().unwrap_or_else(|| json!({ "type": "object" })),
            }))
        })
        .collect()
}

/// Materialize a Commission's inline skills under the working dir's
/// `.agents/skills/<id>/` so the skills extension discovers them.
fn write_skills(commission: &Commission, working_dir: &std::path::Path) -> anyhow::Result<()> {
    let Some(skills) = &commission.skills else {
        return Ok(());
    };
    let base = goose::skills::project_skills_dir(working_dir);
    for skill in skills {
        let dir = base.join(skill.id.to_string());
        for (rel_path, content) in &skill.files {
            let path = dir.join(rel_path);
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::write(&path, content)?;
        }
    }
    Ok(())
}

/// Run a Commission live against Goose, emitting the trajectory to `sink`.
pub async fn run<S: Sink>(commission: &Commission, sink: S) -> anyhow::Result<()> {
    // Isolate Goose's data + config under a throwaway root so a live run never
    // opens the user's production session store, and so the agent's environment
    // is defined by the Commission rather than the user's ambient goose config.
    // Must be set before the first Goose `Config` / `SessionManager` access
    // (both are process-global `LazyLock`s). The provider key still resolves
    // from the OS keychain, which is path-independent.
    let run_id = commission.run_id.to_string();
    let path_root = std::env::temp_dir().join(format!("avp-goose-{run_id}"));
    std::fs::create_dir_all(&path_root)?;
    std::env::set_var("GOOSE_PATH_ROOT", &path_root);

    let cfg: GooseRunConfig = commission::from_commission(commission);
    let model_name = cfg
        .model
        .clone()
        .ok_or_else(|| anyhow::anyhow!("Commission has no model"))?;
    let provider_name = std::env::var("GOOSE_PROVIDER").unwrap_or_else(|_| "anthropic".to_string());

    // Agent + session.
    let agent = Arc::new(Agent::new());
    let working_dir = std::env::current_dir()?;
    let session = agent
        .config
        .session_manager
        .create_session(
            working_dir.clone(),
            run_id.clone(),
            SessionType::User,
            GooseMode::Auto,
        )
        .await?;
    let session_id = session.id.clone();

    // Materialize inline skills before extensions load so they are discovered.
    write_skills(commission, &working_dir)?;

    // Provider, extensions, system prompt, structured output.
    let model_config = ModelConfig::new(&model_name)?;
    let provider =
        goose::providers::create(&provider_name, model_config, cfg.extensions.clone()).await?;
    // Wrap the provider to capture per-inference usage (incl. cache split) off
    // its stream — the signal that never reaches the AgentEvent level.
    let (provider, usage_tap) = provider_tap::tap(provider);
    agent.update_provider(provider, &session_id).await?;
    agent
        .add_extensions_bulk(cfg.extensions.clone(), &session_id)
        .await?;
    if let Some(system_prompt) = &cfg.system_prompt {
        agent
            .extend_system_prompt("commission".to_string(), system_prompt.clone())
            .await;
    }
    if let Some(response) = cfg.response {
        agent.add_final_output_tool(response).await;
    }

    // Static descriptor from the agent's live tool registry (no probe needed).
    let descriptor = build_descriptor(&agent, &session_id, &model_name).await?;

    // Emitter: provider + the set of MCP-extension names (for dispatch target).
    let mcp_servers: HashSet<String> = commission
        .mcp_servers
        .iter()
        .flatten()
        .map(|s| match s {
            AvpV01CommissionMcpServersItem::Stdio(x) => x.id.to_string(),
            AvpV01CommissionMcpServersItem::Http(x) => x.id.to_string(),
        })
        .collect();
    let mut emitter = Emitter::new(
        sink,
        run_id.clone(),
        Some(provider_name),
        mcp_servers,
        avp::load_default_prices(),
    );
    emitter.prelude(commission, &descriptor)?;
    emitter.start(Some(&model_name))?;

    // Drive the live reply stream.
    let user_message = Message::user().with_text(cfg.prompt.clone().unwrap_or_default());
    let session_config = SessionConfig {
        id: session_id.clone(),
        schedule_id: None,
        max_turns: None,
        retry_config: None,
    };
    let mut stream = agent.reply(user_message, session_config, None).await?;

    // Coalesce streamed deltas into turns. Goose yields an assistant inference
    // as incremental message deltas (partial `Text` chunks), and a new
    // inference only begins after tool execution, which arrives as a
    // non-assistant (tool-result) message. So consecutive assistant messages
    // are one inference: accumulate their content, then close the turn when a
    // non-assistant message arrives or the stream ends. By the close trigger
    // the inference is complete, so the provider tap has captured all of its
    // usage; we drain it then. This also preserves ordering (a turn's
    // `tool_invoked` lands before its `tool_returned`).
    let mut consumed: usize = 0;
    let mut ended_ok = true;
    let mut pending: Vec<GooseContent> = Vec::new();

    while let Some(item) = stream.next().await {
        match item {
            Ok(AgentEvent::Message(message)) => {
                let value = serde_json::to_value(&message)?;
                let content: Vec<GooseContent> = serde_json::from_value(
                    value
                        .get("content")
                        .cloned()
                        .unwrap_or_else(|| Value::Array(Vec::new())),
                )?;
                match value.get("role").and_then(Value::as_str) {
                    Some("assistant") => translate::append_coalescing(&mut pending, content),
                    _ => {
                        flush_turn(
                            &mut emitter,
                            &usage_tap,
                            &model_name,
                            &mut consumed,
                            &mut pending,
                        )?;
                        emitter.on_tool_results(&content)?;
                    }
                }
            }
            Ok(AgentEvent::McpNotification(_)) | Ok(AgentEvent::HistoryReplaced(_)) => {}
            Err(e) => {
                flush_turn(
                    &mut emitter,
                    &usage_tap,
                    &model_name,
                    &mut consumed,
                    &mut pending,
                )?;
                let message = e.to_string();
                emitter.error(emit::classify_error(&message), &message)?;
                ended_ok = false;
                break;
            }
        }
    }
    // Final turn: the stream has ended, so all usage has been tapped.
    flush_turn(
        &mut emitter,
        &usage_tap,
        &model_name,
        &mut consumed,
        &mut pending,
    )?;
    emitter.stop(emit::classify_stop(ended_ok, false, false), None)?;
    Ok(())
}

/// Close the open assistant turn, if any: emit one `assistant_message` from the
/// coalesced deltas with the usage tapped since the last turn. Clears `pending`.
fn flush_turn<S: Sink>(
    emitter: &mut Emitter<S>,
    usage_tap: &UsageTap,
    model: &str,
    consumed: &mut usize,
    pending: &mut Vec<GooseContent>,
) -> anyhow::Result<()> {
    if pending.is_empty() {
        return Ok(());
    }
    let content = std::mem::take(pending);
    let usage = tap_usage(usage_tap, consumed);
    emitter.on_assistant(&content, usage, Some(model.to_string()))?;
    Ok(())
}

/// Build the AVP descriptor from the agent's live tool registry. `list_tools`
/// returns rmcp tools whose `name` / `description` / `inputSchema` line up with
/// `ToolDecl`; we keep just those three so extra rmcp fields don't trip the
/// stricter AVP shape.
async fn build_descriptor(
    agent: &Arc<Agent>,
    session_id: &str,
    model: &str,
) -> anyhow::Result<avp::trajectory::AgentDescriptor> {
    let raw: Vec<Value> = agent
        .list_tools(session_id, None)
        .await
        .iter()
        .map(|tool| serde_json::to_value(tool).unwrap_or(Value::Null))
        .collect();
    let tools = tool_decls(raw);
    serde_json::from_value(json!({
        "agent_name": "goose",
        "agent_version": GOOSE_VERSION,
        "spec_version": "0.1",
        "default_model": model,
        "tools": tools,
    }))
    .map_err(|e| anyhow::anyhow!("building descriptor: {e}"))
}

/// AVP usage from the provider tap: sum the per-inference `ProviderUsage`s
/// captured since the last flush. AVP convention folds cache reads/writes into
/// `input_tokens`; the split is also carried in its own fields.
fn tap_usage(tap: &UsageTap, consumed: &mut usize) -> Usage {
    let (mut input, mut output, mut cache_read, mut cache_write) = (0i64, 0i64, 0i64, 0i64);
    for pu in tap.drain_new(consumed) {
        input += pu.usage.input_tokens.unwrap_or(0) as i64;
        output += pu.usage.output_tokens.unwrap_or(0) as i64;
        cache_read += pu.usage.cache_read_input_tokens.unwrap_or(0) as i64;
        cache_write += pu.usage.cache_write_input_tokens.unwrap_or(0) as i64;
    }
    let nonzero = |v: i64| (v > 0).then_some(v as u64);
    Usage {
        input_tokens: (input + cache_read + cache_write).max(0) as u64,
        output_tokens: output.max(0) as u64,
        cache_read_input_tokens: nonzero(cache_read),
        cache_creation_input_tokens: nonzero(cache_write),
        reasoning_output_tokens: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tool_decls_filters_final_output_and_reshapes() {
        let raw = vec![
            json!({ "name": "developer__shell", "description": "run",
                    "inputSchema": { "type": "object" }, "annotations": { "x": 1 } }),
            json!({ "name": "recipe__final_output", "description": "internal",
                    "inputSchema": { "type": "object" } }),
            json!({ "name": "analyze__list_functions" }),
        ];
        let decls = tool_decls(raw);
        let names: Vec<&str> = decls.iter().map(|d| d["name"].as_str().unwrap()).collect();
        assert_eq!(names, vec!["developer__shell", "analyze__list_functions"]);
        // Extra rmcp fields (annotations) dropped: only name/description/inputSchema.
        assert_eq!(decls[0].as_object().unwrap().len(), 3);
        // Missing inputSchema defaults to an object schema.
        assert_eq!(decls[1]["inputSchema"], json!({ "type": "object" }));
    }
}
