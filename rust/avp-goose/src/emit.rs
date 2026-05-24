//! Event emitter: dispatches Goose stream activity into an AVP trajectory.
//!
//! The emitter is the stateful glue between `translate` (projection) and
//! `runstate` (turn buffering). It owns the span hierarchy:
//!
//! ```text
//! agent_started/agent_stopped  span = agent span,  parent = ZERO (root)
//!   assistant_message (turn)   span = turn span,   parent = agent span
//!     tool_invoked             span = invoked span, parent = turn span
//!       tool_returned          span = returned span, parent = invoked span
//! ```
//!
//! Goose surfaces a tool result in a *later* message than the assistant turn
//! that requested it, so `tool_invoked` is buffered into the turn (flushed
//! after `assistant_message`), while the matching `tool_returned` is emitted
//! directly when the result arrives, paired by tool-call id.

use std::collections::{HashMap, HashSet};
use std::time::Instant;

use avp::commission::AvpV01CommissionMcpServersItem;
use avp::ids::{new_span_id, new_trace_id, ZERO_SPAN_ID};
use avp::pricing::PriceTable;
use avp::sink::Sink;
use avp::trajectory::{ErrorCode, StopReason, Usage};

use crate::events;
use crate::runstate::RunState;
use crate::translate::{self, GooseContent};

/// An in-flight tool invocation awaiting its result.
/// Goose extension that delegates to subagents; its calls become AVP
/// `subagent_*` events rather than `tool_*`.
const SUMMON_EXTENSION: &str = "summon";

struct PendingTool {
    step: u64,
    /// Invocation span; becomes the parent span of the return/failed event.
    invoked_span: String,
    name: String,
    started_at: Instant,
    /// A `summon` (subagent) call vs. a plain tool call.
    is_subagent: bool,
}

/// Drives a single agent run's trajectory.
pub struct Emitter<S: Sink> {
    state: RunState<S>,
    mcp_servers: HashSet<String>,
    pending: HashMap<String, PendingTool>,
    stopped: bool,
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
        let state = RunState::new(
            sink,
            run_id,
            new_trace_id(),
            new_span_id(),
            provider,
            prices,
        );
        Self {
            state,
            mcp_servers,
            pending: HashMap::new(),
            stopped: false,
        }
    }

    /// Emit the run prelude: `run_requested` (carrying the Commission) then
    /// `agent_described` (the static descriptor). Call once, before `start`.
    pub fn prelude(
        &mut self,
        commission: &avp::Commission,
        descriptor: &avp::trajectory::AgentDescriptor,
    ) -> std::io::Result<()> {
        let requested = events::run_requested(
            &self.state.run_id,
            &self.state.trace_id,
            &new_span_id(),
            ZERO_SPAN_ID,
            commission,
        );
        self.state.emit(&requested)?;
        let described = events::agent_described(
            &self.state.run_id,
            &self.state.trace_id,
            &new_span_id(),
            ZERO_SPAN_ID,
            descriptor,
        );
        self.state.emit(&described)?;

        // Synthesize an mcp_server_connected for each Commission MCP server,
        // with a tool count derived from the descriptor (Goose has no connect
        // events on the stream). `{id}__` is Goose's tool-name prefix.
        for server in commission.mcp_servers.iter().flatten() {
            let id = match server {
                AvpV01CommissionMcpServersItem::Stdio(x) => x.id.to_string(),
                AvpV01CommissionMcpServersItem::Http(x) => x.id.to_string(),
            };
            let prefix = format!("{id}__");
            let tool_count = descriptor.tools.as_ref().map_or(0, |tools| {
                tools.iter().filter(|t| t.name.starts_with(&prefix)).count()
            }) as u64;
            let connected = events::mcp_server_connected(
                &self.state.run_id,
                &self.state.trace_id,
                &new_span_id(),
                ZERO_SPAN_ID,
                &id,
                tool_count,
            );
            self.state.emit(&connected)?;
        }
        Ok(())
    }

    /// Emit `agent_started` (loop entry). Call once, before any messages.
    pub fn start(&mut self, model: Option<&str>) -> std::io::Result<()> {
        let ev = events::agent_started(
            &self.state.run_id,
            &self.state.trace_id,
            &self.state.agent_span_id,
            ZERO_SPAN_ID,
            self.state.provider.as_deref(),
            model,
        );
        self.state.emit(&ev)
    }

    /// Process one assistant message: accumulate its content, buffer a
    /// `tool_invoked` for each tool request, attach usage, then drain the turn
    /// (one `assistant_message` followed by the buffered invocations).
    pub fn on_assistant(
        &mut self,
        content: &[GooseContent],
        usage: Usage,
        model: Option<String>,
    ) -> std::io::Result<()> {
        let (step, turn_span) = self.state.open_turn();
        for item in content {
            if let Some(block) = translate::to_content_block(item) {
                self.state.push_content(block);
            } else if let Some(call) = translate::as_tool_call(item) {
                let invoked_span = new_span_id();
                let is_subagent = call.extension.as_deref() == Some(SUMMON_EXTENSION);
                let ev = if is_subagent {
                    events::subagent_invoked(
                        &self.state.run_id,
                        &self.state.trace_id,
                        &invoked_span,
                        &turn_span,
                        step,
                        &call.id,
                        &call.name,
                        call.input.clone(),
                    )
                } else {
                    let dispatch =
                        translate::dispatch_target(call.extension.as_deref(), &self.mcp_servers);
                    events::tool_invoked(
                        &self.state.run_id,
                        &self.state.trace_id,
                        &invoked_span,
                        &turn_span,
                        step,
                        &call.id,
                        &call.name,
                        call.input.clone(),
                        Some(dispatch),
                    )
                };
                self.state.buffer_event(ev);
                self.pending.insert(
                    call.id.clone(),
                    PendingTool {
                        step,
                        invoked_span,
                        name: call.name,
                        started_at: Instant::now(),
                        is_subagent,
                    },
                );
            }
        }
        self.state.set_usage(usage, model);
        self.state.drain()
    }

    /// Process one tool-result message: emit a `tool_returned` for each result
    /// paired to a prior invocation. Unpaired results are ignored.
    pub fn on_tool_results(&mut self, content: &[GooseContent]) -> std::io::Result<()> {
        for item in content {
            let Some(ret) = translate::as_tool_return(item) else {
                continue;
            };
            let Some(pending) = self.pending.remove(&ret.id) else {
                continue;
            };
            let duration_ms = pending.started_at.elapsed().as_millis() as u64;
            let span = new_span_id();
            let ev = if pending.is_subagent {
                if ret.is_error {
                    let error = ret
                        .output
                        .as_str()
                        .map(str::to_string)
                        .unwrap_or_else(|| ret.output.to_string());
                    events::subagent_failed(
                        &self.state.run_id,
                        &self.state.trace_id,
                        &span,
                        &pending.invoked_span,
                        pending.step,
                        &ret.id,
                        &pending.name,
                        duration_ms,
                        &error,
                    )
                } else {
                    events::subagent_returned(
                        &self.state.run_id,
                        &self.state.trace_id,
                        &span,
                        &pending.invoked_span,
                        pending.step,
                        &ret.id,
                        &pending.name,
                        duration_ms,
                        &ret.output,
                        StopReason::Converged,
                    )
                }
            } else {
                let block = events::tool_result_block(&ret.id, &ret.output, ret.is_error);
                events::tool_returned(
                    &self.state.run_id,
                    &self.state.trace_id,
                    &span,
                    &pending.invoked_span,
                    pending.step,
                    &ret.id,
                    &pending.name,
                    duration_ms,
                    block,
                )
            };
            self.state.emit(&ev)?;
        }
        Ok(())
    }

    /// Emit a non-terminal `error_occurred` (e.g. a provider/stream error),
    /// parented to the agent span.
    pub fn error(&mut self, code: ErrorCode, message: &str) -> std::io::Result<()> {
        let event = events::error_occurred(
            &self.state.run_id,
            &self.state.trace_id,
            &new_span_id(),
            &self.state.agent_span_id,
            code,
            message,
        );
        self.state.emit(&event)
    }

    /// Flush any open turn and emit the terminal `agent_stopped`. Idempotent.
    pub fn stop(
        &mut self,
        reason: StopReason,
        output: Option<serde_json::Value>,
    ) -> std::io::Result<()> {
        if self.stopped {
            return Ok(());
        }
        self.stopped = true;
        self.state.drain()?;
        let ev = events::agent_stopped(
            &self.state.run_id,
            &self.state.trace_id,
            &self.state.agent_span_id,
            ZERO_SPAN_ID,
            reason,
            output,
        );
        self.state.emit(&ev)
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testkit::CapturingSink;
    use avp::pricing::load_default_prices;

    fn content(raw: &str) -> Vec<GooseContent> {
        serde_json::from_str(raw).expect("content")
    }

    fn usage() -> Usage {
        Usage {
            input_tokens: 100,
            output_tokens: 50,
            cache_read_input_tokens: None,
            cache_creation_input_tokens: None,
            reasoning_output_tokens: None,
        }
    }

    fn emitter(sink: CapturingSink) -> Emitter<CapturingSink> {
        let mcp: HashSet<String> = ["avptest".to_string()].into_iter().collect();
        Emitter::new(
            sink,
            "r1",
            Some("anthropic".to_string()),
            mcp,
            load_default_prices(),
        )
    }

    #[test]
    fn full_round_emits_ordered_trajectory_with_span_hierarchy() {
        let sink = CapturingSink::default();
        let mut em = emitter(sink.clone());

        em.start(Some("claude-opus-4-7")).unwrap();
        em.on_assistant(
            &content(
                r#"[{"type":"text","text":"on it"},
                    {"type":"toolRequest","id":"call_1",
                     "toolCall":{"status":"success",
                       "value":{"name":"developer__shell","arguments":{"command":"ls"}}}}]"#,
            ),
            usage(),
            Some("claude-opus-4-7".to_string()),
        )
        .unwrap();
        em.on_tool_results(&content(
            r#"[{"type":"toolResponse","id":"call_1",
                "toolResult":{"status":"success","value":{"content":[{"type":"text","text":"a\nb"}]}}}]"#,
        ))
        .unwrap();
        em.stop(StopReason::Converged, None).unwrap();

        let evs = sink.events.lock().unwrap();
        let types: Vec<&str> = evs.iter().map(|e| e["type"].as_str().unwrap()).collect();
        assert_eq!(
            types,
            vec![
                "avp.agent_started",
                "avp.assistant_message",
                "avp.tool_invoked",
                "avp.tool_returned",
                "avp.agent_stopped",
            ]
        );

        let agent_span = evs[0]["data"]["span_id"].as_str().unwrap();
        let turn_span = evs[1]["data"]["span_id"].as_str().unwrap();
        let invoked_span = evs[2]["data"]["span_id"].as_str().unwrap();

        // Hierarchy: agent_started is root; turn under agent; tool under turn;
        // return under the invocation.
        assert_eq!(evs[0]["data"]["parent_span_id"], "0".repeat(16));
        assert_eq!(evs[1]["data"]["parent_span_id"], agent_span);
        assert_eq!(evs[2]["data"]["parent_span_id"], turn_span);
        assert_eq!(evs[3]["data"]["parent_span_id"], invoked_span);

        // tool_invoked content.
        assert_eq!(evs[2]["data"]["avp.tool.name"], "developer__shell");
        assert_eq!(evs[2]["data"]["avp.tool.call_id"], "call_1");
        assert_eq!(evs[2]["data"]["avp.tool.dispatch_target"], "local");
        assert_eq!(evs[2]["data"]["avp.tool.input"]["command"], "ls");

        // tool_returned pairs by id, carries extracted text and the step of its
        // invoking turn.
        assert_eq!(evs[3]["data"]["avp.tool.call_id"], "call_1");
        assert_eq!(evs[3]["data"]["avp.step"], 1);
        assert_eq!(evs[3]["data"]["avp.tool_result"]["content"], "a\nb");
        assert_eq!(evs[3]["data"]["avp.tool_result"]["is_error"], false);

        assert_eq!(evs[4]["data"]["avp.reason"], "converged");
    }

    #[test]
    fn mcp_tool_is_classified_mcp_server() {
        let sink = CapturingSink::default();
        let mut em = emitter(sink.clone());
        em.start(None).unwrap();
        em.on_assistant(
            &content(
                r#"[{"type":"toolRequest","id":"c","toolCall":{"status":"success",
                    "value":{"name":"avptest__echo"}},"_meta":{"goose_extension":"avptest"}}]"#,
            ),
            usage(),
            None,
        )
        .unwrap();
        let evs = sink.events.lock().unwrap();
        let invoked = evs
            .iter()
            .find(|e| e["type"] == "avp.tool_invoked")
            .unwrap();
        assert_eq!(invoked["data"]["avp.tool.dispatch_target"], "mcp_server");
    }

    #[test]
    fn error_tool_result_flags_is_error() {
        let sink = CapturingSink::default();
        let mut em = emitter(sink.clone());
        em.start(None).unwrap();
        em.on_assistant(
            &content(
                r#"[{"type":"toolRequest","id":"c","toolCall":{"status":"success",
                    "value":{"name":"developer__shell"}}}]"#,
            ),
            usage(),
            None,
        )
        .unwrap();
        em.on_tool_results(&content(
            r#"[{"type":"toolResponse","id":"c","toolResult":{"status":"error","error":"boom"}}]"#,
        ))
        .unwrap();
        let evs = sink.events.lock().unwrap();
        let ret = evs
            .iter()
            .find(|e| e["type"] == "avp.tool_returned")
            .unwrap();
        assert_eq!(ret["data"]["avp.tool_result"]["is_error"], true);
        assert_eq!(ret["data"]["avp.tool_result"]["content"], "boom");
    }

    #[test]
    fn stop_is_idempotent() {
        let sink = CapturingSink::default();
        let mut em = emitter(sink.clone());
        em.start(None).unwrap();
        em.stop(StopReason::Converged, None).unwrap();
        em.stop(StopReason::Error, None).unwrap();
        let stops = sink
            .events
            .lock()
            .unwrap()
            .iter()
            .filter(|e| e["type"] == "avp.agent_stopped")
            .count();
        assert_eq!(stops, 1);
    }

    #[test]
    fn classify_error_maps_known_messages() {
        assert_eq!(
            classify_error("429 Too Many Requests: rate limit"),
            ErrorCode::RateLimit
        );
        assert_eq!(
            classify_error("prompt exceeds the context window"),
            ErrorCode::ContextLimit
        );
        assert_eq!(
            classify_error("401 Unauthorized: invalid api key"),
            ErrorCode::AuthError
        );
        assert_eq!(
            classify_error("connection reset by peer"),
            ErrorCode::AgentCrash
        );
    }
}
