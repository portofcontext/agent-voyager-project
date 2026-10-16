//! Drive a live Goose `Agent` from a Commission and emit its AVP trajectory.
//!
//! Builds an `Agent` from the Commission (provider/model, extensions, system
//! prompt, structured output), emits the prelude (`run_requested` +
//! `agent_described` from the live tool registry), then consumes the live
//! `reply()` stream into the `Emitter`. Events leave as Goose produces them;
//! there is no batching.

use std::collections::{HashMap, HashSet};
use std::future::Future;
use std::sync::Arc;
use std::time::Instant;

use avp::commission::AvpV01CommissionMcpServersItem;
use avp::sink::Sink;
use avp::trajectory::{ErrorCode, StopReason};
use avp::Commission;
use futures::{Stream, StreamExt};
use goose::agents::{Agent, AgentConfig, AgentEvent, GoosePlatform, SessionConfig};
use goose::config::{Config, GooseMode, PermissionManager};
use goose::conversation::message::{
    Message, MessageContent, MessageErrorKind, SystemNotificationType,
};
use goose::model_config::model_config_from_user_config;
use goose::session::session_manager::{SessionManager, SessionType};
use serde_json::{json, Value};
use tokio_util::sync::CancellationToken;

use crate::commission::{self, GooseRunConfig};
use crate::emit::{self, Emitter};
use crate::translate::{self, GooseContent};

/// The descriptor's `agent_version`: THIS connector build's version (the
/// number `Commission.agent_versions` pins match and release tags derive
/// from). The upstream Goose dependency's version is provenance, not
/// identity; it rides on `agent_started.data["avp.meta"]` as
/// `goose.upstream_version` (see `events::agent_started`).
const AGENT_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Goose's internal structured-output tool; not a tool the agent offers, so it
/// is filtered out of the descriptor.
const FINAL_OUTPUT_TOOL: &str = "recipe__final_output";

/// Reshape rmcp tools (from `list_tools`) to the AVP `ToolDecl` wire shape,
/// keeping only `name`/`description`/`inputSchema`/`outputSchema` (plus
/// `avp.mcp_server_id` when the tool is MCP-surfaced) and dropping
/// Goose-internal tools.
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
            if let Some(output_schema) = v.get("outputSchema") {
                if !output_schema.is_null() {
                    decl["outputSchema"] = output_schema.clone();
                }
            }
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
    // Native config/state paths are supplied by the launcher before SDK startup.
    let run_id = commission.run_id.to_string();

    // Register goose's bundled built-ins so `Builtin` extensions resolve in-process.
    commission::register_builtins();

    let cfg: GooseRunConfig = commission::from_commission(commission);
    // `model_name` is the full canonical `origin/model` slug; it stays the slug
    // for pricing and the descriptor/request_model. `native_model` is the bare
    // SDK-facing id (slug with the origin stripped) handed to goose's provider.
    let model_name = cfg
        .model
        .clone()
        .ok_or_else(|| anyhow::anyhow!("Commission has no model"))?;
    let origin = model_name.split('/').next().unwrap_or("");
    // Provider: the Commission's `provider.id` wins; then the `GOOSE_PROVIDER`
    // env (transitional bridge); then the slug's origin segment; else anthropic.
    let provider_name = cfg
        .provider_id
        .clone()
        .or_else(|| std::env::var("GOOSE_PROVIDER").ok())
        .or_else(|| (!origin.is_empty()).then(|| origin.to_string()))
        .unwrap_or_else(|| "anthropic".to_string());
    // Native model id is provider-aware. A native provider (id == the slug's
    // origin, or no provider) wants the bare model (`gpt-4o`). A gateway that
    // aggregates vendors (id != origin, e.g. openrouter) wants the full
    // vendor-prefixed slug as its model id (`openai/gpt-4o`).
    let native_model = if provider_name != origin {
        model_name.clone()
    } else {
        model_name
            .split_once('/')
            .map(|(_, m)| m)
            .unwrap_or(&model_name)
            .to_string()
    };

    let agent = Arc::new(new_agent());
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
    let model_config = model_config_from_user_config(&provider_name, &native_model)?;
    let provider = goose::providers::create(&provider_name, cfg.extensions.clone()).await?;
    agent
        .update_provider(provider, model_config, &session_id)
        .await?;
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
        agent.add_final_output_tool(response).await?;
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

    // Static descriptor from the agent's live tool registry (no probe needed).
    // Skills are discovered from disk (built-ins + the working dir's `.agents/skills`,
    // where `write_skills` materialized the Commission's inline skills).
    let descriptor = build_descriptor(
        &agent,
        &session_id,
        Some(&model_name),
        &mcp_servers,
        &working_dir,
    )
    .await?;

    let mut emitter = Emitter::new(
        sink,
        run_id.clone(),
        Some(provider_name),
        mcp_servers,
        avp::load_default_prices(),
    );
    emitter.prelude(commission, &descriptor)?;

    // Fail fast (spec §4): a version pin for a different build, an allow-list
    // map without our key, or an allow-listed tool the agent doesn't offer.
    // Emit `error_occurred` + `agent_stopped(error)` before any model turn.
    let offered_tools: Vec<String> = descriptor
        .tools
        .iter()
        .flatten()
        .map(|t| t.name.clone())
        .collect();
    let offered = avp::preflight::Offered {
        tools: Some(&offered_tools),
        ..Default::default()
    };
    if let Some((code, message)) =
        avp::preflight::preflight(commission, commission::AGENT_NAME, AGENT_VERSION, offered)
    {
        emitter.error(code, &message)?;
        emitter.stop(StopReason::Error, None)?;
        return Ok(());
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
    // SIGINT / SIGTERM cancel Goose's run and close the trajectory as
    // `interrupted`. The handlers are installed before the first inference.
    let cancel = CancellationToken::new();
    let interrupt = interrupt_signal()?;
    // Goose's default loop; its experimental state-machine loop stays off.
    let stream = agent
        .reply(user_message, session_config, false, Some(cancel.clone()))
        .await?;

    let sessions = agent.config.session_manager.clone();
    record_reply(
        &mut emitter,
        &model_name,
        Some(&sessions),
        stream,
        async move {
            interrupt.await;
            cancel.cancel();
        },
    )
    .await
}

/// Resolves on the first SIGINT or SIGTERM.
#[cfg(unix)]
fn interrupt_signal() -> std::io::Result<impl Future<Output = ()>> {
    use tokio::signal::unix::{signal, SignalKind};
    let mut int = signal(SignalKind::interrupt())?;
    let mut term = signal(SignalKind::terminate())?;
    Ok(async move {
        tokio::select! {
            _ = int.recv() => {}
            _ = term.recv() => {}
        }
    })
}

#[cfg(not(unix))]
fn interrupt_signal() -> std::io::Result<impl Future<Output = ()>> {
    Ok(async {
        let _ = tokio::signal::ctrl_c().await;
    })
}

/// Consume the native Goose stream, including terminal failures that Goose
/// delivers as successful Message events rather than stream errors.
async fn record_reply<S: Sink>(
    emitter: &mut Emitter<S>,
    model_name: &str,
    sessions: Option<&SessionManager>,
    mut stream: impl Stream<Item = anyhow::Result<AgentEvent>> + Unpin,
    interrupt: impl Future<Output = ()>,
) -> anyhow::Result<()> {
    // Coalesce streamed deltas into turns. Goose yields an assistant inference
    // as incremental message deltas (partial `Text` chunks), and a new
    // inference only begins after tool execution, which arrives as a
    // non-assistant (tool-result) message. So consecutive assistant messages
    // are one inference: accumulate their content, then close the turn when a
    // non-assistant message arrives or the stream ends.
    //
    // Goose attributes an inference's usage to its assistant message with a
    // `MessageUsage` event that lands after the turn's tool results, before the
    // next inference. So a turn is reported under its message id and kept open:
    // tool results buffer onto it, `MessageUsage` fills in its usage and the
    // inference's own elapsed time, and the next inference (or the stop) closes
    // it. Ordering holds: a turn's `tool_invoked` lands before its
    // `tool_returned`.
    let mut ended_ok = true;
    let mut pending: Vec<GooseContent> = Vec::new();
    // Goose message ids coalesced into `pending`, then into the open turn.
    let mut pending_ids: Vec<String> = Vec::new();
    let mut open_ids: Vec<String> = Vec::new();
    // Wall-clock start of the inference whose deltas we are coalescing. Set when
    // `reply()` is dispatched (turn 1) and reset after each tool-result batch
    // (the next inference begins once Goose has the tool output). Carried into
    // the turn so `assistant_message.duration_ms` reflects the model's time, not
    // the ~0 between materializing and draining the coalesced turn at flush.
    let mut turn_start = Instant::now();
    // Set when `interrupt` resolves: stop reading, close what's open, and stop
    // as `interrupted`.
    let mut interrupted = false;
    let mut interrupt = std::pin::pin!(interrupt);

    loop {
        let item = tokio::select! {
            item = stream.next() => item,
            () = &mut interrupt, if !interrupted => {
                interrupted = true;
                None
            }
        };
        let Some(item) = item else { break };
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
                    Some("assistant") => {
                        if let Some((code, diagnostic)) = provider_failure(&message) {
                            flush_turn(
                                emitter,
                                model_name,
                                &mut pending,
                                &mut pending_ids,
                                &mut open_ids,
                                turn_start,
                            )?;
                            emitter.error(code, diagnostic)?;
                            ended_ok = false;
                            // Let Goose finish its bookkeeping and deliver any
                            // final usage for content produced before failure.
                            continue;
                        }
                        if let Some(id) = value.get("id").and_then(Value::as_str) {
                            if !pending_ids.iter().any(|p| p == id) {
                                pending_ids.push(id.to_string());
                            }
                        }
                        translate::append_coalescing(&mut pending, content)
                    }
                    _ => {
                        flush_turn(
                            emitter,
                            model_name,
                            &mut pending,
                            &mut pending_ids,
                            &mut open_ids,
                            turn_start,
                        )?;
                        if let Some(sessions) = sessions {
                            let children: Vec<String> = content
                                .iter()
                                .filter_map(translate::as_tool_return)
                                .filter_map(|ret| {
                                    translate::subagent_session(&ret)
                                        .or_else(|| emitter.loaded_subagent(&ret.id))
                                        .map(str::to_string)
                                })
                                .collect();
                            read_subagent_usage(emitter, sessions, children).await;
                        }
                        emitter.on_tool_results(&content)?;
                        // The next inference begins now that Goose has the tool
                        // output; time it from here.
                        turn_start = Instant::now();
                    }
                }
            }
            Ok(AgentEvent::MessageUsage { message_id, usage }) => {
                // An inference with no tool round reaches `MessageUsage` before
                // any close trigger; report its turn first so usage lands on it.
                let id = message_id.unwrap_or_default();
                if pending_ids.contains(&id) {
                    flush_turn(
                        emitter,
                        model_name,
                        &mut pending,
                        &mut pending_ids,
                        &mut open_ids,
                        turn_start,
                    )?;
                }
                if open_ids.contains(&id) {
                    emitter.on_usage(translate::message_usage(&usage), usage.elapsed_ms)?;
                }
            }
            Ok(AgentEvent::Usage(_))
            | Ok(AgentEvent::McpNotification(_))
            | Ok(AgentEvent::HistoryReplaced(_)) => {}
            Err(e) => {
                flush_turn(
                    emitter,
                    model_name,
                    &mut pending,
                    &mut pending_ids,
                    &mut open_ids,
                    turn_start,
                )?;
                let message = e.to_string();
                emitter.error(emit::classify_error(&message), &message)?;
                ended_ok = false;
                break;
            }
        }
    }
    // Final turn: the stream has ended; `stop` closes the open turn.
    flush_turn(
        emitter,
        model_name,
        &mut pending,
        &mut pending_ids,
        &mut open_ids,
        turn_start,
    )?;
    if let Some(sessions) = sessions {
        let children = emitter.background_subagents();
        read_subagent_usage(emitter, sessions, children).await;
    }
    emitter.stop(emit::classify_stop(ended_ok, interrupted, false), None)?;
    Ok(())
}

/// Goose v1.53.0's default loop renders some provider errors as UI messages.
/// Model output is stamped with inference metadata; never classify that output
/// by its text. Prefer typed error/credit notices, and recognize only the exact
/// wrappers used by the pinned loop for its remaining untyped failures.
fn provider_failure(message: &Message) -> Option<(ErrorCode, &str)> {
    if message.metadata.inference.is_some() {
        return None;
    }
    for block in &message.content {
        match block {
            MessageContent::Error(error) => {
                let code = match error.kind {
                    MessageErrorKind::Authentication => ErrorCode::AuthError,
                    MessageErrorKind::ContextLengthExceeded => ErrorCode::ContextLimit,
                    MessageErrorKind::CreditsExhausted => ErrorCode::RateLimit,
                    MessageErrorKind::Other => emit::classify_error(&error.message),
                };
                return Some((code, &error.message));
            }
            MessageContent::SystemNotification(notice) => {
                if notice.notification_type == SystemNotificationType::CreditsExhausted {
                    return Some((ErrorCode::RateLimit, &notice.msg));
                }
                if notice.notification_type == SystemNotificationType::InlineMessage
                    && notice.msg == "Unable to continue: Context limit still exceeded after compaction. Try using a shorter message, a model with a larger context window, or start a new session."
                {
                    return Some((ErrorCode::ContextLimit, &notice.msg));
                }
            }
            MessageContent::Text(text) => {
                let text = text.text.as_str();
                if (text.starts_with("Ran into this error: ")
                    && text.ends_with(
                        ".\n\nPlease retry if you think this is a transient or recoverable error.",
                    ))
                    || (text.starts_with("Network error: ")
                        && text.ends_with("\n\nPlease resend your message to try again."))
                    || (text.starts_with("Ran into this error trying to compact: ")
                        && text.ends_with(".\n\nPlease try again or create a new session"))
                {
                    return Some((emit::classify_error(text), text));
                }
            }
            _ => {}
        }
    }
    None
}

/// Hand the emitter each child session's usage totals, which Goose keeps per
/// session while dropping the child's own usage events.
async fn read_subagent_usage<S: Sink>(
    emitter: &mut Emitter<S>,
    sessions: &SessionManager,
    children: Vec<String>,
) {
    for child in children {
        if let Ok(totals) = sessions.get_session_usage_totals(&child).await {
            emitter.on_subagent_usage(&child, translate::subagent_usage(&totals));
        }
    }
}

/// Report the coalesced assistant deltas as one turn, keyed by its last Goose
/// message id and left open for that message's `MessageUsage`. The turn's
/// duration is a fallback from `turn_start`, replaced by Goose's own
/// `elapsed_ms` when the usage arrives. Clears `pending`.
fn flush_turn<S: Sink>(
    emitter: &mut Emitter<S>,
    model: &str,
    pending: &mut Vec<GooseContent>,
    pending_ids: &mut Vec<String>,
    open_ids: &mut Vec<String>,
    turn_start: Instant,
) -> anyhow::Result<()> {
    if pending.is_empty() {
        return Ok(());
    }
    let content = std::mem::take(pending);
    *open_ids = std::mem::take(pending_ids);
    // A message without an id still needs a key unique to this turn.
    let key = open_ids
        .last()
        .cloned()
        .unwrap_or_else(|| format!("turn@{turn_start:?}"));
    let duration_ms = turn_start.elapsed().as_millis() as u64;
    emitter.on_inference(&content, Some(model.to_string()), key, Some(duration_ms))?;
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
                "agent_version": AGENT_VERSION,
                "spec_version": "0.1",
            }))
            .map_err(|e| anyhow::anyhow!("building fallback descriptor: {e}"))
        }
    }
}

async fn describe_live() -> anyhow::Result<avp::trajectory::AgentDescriptor> {
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
    let native_model = configured_model
        .clone()
        .unwrap_or_else(|| "claude-haiku-4-5".to_string());
    let provider_name = std::env::var("GOOSE_PROVIDER").unwrap_or_else(|_| "anthropic".to_string());
    // Provider construction requires a key to exist, but the probe never
    // calls the model. Launchers may supply an empty native config store.
    // Give the default provider
    // a throwaway key rather than degrading to the identity-only fallback
    // on keyless hosts. An explicitly chosen provider (GOOSE_PROVIDER set)
    // is expected to bring its own env vars, which pass through.
    if provider_name == "anthropic" && std::env::var("ANTHROPIC_API_KEY").is_err() {
        std::env::set_var("ANTHROPIC_API_KEY", "avp-describe-throwaway");
    }
    // The Commission requires a canonical `origin/model` slug; qualify goose's
    // bare configured model with the provider as its origin.
    let slug = format!("{provider_name}/{native_model}");
    let commission: Commission = serde_json::from_value(json!({
        "schema_version": "0.1",
        "run_id": "describe",
        "model": slug,
    }))?;
    let cfg: GooseRunConfig = commission::from_commission(&commission);

    let agent = Arc::new(new_agent());
    let working_dir = std::env::current_dir()?;
    let session = agent
        .config
        .session_manager
        .create_session(
            working_dir.clone(),
            "describe".to_string(),
            SessionType::User,
            GooseMode::Auto,
        )
        .await?;
    let session_id = session.id.clone();

    let model_config = model_config_from_user_config(&provider_name, &native_model)?;
    let provider = goose::providers::create(&provider_name, cfg.extensions.clone()).await?;
    agent
        .update_provider(provider, model_config, &session_id)
        .await?;
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

    // The pre-flight view carries no Commission MCP servers or skills, and only
    // advertises a default_model if goose actually has one configured.
    build_descriptor(
        &agent,
        &session_id,
        configured_model.as_deref(),
        &HashSet::new(),
        &working_dir,
    )
    .await
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
    working_dir: &std::path::Path,
) -> anyhow::Result<avp::trajectory::AgentDescriptor> {
    // Map each MCP-surfaced tool to its server id by querying the registry
    // per-extension (tool names from `list_tools(None)` are not reliably
    // prefixed, so a per-server query is the dependable correlation).
    let mut mcp_tool_to_server: HashMap<String, String> = HashMap::new();
    for id in mcp_servers {
        for tool in agent.list_tools(session_id, Some(id.clone())).await {
            mcp_tool_to_server.insert(tool.name.to_string(), id.clone());
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

    // Skills auto-available to the agent, loaded on demand via the `load_skill`
    // tool: goose's bundled built-ins (e.g. `goose_doc_guide`) plus any discovered
    // on the filesystem (the working dir's `.agents/skills` — including the
    // Commission's inline skills materialized by `write_skills` — and the operator's
    // configured skill dirs). Filesystem-based by design; a sandbox will scope what's
    // visible later.
    // `avp.source` is the skill's on-disk path (the directory holding SKILL.md;
    // `builtin://skills/<name>` for bundled ones), per trajectory spec §6: with
    // it populated, consumers attribute skill exploration by matching file-tool
    // inputs against these paths.
    let skill_decls: Vec<Value> = goose::skills::discover_skills(Some(working_dir))
        .iter()
        .map(|s| {
            let mut decl = json!({ "name": s.name, "avp.source": s.path });
            if !s.description.is_empty() {
                decl["description"] = json!(s.description);
            }
            decl
        })
        .collect();

    // Subagents the model can `delegate` to via the `summon` extension. With the
    // `delegate` tool loaded, the model can always spawn an ad-hoc subagent from
    // instructions alone (its frame is named `delegate`, as in `emit`); recipes /
    // agents discovered on the filesystem (working-dir and configured dirs) add
    // named ones. Goose ships no bundled recipes.
    let mut subagent_decls: Vec<Value> = Vec::new();
    if tools.iter().any(|t| t["name"] == "delegate") {
        subagent_decls.push(json!({
            "name": "delegate",
            "description": "An ad-hoc subagent the model spawns with instructions via summon's `delegate` tool.",
        }));
    }
    subagent_decls.extend(
        goose::agents::platform_extensions::summon::discover_filesystem_sources(working_dir)
            .iter()
            .map(|s| {
                let mut decl = json!({ "name": s.name });
                if !s.description.is_empty() {
                    decl["description"] = json!(s.description);
                }
                decl
            }),
    );

    let mut descriptor = json!({
        "agent_name": "goose",
        "agent_version": AGENT_VERSION,
        "spec_version": "0.1",
        "tools": tools,
        "mcp_servers": mcp_server_decls,
        "skills": skill_decls,
        "subagents": subagent_decls,
    });
    // Only advertise default_model when there actually is one.
    if let Some(model) = default_model {
        descriptor["default_model"] = json!(model);
    }
    serde_json::from_value(descriptor).map_err(|e| anyhow::anyhow!("building descriptor: {e}"))
}

/// Goose's default agent without session naming: the title Goose generates
/// is a model call outside the reply loop, spend the trajectory never records.
fn new_agent() -> Agent {
    Agent::with_config(AgentConfig::new(
        Arc::new(SessionManager::instance()),
        PermissionManager::instance(),
        None,
        Config::global().get_goose_mode().unwrap_or_default(),
        true,
        GoosePlatform::GooseCli,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    use goose::conversation::message::InferenceMetadata;
    use std::sync::Mutex;

    const QUOTA_FAILURE: &str = "Ran into this error: Rate limit exceeded: You have no credits remaining..\n\nPlease retry if you think this is a transient or recoverable error.";

    #[tokio::test]
    async fn the_agent_never_names_its_session() {
        assert!(new_agent().config.disable_session_naming);
    }

    /// A Goose message from its JSON wire form.
    fn wire(id: &str, role: &str, content: Value) -> anyhow::Result<AgentEvent> {
        Ok(AgentEvent::Message(
            serde_json::from_value(json!({
                "id": id, "role": role, "created": 0,
                "metadata": { "userVisible": true, "agentVisible": true },
                "content": content
            }))
            .unwrap(),
        ))
    }

    fn summon_call(id: &str, name: &str, arguments: Value) -> Value {
        json!([{
            "type": "toolRequest", "id": id,
            "_meta": { "goose_extension": "summon" },
            "toolCall": { "status": "success", "value": { "name": name, "arguments": arguments } }
        }])
    }

    fn tool_result(id: &str, text: &str, meta: Value) -> Value {
        json!([{
            "type": "toolResponse", "id": id,
            "toolResult": { "status": "success", "value": {
                "content": [{ "type": "text", "text": text }],
                "_meta": meta
            } }
        }])
    }

    /// Drive `record_reply` with a session store holding one child session
    /// that spent 1200 input / 34 output tokens; `items` gets its id.
    async fn with_child(items: impl FnOnce(&str) -> Vec<anyhow::Result<AgentEvent>>) -> Vec<Value> {
        let dir = std::env::temp_dir().join(format!(
            "avp-goose-sessions-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let sessions = SessionManager::new(dir.clone());
        let child = sessions
            .create_session(
                dir.clone(),
                "child".into(),
                SessionType::SubAgent,
                GooseMode::Auto,
            )
            .await
            .unwrap();
        sessions
            .update(&child.id)
            .accumulated_usage(goose::providers::base::Usage::new(
                Some(1200),
                Some(34),
                None,
            ))
            .apply()
            .await
            .unwrap();
        let sink = Capture::default();
        let mut emitter = Emitter::new(
            sink.clone(),
            "delegate",
            Some("openai".into()),
            HashSet::new(),
            avp::load_default_prices(),
        );
        emitter.start(Some("gpt-4o-mini")).unwrap();
        record_reply(
            &mut emitter,
            "gpt-4o-mini",
            Some(&sessions),
            futures::stream::iter(items(&child.id)),
            std::future::pending(),
        )
        .await
        .unwrap();
        let _ = std::fs::remove_dir_all(dir);
        let events = sink.0.lock().unwrap().clone();
        events
    }

    fn subagent_returned(events: &[Value]) -> &Value {
        let returned: Vec<_> = events
            .iter()
            .filter(|e| e["type"] == "avp.subagent_returned")
            .collect();
        assert_eq!(returned.len(), 1, "one subagent frame closes");
        &returned[0]["data"]
    }

    #[tokio::test]
    async fn a_delegate_result_carries_the_child_sessions_usage() {
        // Goose drops a subagent's own usage events; its session keeps the
        // totals, and the `delegate` result names that session.
        let events = with_child(|child| {
            vec![
                wire(
                    "p1",
                    "assistant",
                    summon_call("d1", "delegate", json!({ "instructions": "say PONG" })),
                ),
                wire(
                    "t1",
                    "user",
                    tool_result("d1", "PONG", json!({ "subagent_session_id": child })),
                ),
            ]
        })
        .await;
        let returned = subagent_returned(&events);
        assert_eq!(returned["avp.subagent.result.text"], "PONG");
        assert_eq!(returned["avp.subagent.usage"]["tokens_input"], 1200);
        assert_eq!(returned["avp.subagent.usage"]["tokens_output"], 34);
    }

    #[tokio::test]
    async fn a_background_delegate_closes_when_its_result_is_loaded() {
        // `async: true` returns at launch; the child's answer and spend arrive
        // through a later `load` of its task id.
        let events = with_child(|child| {
            vec![
                wire(
                    "p1",
                    "assistant",
                    summon_call(
                        "d1",
                        "delegate",
                        json!({ "async": true, "instructions": "say PONG" }),
                    ),
                ),
                wire(
                    "t1",
                    "user",
                    tool_result(
                        "d1",
                        "started in background",
                        json!({ "subagent_session_id": child }),
                    ),
                ),
                wire(
                    "p2",
                    "assistant",
                    summon_call("l1", "load", json!({ "source": child })),
                ),
                wire("t2", "user", tool_result("l1", "PONG", json!({}))),
            ]
        })
        .await;
        let returned = subagent_returned(&events);
        assert_eq!(returned["avp.subagent.invocation_id"], "d1");
        assert_eq!(returned["avp.subagent.reason"], "converged");
        assert_eq!(returned["avp.subagent.result.text"], "PONG");
        assert_eq!(returned["avp.subagent.usage"]["tokens_input"], 1200);
        let types: Vec<_> = events.iter().map(|e| e["type"].as_str().unwrap()).collect();
        let load_returned = events
            .iter()
            .rposition(|e| e["type"] == "avp.tool_returned")
            .unwrap();
        assert!(
            types
                .iter()
                .position(|t| *t == "avp.subagent_returned")
                .unwrap()
                > load_returned
        );
    }

    #[tokio::test]
    async fn a_background_delegate_never_loaded_is_abandoned_with_its_spend() {
        let events = with_child(|child| {
            vec![
                wire(
                    "p1",
                    "assistant",
                    summon_call(
                        "d1",
                        "delegate",
                        json!({ "async": true, "instructions": "say PONG" }),
                    ),
                ),
                wire(
                    "t1",
                    "user",
                    tool_result(
                        "d1",
                        "started in background",
                        json!({ "subagent_session_id": child }),
                    ),
                ),
            ]
        })
        .await;
        let returned = subagent_returned(&events);
        assert_eq!(returned["avp.subagent.reason"], "abandoned");
        assert_eq!(returned["avp.subagent.usage"]["tokens_output"], 34);
    }

    #[derive(Clone, Default)]
    struct Capture(Arc<Mutex<Vec<Value>>>);

    impl Sink for Capture {
        fn emit(&self, event: &avp::Event) -> std::io::Result<()> {
            self.0.lock().unwrap().push(serde_json::to_value(event)?);
            Ok(())
        }
    }

    fn model_message(text: &str) -> Message {
        Message::assistant()
            .with_id("model-turn")
            .with_text(text)
            .with_inference(InferenceMetadata {
                provider: "openai".into(),
                requested_model: "gpt-4o-mini".into(),
                resolved_model: None,
                provider_session_id: None,
            })
    }

    async fn trajectory(items: Vec<anyhow::Result<AgentEvent>>) -> Vec<Value> {
        let sink = Capture::default();
        let mut emitter = Emitter::new(
            sink.clone(),
            "provider-failure",
            Some("openai".into()),
            HashSet::new(),
            avp::load_default_prices(),
        );
        emitter.start(Some("gpt-4o-mini")).unwrap();
        record_reply(
            &mut emitter,
            "gpt-4o-mini",
            None,
            futures::stream::iter(items),
            std::future::pending(),
        )
        .await
        .unwrap();
        let events = sink.0.lock().unwrap().clone();
        let schema: Value = serde_json::from_str(include_str!(
            "../../../../avp/core/spec/v0.1/trajectory.schema.json"
        ))
        .unwrap();
        let validator = jsonschema::validator_for(&schema).unwrap();
        for event in &events {
            assert!(validator.is_valid(event), "invalid event: {event}");
        }
        events
    }

    #[tokio::test]
    async fn an_interrupt_closes_the_open_turn_and_stops_interrupted() {
        // The model streamed a turn, then the stream stalls; SIGTERM arrives.
        let sink = Capture::default();
        let mut emitter = Emitter::new(
            sink.clone(),
            "interrupted",
            Some("openai".into()),
            HashSet::new(),
            avp::load_default_prices(),
        );
        emitter.start(Some("gpt-4o-mini")).unwrap();
        // The signal fires only once the stream has handed over its message,
        // then the stream stalls: `select!` picks randomly between ready
        // branches, so firing earlier could interrupt before the message.
        let (fire, fired) = tokio::sync::oneshot::channel::<()>();
        let stream = futures::stream::iter(vec![Ok(AgentEvent::Message(model_message(
            "partial answer",
        )))])
        .chain(futures::stream::once(async move {
            let _ = fire.send(());
            futures::future::pending::<anyhow::Result<AgentEvent>>().await
        }));
        let run = record_reply(&mut emitter, "gpt-4o-mini", None, Box::pin(stream), async {
            let _ = fired.await;
        });
        tokio::time::timeout(std::time::Duration::from_secs(5), run)
            .await
            .expect("an interrupt ends the reply loop")
            .unwrap();
        let events = sink.0.lock().unwrap().clone();
        let types: Vec<_> = events.iter().map(|e| e["type"].as_str().unwrap()).collect();
        assert_eq!(
            types,
            [
                "avp.agent_started",
                "avp.assistant_message",
                "avp.agent_stopped"
            ]
        );
        assert_eq!(
            events[1]["data"]["avp.content"][0]["text"],
            "partial answer"
        );
        assert_eq!(events[2]["data"]["avp.reason"], "interrupted");
    }

    #[tokio::test]
    async fn provider_failure_messages_close_with_error_without_a_fake_model_turn() {
        // These are the native forms emitted by the pinned Goose reply loop.
        let cases = [
            (Message::assistant().with_text(QUOTA_FAILURE), "rate_limit"),
            (Message::assistant().with_error(MessageErrorKind::Authentication, "bad credential"), "auth_error"),
            (Message::assistant().with_error(MessageErrorKind::ContextLengthExceeded, "too many tokens"), "context_limit"),
            (Message::assistant().with_error(MessageErrorKind::Other, "upstream server failed"), "agent_crash"),
            (Message::assistant().with_system_notification(SystemNotificationType::CreditsExhausted, "Please add credits"), "rate_limit"),
            (Message::assistant().with_text("Network error: connection reset\n\nPlease resend your message to try again."), "agent_crash"),
            (Message::assistant().with_text("Ran into this error trying to compact: unavailable.\n\nPlease try again or create a new session"), "agent_crash"),
            (Message::assistant().with_system_notification(SystemNotificationType::InlineMessage,
                "Unable to continue: Context limit still exceeded after compaction. Try using a shorter message, a model with a larger context window, or start a new session."), "context_limit"),
        ];
        for (message, code) in cases {
            let events = trajectory(vec![Ok(AgentEvent::Message(message))]).await;
            let types: Vec<_> = events.iter().map(|e| e["type"].as_str().unwrap()).collect();
            assert_eq!(
                types,
                [
                    "avp.agent_started",
                    "avp.error_occurred",
                    "avp.agent_stopped"
                ]
            );
            assert_eq!(events[1]["data"]["avp.error.code"], code);
            assert_eq!(events[2]["data"]["avp.reason"], "error");
        }
    }

    #[tokio::test]
    async fn provider_failure_preserves_buffered_model_output() {
        for failure in [
            Ok(AgentEvent::Message(
                Message::assistant().with_text(QUOTA_FAILURE),
            )),
            Err(anyhow::anyhow!("Rate limit exceeded")),
        ] {
            let events = trajectory(vec![
                Ok(AgentEvent::Message(model_message("Partial answer"))),
                failure,
            ])
            .await;
            let types: Vec<_> = events.iter().map(|e| e["type"].as_str().unwrap()).collect();
            assert_eq!(
                types,
                [
                    "avp.agent_started",
                    "avp.assistant_message",
                    "avp.error_occurred",
                    "avp.agent_stopped"
                ]
            );
            assert_eq!(
                events[1]["data"]["avp.content"][0]["text"],
                "Partial answer"
            );
            assert_eq!(events[2]["data"]["avp.error.code"], "rate_limit");
            assert_eq!(events[3]["data"]["avp.reason"], "error");
        }
    }

    #[tokio::test]
    async fn failure_notice_does_not_drop_trailing_usage() {
        let events = trajectory(vec![
            Ok(AgentEvent::Message(model_message("Partial answer"))),
            Ok(AgentEvent::Message(
                Message::assistant().with_text(QUOTA_FAILURE),
            )),
            Ok(AgentEvent::MessageUsage {
                message_id: Some("model-turn".into()),
                usage: goose::conversation::message::MessageUsage {
                    input_tokens: Some(10),
                    output_tokens: Some(2),
                    ..Default::default()
                },
            }),
        ])
        .await;
        assert_eq!(events[1]["type"], "avp.assistant_message");
        assert_eq!(events[1]["data"]["avp.usage"]["input_tokens"], 10);
        assert_eq!(events[1]["data"]["avp.usage"]["output_tokens"], 2);
        assert_eq!(events[2]["type"], "avp.error_occurred");
        assert_eq!(events[3]["data"]["avp.reason"], "error");
    }

    #[tokio::test]
    async fn quoted_provider_error_and_recovery_notice_do_not_fail_a_successful_reply() {
        let events = trajectory(vec![
            Ok(AgentEvent::Message(
                Message::assistant().with_system_notification(
                    SystemNotificationType::InlineMessage,
                    "Context limit reached. Compacting to continue conversation...",
                ),
            )),
            Ok(AgentEvent::Message(model_message(QUOTA_FAILURE))),
        ])
        .await;
        let types: Vec<_> = events.iter().map(|e| e["type"].as_str().unwrap()).collect();
        assert_eq!(
            types,
            [
                "avp.agent_started",
                "avp.assistant_message",
                "avp.agent_stopped"
            ]
        );
        assert_eq!(events[1]["data"]["avp.content"][0]["text"], QUOTA_FAILURE);
        assert_eq!(events[2]["data"]["avp.reason"], "converged");
    }

    #[test]
    fn tool_decls_filters_final_output_and_reshapes() {
        let raw = vec![
            json!({ "name": "developer__shell", "description": "run",
                    "inputSchema": { "type": "object" }, "annotations": { "x": 1 } }),
            json!({ "name": "recipe__final_output", "description": "internal",
                    "inputSchema": { "type": "object" } }),
            json!({ "name": "analyze__list_functions",
                    "outputSchema": { "type": "object", "properties": { "functions": { "type": "array" } } } }),
        ];
        // `analyze__list_functions` is surfaced by the `analyze` MCP server.
        let mcp: HashMap<String, String> =
            [("analyze__list_functions".to_string(), "analyze".to_string())].into();
        let decls = tool_decls(raw, &mcp);
        let names: Vec<&str> = decls.iter().map(|d| d["name"].as_str().unwrap()).collect();
        assert_eq!(names, vec!["developer__shell", "analyze__list_functions"]);
        // Local tool: only name/description/inputSchema, no mcp_server_id
        // and no outputSchema when the source tool doesn't declare one.
        assert_eq!(decls[0].as_object().unwrap().len(), 3);
        assert!(decls[0].get("avp.mcp_server_id").is_none());
        assert!(decls[0].get("outputSchema").is_none());
        // Missing inputSchema defaults to an object schema.
        assert_eq!(decls[1]["inputSchema"], json!({ "type": "object" }));
        // MCP-surfaced tool carries its server id and outputSchema verbatim.
        assert_eq!(decls[1]["avp.mcp_server_id"], "analyze");
        assert_eq!(
            decls[1]["outputSchema"],
            json!({ "type": "object", "properties": { "functions": { "type": "array" } } })
        );
    }
}
