//! Goose stream activity in, `avp::recorder::Recorder` calls out.
//!
//! The Recorder owns the trajectory's ordering and span rules. This module
//! keeps what is Goose-specific: projecting Goose content onto AVP blocks
//! (`translate`), classifying a tool's dispatch target from its owning
//! extension, surfacing `summon`/`delegate` calls as subagent frames, and
//! mapping Goose errors and run endings to AVP codes and stop reasons.

use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};

use avp::pricing::PriceTable;
use avp::recorder::{AssistantOpts, DispatchTarget, Recorder, RecorderOptions, StartInfo};
use avp::sink::Sink;
use avp::trajectory::{
    AgentDescriptor, AvpContentItem, ErrorCode, StopReason, ToolUseBlock, Usage,
};
use serde_json::{Map, Value};

use crate::translate::{self, GooseContent};

/// Goose's `summon` platform extension. It exposes two tools: `delegate` (run a
/// subagent recipe) and `load` (pull content into context). Only `delegate` is a
/// subagent invocation; `load` is a plain tool call.
const SUMMON_EXTENSION: &str = "summon";
const DELEGATE_TOOL: &str = "delegate";

/// Drives a single agent run's trajectory.
pub struct Emitter<S: Sink> {
    rec: Recorder<S>,
    /// Dispatch target per tool name, filled from each call's owning extension
    /// before the Recorder sees the call.
    targets: Arc<Mutex<HashMap<String, DispatchTarget>>>,
    mcp_servers: HashSet<String>,
    /// Call ids of in-flight `delegate` calls: their result also closes a
    /// subagent frame.
    delegates: HashSet<String>,
    /// Captured in `prelude`; `start` mirrors its surface onto `agent_started`.
    descriptor: Option<AgentDescriptor>,
}

impl<S: Sink> Emitter<S> {
    /// `mcp_servers` is the set of extension names that are MCP servers (for
    /// tool dispatch-target classification).
    pub fn new(
        sink: S,
        run_id: impl Into<String>,
        provider: Option<String>,
        mcp_servers: HashSet<String>,
        prices: PriceTable,
    ) -> Self {
        let targets: Arc<Mutex<HashMap<String, DispatchTarget>>> = Arc::default();
        let lookup = targets.clone();
        let rec = Recorder::new(
            sink,
            RecorderOptions {
                run_id: Some(run_id.into()),
                provider,
                prices,
                dispatch_target: Some(Box::new(move |name: &str| {
                    lookup.lock().unwrap().get(name).copied().unwrap_or("local")
                })),
                ..Default::default()
            },
        );
        Self {
            rec,
            targets,
            mcp_servers,
            delegates: HashSet::new(),
            descriptor: None,
        }
    }

    /// Emit `run_requested` (carrying the Commission) then `agent_described`.
    pub fn prelude(
        &mut self,
        commission: &avp::Commission,
        descriptor: &AgentDescriptor,
    ) -> std::io::Result<()> {
        self.descriptor = Some(descriptor.clone());
        self.rec.prelude(Some(commission), descriptor)
    }

    /// Emit `agent_started`. We apply no mid-run Commission filtering beyond
    /// what is baked into the loaded extensions (e.g. `enabled_builtin_tools`
    /// -> the developer extension's `available_tools`), so it mirrors the
    /// descriptor's tools / subagents / MCP servers / skills. The wrapped Goose
    /// version is provenance and rides as an opaque meta annotation.
    pub fn start(&mut self, model: Option<&str>) -> std::io::Result<()> {
        let d = self.descriptor.as_ref();
        let mut meta = Map::new();
        meta.insert(
            "goose.upstream_version".into(),
            env!("GOOSE_VERSION").into(),
        );
        self.rec.start(StartInfo {
            request_model: model.map(str::to_string),
            tools: d.and_then(|d| d.tools.clone()),
            mcp_servers: d.and_then(|d| d.mcp_servers.clone()),
            skills: d.and_then(|d| d.skills.clone()),
            subagents: d.and_then(|d| d.subagents.clone()),
            meta: Some(meta),
            ..Default::default()
        })
    }

    /// Report one complete assistant inference with its usage; the turn
    /// closes at once.
    pub fn on_assistant(
        &mut self,
        content: &[GooseContent],
        usage: Usage,
        model: Option<String>,
        duration_ms: Option<u64>,
    ) -> std::io::Result<()> {
        self.report(
            content,
            AssistantOpts {
                model,
                duration_ms,
                ..Default::default()
            },
            Some(usage),
        )
    }

    /// Report one assistant inference whose usage arrives later (Goose's
    /// `MessageUsage`, after the turn's tool results). The turn stays open
    /// under `turn_key` until [`Emitter::on_usage`] fills it in and the next
    /// inference (or the stop) closes it.
    pub fn on_inference(
        &mut self,
        content: &[GooseContent],
        model: Option<String>,
        turn_key: String,
        duration_ms: Option<u64>,
    ) -> std::io::Result<()> {
        self.report(
            content,
            AssistantOpts {
                model,
                turn_key: Some(turn_key),
                duration_ms,
                ..Default::default()
            },
            None,
        )
    }

    /// Usage for the open turn (see [`Emitter::on_inference`]).
    pub fn on_usage(&mut self, usage: Usage, duration_ms: Option<u64>) {
        self.rec.usage(usage, None, None, duration_ms);
    }

    /// Tool requests become `tool_use` blocks (the Recorder derives
    /// `tool_invoked` from them); a `summon`/`delegate` request also opens a
    /// subagent frame named after the delegated recipe (its `source` argument).
    fn report(
        &mut self,
        content: &[GooseContent],
        opts: AssistantOpts,
        usage: Option<Usage>,
    ) -> std::io::Result<()> {
        let mut blocks = Vec::new();
        let mut delegated = Vec::new();
        for item in content {
            if let Some(block) = translate::to_content_block(item) {
                blocks.push(block);
            } else if let Some(call) = translate::as_tool_call(item) {
                let target =
                    translate::dispatch_target(call.extension.as_deref(), &self.mcp_servers);
                self.targets
                    .lock()
                    .unwrap()
                    .insert(call.name.clone(), target);
                if call.extension.as_deref() == Some(SUMMON_EXTENSION) && call.name == DELEGATE_TOOL
                {
                    let name = call
                        .input
                        .get("source")
                        .and_then(Value::as_str)
                        .unwrap_or(&call.name)
                        .to_string();
                    delegated.push((call.id.clone(), name));
                }
                blocks.push(AvpContentItem::ToolUseBlock(ToolUseBlock {
                    id: call.id,
                    name: call.name,
                    input: call.input,
                    type_: "tool_use".to_string(),
                }));
            }
        }
        self.rec.assistant(blocks, usage, opts)?;
        for (id, name) in delegated {
            self.rec.subagent_start(&id, &name, None, None)?;
            self.delegates.insert(id);
        }
        Ok(())
    }

    /// Report one tool-result message: a `tool_returned` per result paired to
    /// a prior call, plus `subagent_returned` for a `delegate` call (mirroring
    /// the tool's error as `reason = error`).
    pub fn on_tool_results(&mut self, content: &[GooseContent]) -> std::io::Result<()> {
        for item in content {
            let Some(ret) = translate::as_tool_return(item) else {
                continue;
            };
            let block = translate::tool_result_block(&ret.id, &ret.output, ret.is_error);
            self.rec.tool_result(&ret.id, block, ret.is_error, None)?;
            if self.delegates.remove(&ret.id) {
                let reason = if ret.is_error {
                    StopReason::Error
                } else {
                    StopReason::Converged
                };
                self.rec.subagent_result(
                    &ret.id,
                    &translate::result_text(&ret.output),
                    reason,
                    None,
                    None,
                )?;
            }
        }
        Ok(())
    }

    /// Report a non-terminal `error_occurred` (e.g. a provider/stream error).
    pub fn error(&mut self, code: ErrorCode, message: &str) -> std::io::Result<()> {
        self.rec.error(code, message)
    }

    /// Close any open turn and frame, then emit `agent_stopped`. Idempotent.
    pub fn stop(&mut self, reason: StopReason, output: Option<Value>) -> std::io::Result<()> {
        self.rec.stop(reason, output)
    }
}

/// Best-effort mapping of a provider/stream error to an AVP `ErrorCode`.
pub fn classify_error(message: &str) -> ErrorCode {
    let m = message.to_lowercase();
    if m.contains("rate limit") || m.contains("rate_limit") || m.contains("429") {
        ErrorCode::RateLimit
    } else if m.contains("context") || m.contains("token limit") || m.contains("too long") {
        ErrorCode::ContextLimit
    } else if m.contains("unauthorized")
        || m.contains("401")
        || m.contains("api key")
        || m.contains("auth")
    {
        ErrorCode::AuthError
    } else {
        ErrorCode::AgentCrash
    }
}

/// Infer the AVP stop reason from terminal run signals. Precedence: an explicit
/// refusal, then operator interruption (cancel), then a clean end, else error.
pub fn classify_stop(ended_ok: bool, cancelled: bool, refused: bool) -> StopReason {
    if refused {
        StopReason::Refused
    } else if cancelled {
        StopReason::Interrupted
    } else if ended_ok {
        StopReason::Converged
    } else {
        StopReason::Error
    }
}
