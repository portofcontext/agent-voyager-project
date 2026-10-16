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
    AgentDescriptor, AvpContentItem, ErrorCode, StopReason, SubagentUsage, ToolUseBlock, Usage,
};
use serde_json::{Map, Value};

use crate::translate::{self, GooseContent};

/// Goose's `summon` platform extension. It exposes two tools: `delegate` (run a
/// subagent recipe) and `load` (pull content into context). Only `delegate` is a
/// subagent invocation; `load` is a plain tool call, which also returns a
/// background subagent's result.
const SUMMON_EXTENSION: &str = "summon";
const DELEGATE_TOOL: &str = "delegate";
const LOAD_TOOL: &str = "load";

/// Drives a single agent run's trajectory.
pub struct Emitter<S: Sink> {
    rec: Recorder<S>,
    /// Dispatch target per tool name, filled from each call's owning extension
    /// before the Recorder sees the call.
    targets: Arc<Mutex<HashMap<String, DispatchTarget>>>,
    mcp_servers: HashSet<String>,
    /// In-flight `delegate` calls, by call id, and whether each runs in the
    /// background. A foreground delegate's result closes its subagent frame.
    delegates: HashMap<String, bool>,
    /// Background subagents still running: child session id to the call id
    /// whose frame stays open until a `load` returns the result.
    background: HashMap<String, String>,
    /// In-flight `load` calls: call id to the `source` they load.
    loads: HashMap<String, String>,
    /// Subagent usage by child session id, attached when its frame closes.
    subagent_usage: HashMap<String, SubagentUsage>,
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
            delegates: HashMap::new(),
            background: HashMap::new(),
            loads: HashMap::new(),
            subagent_usage: HashMap::new(),
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
    pub fn on_usage(&mut self, usage: Usage, duration_ms: Option<u64>) -> std::io::Result<()> {
        self.rec.usage(usage, None, None, duration_ms)
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
                let summon = call.extension.as_deref() == Some(SUMMON_EXTENSION);
                if summon && call.name == DELEGATE_TOOL {
                    let name = call
                        .input
                        .get("source")
                        .and_then(Value::as_str)
                        .unwrap_or(&call.name)
                        .to_string();
                    let background = call.input.get("async").and_then(Value::as_bool) == Some(true);
                    delegated.push((call.id.clone(), name, background));
                } else if summon && call.name == LOAD_TOOL {
                    if let Some(source) = call.input.get("source").and_then(Value::as_str) {
                        self.loads.insert(call.id.clone(), source.to_string());
                    }
                }
                blocks.push(AvpContentItem::ToolUseBlock(ToolUseBlock {
                    id: call.id,
                    name: call.name,
                    input: call.input,
                    type_: "tool_use".to_string(),
                    extra: Default::default(),
                }));
            }
        }
        self.rec.assistant(blocks, usage, opts)?;
        for (id, name, background) in delegated {
            self.rec.subagent_start(&id, &name, None, None)?;
            self.delegates.insert(id, background);
        }
        Ok(())
    }

    /// Attach a subagent's usage, by its child session, to the frame that
    /// closes on it. Goose drops the child's per-response usage events, so the
    /// parent reads its session totals instead.
    pub fn on_subagent_usage(&mut self, session_id: &str, usage: SubagentUsage) {
        self.subagent_usage.insert(session_id.to_string(), usage);
    }

    /// The background subagent session a `load` call returns, if any.
    pub fn loaded_subagent(&self, call_id: &str) -> Option<&str> {
        self.loads
            .get(call_id)
            .filter(|source| self.background.contains_key(*source))
            .map(String::as_str)
    }

    /// Background subagents whose result was never loaded.
    pub fn background_subagents(&self) -> Vec<String> {
        self.background.keys().cloned().collect()
    }

    /// Report one tool-result message: a `tool_returned` per result paired to
    /// a prior call, plus `subagent_returned` for a foreground `delegate` call
    /// (mirroring the tool's error as `reason = error`) or a `load` of a
    /// background subagent's result. A background launch keeps its frame open.
    pub fn on_tool_results(&mut self, content: &[GooseContent]) -> std::io::Result<()> {
        for item in content {
            let Some(ret) = translate::as_tool_return(item) else {
                continue;
            };
            let block = translate::tool_result_block(&ret.id, &ret.output, ret.is_error);
            self.rec.tool_result(&ret.id, block, ret.is_error, None)?;
            let session = translate::subagent_session(&ret).map(str::to_string);
            let call = if let Some(background) = self.delegates.remove(&ret.id) {
                if let (true, false, Some(session)) = (background, ret.is_error, &session) {
                    self.background.insert(session.clone(), ret.id.clone());
                    continue;
                }
                ret.id.clone()
            } else if let Some(source) = self.loads.remove(&ret.id) {
                match self.background.remove(&source) {
                    Some(call) => {
                        self.close_subagent(&call, &ret, Some(&source))?;
                        continue;
                    }
                    None => continue,
                }
            } else {
                continue;
            };
            self.close_subagent(&call, &ret, session.as_deref())?;
        }
        Ok(())
    }

    fn close_subagent(
        &mut self,
        call: &str,
        ret: &translate::ToolReturn,
        session: Option<&str>,
    ) -> std::io::Result<()> {
        let reason = if ret.is_error {
            StopReason::Error
        } else {
            StopReason::Converged
        };
        let usage = session.and_then(|s| self.subagent_usage.remove(s));
        self.rec.subagent_result(
            call,
            &translate::result_text(&ret.output),
            reason,
            usage,
            None,
        )
    }

    /// Report a non-terminal `error_occurred` (e.g. a provider/stream error).
    pub fn error(&mut self, code: ErrorCode, message: &str) -> std::io::Result<()> {
        self.rec.error(code, message)
    }

    /// Close any open turn and frame, then emit `agent_stopped`. Idempotent.
    /// A background subagent whose result was never loaded closes as
    /// `abandoned`, carrying whatever it spent.
    pub fn stop(&mut self, reason: StopReason, output: Option<Value>) -> std::io::Result<()> {
        if !self.rec.is_stopped() {
            for (session, call) in std::mem::take(&mut self.background) {
                let usage = self.subagent_usage.remove(&session);
                self.rec
                    .subagent_result(&call, "", StopReason::Abandoned, usage, None)?;
            }
        }
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
