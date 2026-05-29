//! Drive a live Goose `Agent` from a Commission and emit its AVP trajectory.
//!
//! Builds an `Agent` from the Commission (provider/model, extensions, system
//! prompt, structured output), emits the prelude (`run_requested` +
//! `agent_described` from the live tool registry), then consumes the live
//! `reply()` stream into the `Emitter`. Events leave as Goose produces them;
//! there is no batching.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use avp::commission::AvpV01CommissionMcpServersItem;
use avp::sink::Sink;
use avp::trajectory::{ErrorCode, StopReason, Usage};
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
/// keeping only `name`/`description`/`inputSchema` (plus `avp.mcp_server_id`
/// when the tool is MCP-surfaced) and dropping Goose-internal tools.
///
/// `mcp_tool_to_server` maps a tool name to the id of the MCP server that
/// surfaced it; tools absent from the map run locally and carry no server id.
fn tool_decls(raw: Vec<Value>, mcp_tool_to_server: &HashMap<String, String>) -> Vec<Value> {
    raw.into_iter()
        .filter_map(|v| {
            let name = v.get("name").and_then(Value::as_str)?.to_string();
            if name == FINAL_OUTPUT_TOOL {
                return None;
            }
            let mut decl = json!({
                "name": name,
                "description": v.get("description").cloned().unwrap_or(Value::Null),
                "inputSchema": v.get("inputSchema").cloned().unwrap_or_else(|| json!({ "type": "object" })),
            });
            if let Some(server_id) = mcp_tool_to_server.get(&name) {
                decl["avp.mcp_server_id"] = json!(server_id);
            }
            Some(decl)
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

    // Register goose's bundled built-ins so `Builtin` extensions resolve in-process.
    commission::register_builtins();

    let cfg: GooseRunConfig = commission::from_commission(commission);
    let model_name = cfg
        .model
        .clone()
        .ok_or_else(|| anyhow::anyhow!("Commission has no model"))?;
    let provider_name = std::env::var("GOOSE_PROVIDER").unwrap_or_else(|_| "anthropic".to_string());

    // Agent + session. The working dir is an isolated workspace under the run's
    // path root, not the user's CWD: the Commission defines the environment, and
    // Goose writes run-scoped state there (`.agents/skills`, `.agents/recipes`)
    // which must not pollute the caller's directory. (If a future use case needs
    // the agent to operate on the caller's project tree, make this configurable.)
    let agent = Arc::new(Agent::new());
    let working_dir = path_root.join("workspace");
    std::fs::create_dir_all(&working_dir)?;
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
    // `add_extensions_bulk` reports per-extension outcomes in its return value
    // rather than failing the call, so a built-in that won't load (missing
    // factory, init error) is otherwise silent. Surface failures on stderr.
    for result in agent
        .add_extensions_bulk(cfg.extensions.clone(), &session_id)
        .await?
    {
        if !result.success {
            eprintln!(
                "avp-goose: extension '{}' failed to load: {}",
                result.name,
                result.error.as_deref().unwrap_or("unknown error"),
            );
        }
    }
    if let Some(system_prompt) = &cfg.system_prompt {
        agent
            .extend_system_prompt("commission".to_string(), system_prompt.clone())
            .await;
    }
    if let Some(response) = cfg.response {
        agent.add_final_output_tool(response).await;
    }

    // The set of MCP-extension ids (for tool dispatch-target classification and
    // for tagging descriptor tools with their `mcp_server_id`).
    let mcp_servers: HashSet<String> = commission
        .mcp_servers
        .iter()
        .flatten()
        .map(|s| match s {
            AvpV01CommissionMcpServersItem::Stdio(x) => x.id.to_string(),
            AvpV01CommissionMcpServersItem::Http(x) => x.id.to_string(),
        })
        .collect();

    // Commission-declared skills (materialized by `write_skills`), enumerated on
    // the descriptor.
    let skills: Vec<String> =
        commission.skills.iter().flatten().map(|s| s.id.to_string()).collect();

    // Static descriptor from the agent's live tool registry (no probe needed).
    let descriptor =
        build_descriptor(&agent, &session_id, Some(&model_name), &mcp_servers, &skills).await?;

    let mut emitter = Emitter::new(
        sink,
        run_id.clone(),
        Some(provider_name),
        mcp_servers,
        avp::load_default_prices(),
    );
    emitter.prelude(commission, &descriptor)?;

    // Fail fast (spec): every name in `enabled_builtin_tools` must be a tool the
    // agent actually offers. An unknown name is a Commission/agent collision —
    // emit `error_occurred(commission_collision)` + `agent_stopped(error)` before
    // the loop, so no model turn runs.
    if let Some(names) = &commission.enabled_builtin_tools {
        let known: HashSet<&str> =
            descriptor.tools.iter().flatten().map(|t| t.name.as_str()).collect();
        let unknown: Vec<&str> =
            names.iter().map(String::as_str).filter(|n| !known.contains(n)).collect();
        if !unknown.is_empty() {
            emitter.error(
                ErrorCode::CommissionCollision,
                &format!(
                    "enabled_builtin_tools names not offered by the agent: {}",
                    unknown.join(", ")
                ),
            )?;
            emitter.stop(StopReason::Error, None)?;
            return Ok(());
        }
    }

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

/// The agent's pre-flight `AgentDescriptor`: full capability surface (identity,
/// default model, built-in tools) with no Commission and no run.
///
/// Heavy by design — it boots a default Goose `Agent` with its built-in
/// extensions and lists their live tool registry, the same surface
/// `agent_described` reports during a run. If the live probe can't complete
/// (e.g. no provider creds to construct the provider), it degrades to an
/// identity-only descriptor, which still validates against the spec.
pub async fn describe() -> anyhow::Result<avp::trajectory::AgentDescriptor> {
    match describe_live().await {
        Ok(descriptor) => Ok(descriptor),
        Err(e) => {
            eprintln!("avp-goose: describe probe failed ({e}); emitting identity-only descriptor");
            serde_json::from_value(json!({
                "agent_name": "goose",
                "agent_version": GOOSE_VERSION,
                "spec_version": "0.1",
            }))
            .map_err(|e| anyhow::anyhow!("building fallback descriptor: {e}"))
        }
    }
}

async fn describe_live() -> anyhow::Result<avp::trajectory::AgentDescriptor> {
    // Throwaway data/config root so the probe never opens the user's goose store.
    let path_root = std::env::temp_dir().join(format!("avp-goose-describe-{}", std::process::id()));
    std::fs::create_dir_all(&path_root)?;
    std::env::set_var("GOOSE_PATH_ROOT", &path_root);

    // Register goose's bundled built-ins so the full surface resolves in-process.
    commission::register_builtins();

    // No Commission: a minimal one yields goose's default built-in extensions
    // (the surface the agent ships with). Advertise goose's actually-configured
    // model (env or config) as `default_model` — or nothing if it has none. A
    // model is still needed to construct the provider for tool-listing (no model
    // call fires), so fall back to a throwaway there only.
    let configured_model = goose::config::Config::global()
        .get_param::<String>("GOOSE_MODEL")
        .ok();
    let model_name = configured_model
        .clone()
        .unwrap_or_else(|| "claude-haiku-4-5".to_string());
    let commission: Commission = serde_json::from_value(json!({
        "schema_version": "0.1",
        "run_id": "describe",
        "model": model_name,
    }))?;
    let cfg: GooseRunConfig = commission::from_commission(&commission);
    let provider_name = std::env::var("GOOSE_PROVIDER").unwrap_or_else(|_| "anthropic".to_string());

    let agent = Arc::new(Agent::new());
    let working_dir = path_root.join("workspace");
    std::fs::create_dir_all(&working_dir)?;
    let session = agent
        .config
        .session_manager
        .create_session(working_dir, "describe".to_string(), SessionType::User, GooseMode::Auto)
        .await?;
    let session_id = session.id.clone();

    let model_config = ModelConfig::new(&model_name)?;
    let provider =
        goose::providers::create(&provider_name, model_config, cfg.extensions.clone()).await?;
    agent.update_provider(provider, &session_id).await?;
    for result in agent.add_extensions_bulk(cfg.extensions.clone(), &session_id).await? {
        if !result.success {
            eprintln!(
                "avp-goose: extension '{}' failed to load: {}",
                result.name,
                result.error.as_deref().unwrap_or("unknown error"),
            );
        }
    }

    // The pre-flight view carries no Commission MCP servers or skills, and only
    // advertises a default_model if goose actually has one configured.
    build_descriptor(&agent, &session_id, configured_model.as_deref(), &HashSet::new(), &[]).await
}

/// Build the AVP descriptor from the agent's live tool registry. `list_tools`
/// returns rmcp tools whose `name` / `description` / `inputSchema` line up with
/// `ToolDecl`; we keep just those three so extra rmcp fields don't trip the
/// stricter AVP shape.
async fn build_descriptor(
    agent: &Arc<Agent>,
    session_id: &str,
    default_model: Option<&str>,
    mcp_servers: &HashSet<String>,
    skills: &[String],
) -> anyhow::Result<avp::trajectory::AgentDescriptor> {
    let tool_names = |tools: Vec<rmcp::model::Tool>| -> Vec<String> {
        tools.iter().map(|t| t.name.to_string()).collect()
    };

    // Map each MCP-surfaced tool to its server id by querying the registry
    // per-extension (tool names from `list_tools(None)` are not reliably
    // prefixed, so a per-server query is the dependable correlation).
    let mut mcp_tool_to_server: HashMap<String, String> = HashMap::new();
    for id in mcp_servers {
        for name in tool_names(agent.list_tools(session_id, Some(id.clone())).await) {
            mcp_tool_to_server.insert(name, id.clone());
        }
    }

    let raw: Vec<Value> = agent
        .list_tools(session_id, None)
        .await
        .iter()
        .map(|tool| serde_json::to_value(tool).unwrap_or(Value::Null))
        .collect();
    let tools = tool_decls(raw, &mcp_tool_to_server);

    // Each Commission MCP server the agent loaded is enumerated with its dial
    // status. `add_extensions_bulk` connected them earlier, so status is
    // `connected`; only connected servers contribute tools (above).
    let mcp_server_decls: Vec<Value> = mcp_servers
        .iter()
        .map(|id| json!({ "id": id, "status": "connected" }))
        .collect();

    // The Commission's inline skills, materialized by `write_skills` and loaded
    // on demand via Goose's `load_skill` tool. The descriptor enumerates them as
    // the agent's available skills.
    let skill_decls: Vec<Value> = skills.iter().map(|name| json!({ "name": name })).collect();

    let mut descriptor = json!({
        "agent_name": "goose",
        "agent_version": GOOSE_VERSION,
        "spec_version": "0.1",
        "tools": tools,
        "mcp_servers": mcp_server_decls,
        "skills": skill_decls,
    });
    // Only advertise default_model when there actually is one.
    if let Some(model) = default_model {
        descriptor["default_model"] = json!(model);
    }
    serde_json::from_value(descriptor).map_err(|e| anyhow::anyhow!("building descriptor: {e}"))
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
        // `analyze__list_functions` is surfaced by the `analyze` MCP server.
        let mcp: HashMap<String, String> =
            [("analyze__list_functions".to_string(), "analyze".to_string())].into();
        let decls = tool_decls(raw, &mcp);
        let names: Vec<&str> = decls.iter().map(|d| d["name"].as_str().unwrap()).collect();
        assert_eq!(names, vec!["developer__shell", "analyze__list_functions"]);
        // Local tool: only name/description/inputSchema, no mcp_server_id.
        assert_eq!(decls[0].as_object().unwrap().len(), 3);
        assert!(decls[0].get("avp.mcp_server_id").is_none());
        // Missing inputSchema defaults to an object schema.
        assert_eq!(decls[1]["inputSchema"], json!({ "type": "object" }));
        // MCP-surfaced tool carries its server id.
        assert_eq!(decls[1]["avp.mcp_server_id"], "analyze");
    }
}
