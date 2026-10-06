//! The trajectory's ordering and span rules, in one place.
//!
//! An adapter reports what its harness did; the [`Recorder`] decides what goes
//! on the wire and in what order. It is a plain value the adapter calls: no
//! trait to implement, no agent loop, no callbacks into the adapter.
//!
//! ```no_run
//! # use avp::recorder::{Recorder, RecorderOptions, AssistantOpts, StartInfo};
//! # use avp::trajectory::{StopReason, Usage};
//! # fn demo(descriptor: &avp::trajectory::AgentDescriptor) -> std::io::Result<()> {
//! let mut rec = Recorder::new(avp::StdioSink, RecorderOptions::default());
//! rec.prelude(None, descriptor)?;                    // run_requested, agent_described
//! rec.start(StartInfo::default())?;                  // agent_started
//! rec.assistant(vec![], None, AssistantOpts::default())?;  // assistant_message + tool_invoked
//! rec.tool_result("call_1", "ok".into(), false, None)?;   // tool_returned
//! rec.stop(StopReason::Converged, None)?;            // agent_stopped
//! # Ok(()) }
//! ```
//!
//! The rules match the Python `avp.recorder.Recorder` and are pinned by the
//! shared vectors under `avp/core/conformance/src/avp_conformance/recorder/v0.1/`
//! (run by `tests/recorder_vectors.rs`):
//!
//! - Span tree: agent span, then turn span, then `tool_invoked`, then
//!   `tool_returned`; subagent frames sit beside `tool_invoked` under the turn.
//! - Step counter: a turn with no output (no content beyond empty text, no
//!   events) is not put on the wire and does not consume a step.
//! - Turn buffering: `assistant_message` first, then everything reported while
//!   the turn was open, in arrival order, each with the time it was reported.
//!   The `assistant_message` is stamped with its last chunk's time.
//! - Turn delivery: chunks under the same `turn_key` merge until one of the
//!   turn's tool calls returns; a new key or no key closes the open turn, and a
//!   keyless turn closes at once.
//! - `tool_invoked` comes from the `tool_use` / `server_tool_use` blocks in an
//!   assistant turn's content; `tool_returned` pairs by call id.
//! - Subagent frames are run-scoped; frames open at stop close as `abandoned`
//!   and a `converged` stop downgrades to `abandoned`.
//! - Cost: `reported` when the adapter passes one, `unknown` for an unpriced
//!   model or a turn with no token counts, else `computed` from the price table.
//! - `stop` is idempotent; `error` parents under the agent span once started.

use std::collections::{HashMap, HashSet};
use std::io;
use std::time::Instant;

use chrono::{SecondsFormat, Utc};
use serde_json::{json, Map, Value};

use crate::ids::{new_event_id, new_span_id, new_trace_id, SOURCE_AGENT, ZERO_SPAN_ID};
use crate::pricing::{compute_cost, CostSource, PriceTable};
use crate::sink::Sink;
use crate::trajectory::{
    AgentDescriptor, AvpContentItem, ErrorCode, McpServerDecl, SkillDecl, StopReason, SubagentDecl,
    SubagentUsage, ToolDecl, Usage,
};
use crate::{Commission, Event};

/// Text carried by a subagent frame the Recorder closes at stop.
pub const ABANDONED_SUBAGENT_TEXT: &str =
    "Run ended while this subagent was still running; it never reported a result.";

/// Time source. `now_iso` stamps event `time`; `monotonic` (seconds) drives
/// every `duration_ms`.
pub trait Clock {
    fn now_iso(&self) -> String;
    fn monotonic(&self) -> f64;
}

/// Id source for the trace, spans, and CloudEvents `id`.
pub trait Ids {
    fn trace_id(&self) -> String;
    fn span_id(&self) -> String;
    fn event_id(&self) -> String;
}

pub struct SystemClock {
    origin: Instant,
}

impl Default for SystemClock {
    fn default() -> Self {
        Self {
            origin: Instant::now(),
        }
    }
}

impl Clock for SystemClock {
    fn now_iso(&self) -> String {
        Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true)
    }
    fn monotonic(&self) -> f64 {
        self.origin.elapsed().as_secs_f64()
    }
}

#[derive(Default)]
pub struct RandomIds;

impl Ids for RandomIds {
    fn trace_id(&self) -> String {
        new_trace_id()
    }
    fn span_id(&self) -> String {
        new_span_id()
    }
    fn event_id(&self) -> String {
        new_event_id()
    }
}

/// Wire value of `avp.tool.dispatch_target`.
pub type DispatchTarget = &'static str;

/// Constructor inputs. Everything is optional.
#[derive(Default)]
pub struct RecorderOptions {
    /// CloudEvents `subject` on every event; a fresh UUID if omitted.
    pub run_id: Option<String>,
    /// `avp.provider.name`, and the provider bare model names resolve under in
    /// `prices`.
    pub provider: Option<String>,
    /// Price table for computed cost. Empty means every turn is `unknown`
    /// unless the adapter reports a cost.
    pub prices: PriceTable,
    /// Classifies a tool name as `"mcp_server"` / `"local"`. Defaults to the
    /// catalog passed to `start` (a decl with `avp.mcp_server_id` is MCP).
    pub dispatch_target: Option<Box<dyn Fn(&str) -> DispatchTarget + Send>>,
    pub clock: Option<Box<dyn Clock + Send>>,
    pub ids: Option<Box<dyn Ids + Send>>,
}

/// `agent_started` inputs. `tools` is also the dispatch-target catalog.
#[derive(Default, Clone)]
pub struct StartInfo {
    pub request_model: Option<String>,
    pub prompt: Option<String>,
    pub system_prompt: Option<String>,
    pub tools: Option<Vec<ToolDecl>>,
    pub mcp_servers: Option<Vec<McpServerDecl>>,
    pub skills: Option<Vec<SkillDecl>>,
    pub subagents: Option<Vec<SubagentDecl>>,
    pub session_id: Option<String>,
    pub thread_id: Option<String>,
    pub tags: Option<Vec<String>>,
    pub meta: Option<Map<String, Value>>,
}

/// Per-chunk extras for [`Recorder::assistant`]. `model` is the response
/// model: `avp.response.model` on the wire and the price-table key; when the
/// table doesn't know it, cost is computed for `request_model` instead.
/// Within a turn `finish_reasons`,
/// `cost_usd`, and `duration_ms` are last-write-wins, `model` and
/// `request_model` first-write-wins, and `meta` keys merge.
#[derive(Default, Clone)]
pub struct AssistantOpts {
    pub model: Option<String>,
    pub request_model: Option<String>,
    pub turn_key: Option<String>,
    pub finish_reasons: Option<Vec<String>>,
    pub meta: Option<Map<String, Value>>,
    pub cost_usd: Option<f64>,
    pub duration_ms: Option<u64>,
}

struct Call {
    span_id: String,
    turn_span_id: String,
    step: u64,
    name: String,
    input: Value,
    started_at: f64,
}

struct Frame {
    span_id: String,
    parent_span_id: String,
    step: u64,
    name: String,
    started_at: f64,
}

struct Turn {
    key: Option<String>,
    step: u64,
    span_id: String,
    opened_at: f64,
    last_chunk_at: f64,
    last_chunk_iso: String,
    content: Vec<Value>,
    usage: Option<Usage>,
    response_model: Option<String>,
    request_model: Option<String>,
    finish_reasons: Option<Vec<String>>,
    meta: Map<String, Value>,
    cost_usd: Option<f64>,
    duration_ms: Option<u64>,
    emissions: Vec<Value>,
    call_ids: HashSet<String>,
    tool_resulted: bool,
}

impl Turn {
    fn has_output(&self) -> bool {
        !self.emissions.is_empty()
            || self
                .content
                .iter()
                .any(|b| !(b["type"] == "text" && b["text"].as_str().map_or(true, str::is_empty)))
    }
}

/// Builds one run's trajectory from what the adapter reports.
pub struct Recorder<S: Sink> {
    sink: S,
    clock: Box<dyn Clock + Send>,
    ids: Box<dyn Ids + Send>,
    run_id: String,
    trace_id: String,
    provider: Option<String>,
    prices: PriceTable,
    dispatch_override: Option<Box<dyn Fn(&str) -> DispatchTarget + Send>>,
    catalog: HashMap<String, bool>,
    agent_span_id: Option<String>,
    turn: Option<Turn>,
    last_step: u64,
    calls: HashMap<String, Call>,
    open_calls: HashSet<String>,
    frames: Vec<(String, Frame)>,
    stopped: bool,
}

fn to_value<T: serde::Serialize>(v: &T) -> Value {
    serde_json::to_value(v).expect("wire types serialize")
}

fn strip_nulls(mut v: Value) -> Value {
    if let Value::Object(m) = &mut v {
        m.retain(|_, x| !x.is_null());
    }
    v
}

impl<S: Sink> Recorder<S> {
    pub fn new(sink: S, opts: RecorderOptions) -> Self {
        let clock = opts
            .clock
            .unwrap_or_else(|| Box::new(SystemClock::default()));
        let ids = opts.ids.unwrap_or_else(|| Box::new(RandomIds));
        let run_id = opts.run_id.unwrap_or_else(|| ids.event_id());
        let trace_id = ids.trace_id();
        Self {
            sink,
            clock,
            ids,
            run_id,
            trace_id,
            provider: opts.provider,
            prices: opts.prices,
            dispatch_override: opts.dispatch_target,
            catalog: HashMap::new(),
            agent_span_id: None,
            turn: None,
            last_step: 0,
            calls: HashMap::new(),
            open_calls: HashSet::new(),
            frames: Vec::new(),
            stopped: false,
        }
    }

    pub fn run_id(&self) -> &str {
        &self.run_id
    }

    pub fn trace_id(&self) -> &str {
        &self.trace_id
    }

    pub fn is_stopped(&self) -> bool {
        self.stopped
    }

    pub fn sink(&self) -> &S {
        &self.sink
    }

    // ── envelope ─────────────────────────────────────────────────────────

    fn event(&self, ty: &str, time: String, span: &str, parent: &str, data: Value) -> Value {
        let mut d = Map::new();
        d.insert("trace_id".into(), self.trace_id.clone().into());
        d.insert("span_id".into(), span.into());
        d.insert("parent_span_id".into(), parent.into());
        if let Value::Object(m) = strip_nulls(data) {
            d.extend(m);
        }
        json!({
            "specversion": "1.0",
            "id": self.ids.event_id(),
            "time": time,
            "subject": self.run_id,
            "datacontenttype": "application/json",
            "type": format!("avp.{ty}"),
            "source": SOURCE_AGENT,
            "data": d,
        })
    }

    fn now_event(&self, ty: &str, span: &str, parent: &str, data: Value) -> Value {
        self.event(ty, self.clock.now_iso(), span, parent, data)
    }

    fn write(&self, event: Value) -> io::Result<()> {
        let typed: Event = serde_json::from_value(event).map_err(io::Error::other)?;
        self.sink.emit(&typed)
    }

    fn emit_or_buffer(&mut self, event: Value) -> io::Result<()> {
        match self.turn.as_mut() {
            Some(turn) => {
                turn.emissions.push(event);
                Ok(())
            }
            None => self.write(event),
        }
    }

    fn elapsed_ms(&self, since: f64) -> u64 {
        ((self.clock.monotonic() - since) * 1000.0).max(0.0) as u64
    }

    fn agent_parent(&self) -> String {
        self.agent_span_id
            .clone()
            .unwrap_or_else(|| ZERO_SPAN_ID.to_string())
    }

    // ── lifecycle ────────────────────────────────────────────────────────

    /// Emit `run_requested` (with the Commission and its supervisor
    /// attribution) then `agent_described`.
    pub fn prelude(
        &mut self,
        commission: Option<&Commission>,
        descriptor: &AgentDescriptor,
    ) -> io::Result<()> {
        let supervisor = commission.and_then(|c| c.supervisor.as_ref());
        let requested = self.now_event(
            "run_requested",
            &self.ids.span_id(),
            ZERO_SPAN_ID,
            json!({
                "avp.supervisor.name": supervisor.map(|s| to_value(&s.name)),
                "avp.supervisor.version": supervisor.and_then(|s| s.version.clone()),
                "avp.commission": commission.map(to_value),
            }),
        );
        self.write(requested)?;
        let described = self.now_event(
            "agent_described",
            &self.ids.span_id(),
            ZERO_SPAN_ID,
            json!({ "avp.descriptor": to_value(descriptor) }),
        );
        self.write(described)
    }

    /// Emit `agent_started` and open the agent span.
    pub fn start(&mut self, info: StartInfo) -> io::Result<()> {
        let span = self.ids.span_id();
        self.agent_span_id = Some(span.clone());
        self.catalog = info
            .tools
            .iter()
            .flatten()
            .map(|t| (t.name.clone(), t.avp_mcp_server_id.is_some()))
            .collect();
        let meta = info.meta.filter(|m| !m.is_empty());
        let event = self.now_event(
            "agent_started",
            &span,
            ZERO_SPAN_ID,
            json!({
                "avp.meta": meta,
                "avp.provider.name": self.provider,
                "avp.operation.name": "invoke_agent",
                "avp.request.model": info.request_model,
                "avp.prompt": info.prompt,
                "avp.system_prompt": info.system_prompt,
                "avp.tools": info.tools.as_ref().map(to_value),
                "avp.mcp_servers": info.mcp_servers.as_ref().map(to_value),
                "avp.skills": info.skills.as_ref().map(to_value),
                "avp.subagents": info.subagents.as_ref().map(to_value),
                "avp.session_id": info.session_id,
                "avp.thread_id": info.thread_id,
                "avp.tags": info.tags,
            }),
        );
        self.write(event)
    }

    /// Report `error_occurred` under the agent span (the root before `start`).
    /// Like every event reported while a turn is open, it lands after that
    /// turn's `assistant_message`. Not terminal; follow with `stop`.
    pub fn error(&mut self, code: ErrorCode, message: &str) -> io::Result<()> {
        let event = self.now_event(
            "error_occurred",
            &self.ids.span_id(),
            &self.agent_parent(),
            json!({ "avp.error.code": to_value(&code), "avp.error.message": message }),
        );
        self.emit_or_buffer(event)
    }

    /// Close the open turn and any open subagent frames, then emit
    /// `agent_stopped`. Idempotent: only the first call emits.
    pub fn stop(&mut self, reason: StopReason, output: Option<Value>) -> io::Result<()> {
        if self.stopped {
            return Ok(());
        }
        self.stopped = true;
        self.close_turn()?;
        let mut reason = reason;
        if !self.frames.is_empty() {
            let ids: Vec<String> = self.frames.iter().map(|(id, _)| id.clone()).collect();
            for id in ids {
                self.close_frame(
                    &id,
                    ABANDONED_SUBAGENT_TEXT,
                    StopReason::Abandoned,
                    None,
                    None,
                )?;
            }
            if reason == StopReason::Converged {
                reason = StopReason::Abandoned;
            }
        }
        let event = self.now_event(
            "agent_stopped",
            &self.ids.span_id(),
            &self.agent_parent(),
            json!({ "avp.reason": to_value(&reason), "avp.output": output }),
        );
        self.write(event)
    }

    // ── turns ────────────────────────────────────────────────────────────

    /// Report model output for one inference (or one chunk of it).
    pub fn assistant(
        &mut self,
        content: Vec<AvpContentItem>,
        usage: Option<Usage>,
        opts: AssistantOpts,
    ) -> io::Result<()> {
        if self.agent_span_id.is_none() {
            return Err(io::Error::other("Recorder::assistant called before start"));
        }
        let merge = match (&self.turn, &opts.turn_key) {
            (Some(t), Some(k)) => !t.tool_resulted && t.key.as_deref() == Some(k.as_str()),
            _ => false,
        };
        if !merge {
            self.close_turn()?;
        }
        let now = self.clock.monotonic();
        let now_iso = self.clock.now_iso();
        if self.turn.is_none() {
            self.turn = Some(Turn {
                key: opts.turn_key.clone(),
                step: self.last_step + 1,
                span_id: self.ids.span_id(),
                opened_at: now,
                last_chunk_at: now,
                last_chunk_iso: now_iso.clone(),
                content: Vec::new(),
                usage: None,
                response_model: None,
                request_model: None,
                finish_reasons: None,
                meta: Map::new(),
                cost_usd: None,
                duration_ms: None,
                emissions: Vec::new(),
                call_ids: HashSet::new(),
                tool_resulted: false,
            });
        }
        let blocks: Vec<Value> = content.iter().map(to_value).collect();
        {
            let turn = self.turn.as_mut().expect("turn opened above");
            turn.last_chunk_at = now;
            turn.last_chunk_iso = now_iso;
            turn.content.extend(blocks.iter().cloned());
            if usage.is_some() {
                turn.usage = usage;
            }
            if turn.response_model.is_none() {
                turn.response_model = opts.model;
            }
            if turn.request_model.is_none() {
                turn.request_model = opts.request_model;
            }
            if opts.finish_reasons.is_some() {
                turn.finish_reasons = opts.finish_reasons;
            }
            if let Some(meta) = opts.meta {
                turn.meta.extend(meta);
            }
            if opts.cost_usd.is_some() {
                turn.cost_usd = opts.cost_usd;
            }
            if opts.duration_ms.is_some() {
                turn.duration_ms = opts.duration_ms;
            }
        }
        for block in &blocks {
            match block["type"].as_str() {
                Some("tool_use") | Some("server_tool_use") => {
                    let id = block["id"].as_str().unwrap_or_default().to_string();
                    let name = block["name"].as_str().unwrap_or_default().to_string();
                    self.invoke(id, name, block["input"].clone());
                }
                Some("server_tool_result") => {
                    let id = block["tool_use_id"]
                        .as_str()
                        .unwrap_or_default()
                        .to_string();
                    let result = json!({
                        "type": "tool_result",
                        "tool_use_id": id,
                        "content": result_content(&block["content"]),
                        "is_error": block["is_error"].as_bool().unwrap_or(false),
                    });
                    self.tool_result(&id, result, false, None)?;
                }
                _ => {}
            }
        }
        if opts.turn_key.is_none() {
            self.close_turn()?;
        }
        Ok(())
    }

    /// Report usage for the open turn after its content, for harnesses that
    /// deliver token counts once the inference (or its tool round) is over.
    /// Keep the turn open with a `turn_key` until then. Applies to the open
    /// turn when `turn_key` is `None` or matches it; otherwise dropped.
    pub fn usage(
        &mut self,
        usage: Usage,
        turn_key: Option<&str>,
        cost_usd: Option<f64>,
        duration_ms: Option<u64>,
    ) {
        let Some(turn) = self.turn.as_mut() else {
            return;
        };
        if turn_key.is_some_and(|k| turn.key.as_deref() != Some(k)) {
            return;
        }
        turn.usage = Some(usage);
        if cost_usd.is_some() {
            turn.cost_usd = cost_usd;
        }
        if duration_ms.is_some() {
            turn.duration_ms = duration_ms;
        }
    }

    fn invoke(&mut self, call_id: String, name: String, input: Value) {
        let span = self.ids.span_id();
        let target = self.dispatch_target(&name);
        let started_at = self.clock.monotonic();
        let turn = self.turn.as_ref().expect("invoke inside an open turn");
        let (turn_span, step) = (turn.span_id.clone(), turn.step);
        let event = self.now_event(
            "tool_invoked",
            &span,
            &turn_span,
            json!({
                "avp.step": step,
                "avp.tool.call_id": call_id,
                "avp.tool.name": name,
                "avp.tool.input": input,
                "avp.tool.dispatch_target": target,
            }),
        );
        let turn = self.turn.as_mut().expect("invoke inside an open turn");
        turn.call_ids.insert(call_id.clone());
        turn.emissions.push(event);
        self.open_calls.insert(call_id.clone());
        self.calls.insert(
            call_id,
            Call {
                span_id: span,
                turn_span_id: turn_span,
                step,
                name,
                input,
                started_at,
            },
        );
    }

    fn dispatch_target(&self, name: &str) -> DispatchTarget {
        if let Some(f) = &self.dispatch_override {
            return f(name);
        }
        if self.catalog.get(name).copied().unwrap_or(false) {
            "mcp_server"
        } else {
            "local"
        }
    }

    /// Close the open turn now: its `assistant_message` (with cost), then its
    /// buffered events. A turn with no output emits nothing and frees its
    /// step. No-op when no turn is open.
    pub fn close_turn(&mut self) -> io::Result<()> {
        let Some(turn) = self.turn.take() else {
            return Ok(());
        };
        if !turn.has_output() {
            return Ok(());
        }
        self.last_step = turn.step;
        let usage = turn.usage.clone().unwrap_or(Usage {
            cache_creation_input_tokens: None,
            cache_read_input_tokens: None,
            input_tokens: 0,
            output_tokens: 0,
            reasoning_output_tokens: None,
        });
        let (cost_usd, cost_source) = if let Some(c) = turn.cost_usd {
            (c, CostSource::Reported)
        } else if usage.input_tokens == 0 && usage.output_tokens == 0 {
            (0.0, CostSource::Unknown)
        } else {
            // Providers often answer with a dated snapshot id the table lacks
            // (`gpt-4o-mini-2024-07-18`); price it as the requested model then.
            let mut candidates = vec![
                turn.response_model.as_deref(),
                turn.request_model.as_deref(),
            ];
            candidates.dedup();
            candidates
                .into_iter()
                .flatten()
                .map(|model| {
                    compute_cost(
                        self.provider.as_deref(),
                        model,
                        usage.input_tokens,
                        usage.output_tokens,
                        usage.cache_read_input_tokens.unwrap_or(0),
                        usage.cache_creation_input_tokens.unwrap_or(0),
                        &self.prices,
                    )
                })
                .find(|(_, source)| *source != CostSource::Unknown)
                .unwrap_or((0.0, CostSource::Unknown))
        };
        let duration_ms = turn
            .duration_ms
            .unwrap_or_else(|| ((turn.last_chunk_at - turn.opened_at) * 1000.0).max(0.0) as u64);
        let agent_span = self.agent_parent();
        let meta = (!turn.meta.is_empty()).then(|| Value::Object(turn.meta.clone()));
        let message = self.event(
            "assistant_message",
            turn.last_chunk_iso.clone(),
            &turn.span_id,
            &agent_span,
            json!({
                "avp.meta": meta,
                "avp.step": turn.step,
                "avp.duration_ms": duration_ms,
                "avp.content": turn.content,
                "avp.provider.name": self.provider,
                "avp.request.model": turn.request_model.clone().or(turn.response_model.clone()),
                "avp.response.model": turn.response_model,
                "avp.response.finish_reasons": turn.finish_reasons,
                "avp.usage": to_value(&usage),
                "avp.cost_usd": cost_usd,
                "avp.cost.source": cost_source_wire(cost_source),
            }),
        );
        self.write(message)?;
        for event in turn.emissions {
            self.write(event)?;
        }
        Ok(())
    }

    // ── tools ────────────────────────────────────────────────────────────

    /// Report the result of a tool call seen in assistant content. `content`
    /// is the `ToolResultBlock.content` (a string or an array of blocks), or a
    /// whole `tool_result` block. A result for an unknown or already returned
    /// call id is dropped.
    pub fn tool_result(
        &mut self,
        call_id: &str,
        content: Value,
        is_error: bool,
        structured_content: Option<Map<String, Value>>,
    ) -> io::Result<()> {
        if !self.open_calls.remove(call_id) {
            return Ok(());
        }
        let block = if content.get("type").and_then(Value::as_str) == Some("tool_result") {
            content
        } else {
            strip_nulls(json!({
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": content,
                "structured_content": structured_content,
                "is_error": is_error,
            }))
        };
        let call = &self.calls[call_id];
        let (call_span, step, name) = (call.span_id.clone(), call.step, call.name.clone());
        let duration_ms = self.elapsed_ms(call.started_at);
        let event = self.now_event(
            "tool_returned",
            &self.ids.span_id(),
            &call_span,
            json!({
                "avp.step": step,
                "avp.tool.call_id": call_id,
                "avp.tool.name": name,
                "avp.duration_ms": duration_ms,
                "avp.tool_result": block,
            }),
        );
        if let Some(turn) = self.turn.as_mut() {
            if turn.call_ids.contains(call_id) {
                turn.tool_resulted = true;
            }
        }
        self.emit_or_buffer(event)
    }

    // ── subagents ────────────────────────────────────────────────────────

    /// Open a subagent frame. When `invocation_id` is a tool call seen in
    /// assistant content, the frame sits under that call's turn and defaults
    /// its input to the call's input.
    pub fn subagent_start(
        &mut self,
        invocation_id: &str,
        name: &str,
        input: Option<Value>,
        description: Option<&str>,
    ) -> io::Result<()> {
        let (parent, step, frame_input) = if let Some(call) = self.calls.get(invocation_id) {
            (
                call.turn_span_id.clone(),
                call.step,
                input.unwrap_or_else(|| call.input.clone()),
            )
        } else if let Some(turn) = &self.turn {
            (
                turn.span_id.clone(),
                turn.step,
                input.unwrap_or_else(|| json!({})),
            )
        } else {
            (
                self.agent_parent(),
                self.last_step,
                input.unwrap_or_else(|| json!({})),
            )
        };
        let span = self.ids.span_id();
        let started_at = self.clock.monotonic();
        self.frames.retain(|(id, _)| id != invocation_id);
        self.frames.push((
            invocation_id.to_string(),
            Frame {
                span_id: span.clone(),
                parent_span_id: parent.clone(),
                step,
                name: name.to_string(),
                started_at,
            },
        ));
        let event = self.now_event(
            "subagent_invoked",
            &span,
            &parent,
            json!({
                "avp.step": step,
                "avp.subagent.name": name,
                "avp.subagent.description": description,
                "avp.subagent.invocation_id": invocation_id,
                "avp.subagent.input": frame_input,
            }),
        );
        self.emit_or_buffer(event)
    }

    /// Close a subagent frame. A result for an unknown or already closed
    /// frame is dropped.
    pub fn subagent_result(
        &mut self,
        invocation_id: &str,
        text: &str,
        reason: StopReason,
        usage: Option<SubagentUsage>,
        structured: Option<Value>,
    ) -> io::Result<()> {
        if !self.frames.iter().any(|(id, _)| id == invocation_id) {
            return Ok(());
        }
        self.close_frame(invocation_id, text, reason, usage, structured)
    }

    fn close_frame(
        &mut self,
        invocation_id: &str,
        text: &str,
        reason: StopReason,
        usage: Option<SubagentUsage>,
        structured: Option<Value>,
    ) -> io::Result<()> {
        let idx = self
            .frames
            .iter()
            .position(|(id, _)| id == invocation_id)
            .expect("open frame");
        let (_, frame) = self.frames.remove(idx);
        let event = self.now_event(
            "subagent_returned",
            &frame.span_id,
            &frame.parent_span_id,
            json!({
                "avp.step": frame.step,
                "avp.subagent.name": frame.name,
                "avp.subagent.invocation_id": invocation_id,
                "avp.duration_ms": self.elapsed_ms(frame.started_at),
                "avp.subagent.result.text": text,
                "avp.subagent.result.structured": structured,
                "avp.subagent.reason": to_value(&reason),
                "avp.subagent.usage": usage.as_ref().map(to_value),
            }),
        );
        self.emit_or_buffer(event)
    }
}

fn cost_source_wire(source: CostSource) -> &'static str {
    match source {
        CostSource::Computed => "computed",
        CostSource::Reported => "reported",
        CostSource::Unknown => "unknown",
    }
}

/// A server tool's inline result (provider-shaped, not AVP blocks) as
/// `ToolResultBlock.content`: strings pass through, anything else is
/// JSON-encoded the way Python's `json.dumps` does.
fn result_content(content: &Value) -> Value {
    match content {
        Value::Null => Value::String(String::new()),
        Value::String(_) => content.clone(),
        other => Value::String(python_json(other)),
    }
}

/// `json.dumps` default separators (`", "` and `": "`), so both bindings
/// encode the same payload to the same string.
fn python_json(v: &Value) -> String {
    match v {
        Value::Array(items) => {
            format!(
                "[{}]",
                items.iter().map(python_json).collect::<Vec<_>>().join(", ")
            )
        }
        Value::Object(m) => format!(
            "{{{}}}",
            m.iter()
                .map(|(k, v)| format!("{}: {}", Value::String(k.clone()), python_json(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        other => other.to_string(),
    }
}
