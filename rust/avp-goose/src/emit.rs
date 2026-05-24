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

use avp::ids::{new_span_id, new_trace_id, ZERO_SPAN_ID};
use avp::pricing::PriceTable;
use avp::sink::Sink;
use avp::trajectory::{ErrorCode, StopReason, Usage};

use crate::events;
use crate::runstate::RunState;
use crate::translate::{self, GooseContent};

/// An in-flight tool invocation awaiting its result.
/// Goose's `summon` platform extension. It exposes two tools: `delegate` (run a
/// subagent recipe) and `load` (pull content into context). Only `delegate` is a
/// subagent invocation; `load` is a plain tool call.
const SUMMON_EXTENSION: &str = "summon";
const DELEGATE_TOOL: &str = "delegate";

/// The frame a subagent invocation opens. The same span closes it on return:
/// the spec pairs `subagent_invoked` / `subagent_returned` by a shared frame
/// span (unlike tool events, where the return is a child of the invocation).
struct SubagentFrame {
    /// `subagent_invoked` span; reused as the `subagent_returned` span_id.
    span: String,
    /// Parent of the frame (the turn span); also the `subagent_returned` parent.
    parent: String,
    /// The delegated subagent's name (the `delegate` call's `source` arg), not
    /// the tool name. Carried so `subagent_returned` reports the same name.
    name: String,
}

struct PendingTool {
    step: u64,
    /// `tool_invoked` span; the matching `tool_returned` parents to it.
    tool_span: String,
    /// Present when the call also spawned a subagent (a `summon` call). Such a
    /// call fires BOTH tool_* and subagent_* events (spec: a subagent started
    /// via a tool call surfaces on both axes).
    subagent: Option<SubagentFrame>,
    name: String,
    started_at: Instant,
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
        // MCP servers are no longer announced via events: their identity and
        // dial status ride on the descriptor's `mcp_servers[]`, and each
        // MCP-surfaced tool carries `avp.mcp_server_id` in the descriptor's
        // `tools[]` (built in `runner::build_descriptor`).
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
                // Every tool call surfaces a tool_invoked.
                let tool_span = new_span_id();
                let dispatch =
                    translate::dispatch_target(call.extension.as_deref(), &self.mcp_servers);
                self.state.buffer_event(events::tool_invoked(
                    &self.state.run_id,
                    &self.state.trace_id,
                    &tool_span,
                    &turn_span,
                    step,
                    &call.id,
                    &call.name,
                    call.input.clone(),
                    Some(dispatch),
                ));
                // A `summon`/`delegate` call additionally opens a subagent frame,
                // so the delegation surfaces on the subagent axis as well. The
                // subagent's name is the delegated recipe (`source` arg), not the
                // tool name. `load` (the other summon tool) is not a subagent.
                let is_delegate =
                    call.extension.as_deref() == Some(SUMMON_EXTENSION) && call.name == DELEGATE_TOOL;
                let subagent = if is_delegate {
                    let subagent_name = call
                        .input
                        .get("source")
                        .and_then(serde_json::Value::as_str)
                        .unwrap_or(&call.name)
                        .to_string();
                    let frame_span = new_span_id();
                    self.state.buffer_event(events::subagent_invoked(
                        &self.state.run_id,
                        &self.state.trace_id,
                        &frame_span,
                        &turn_span,
                        step,
                        &call.id,
                        &subagent_name,
                        call.input.clone(),
                    ));
                    Some(SubagentFrame {
                        span: frame_span,
                        parent: turn_span.clone(),
                        name: subagent_name,
                    })
                } else {
                    None
                };
                self.pending.insert(
                    call.id.clone(),
                    PendingTool {
                        step,
                        tool_span,
                        subagent,
                        name: call.name,
                        started_at: Instant::now(),
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
            // Every tool call closes with a tool_returned (parented to its
            // tool_invoked span), carrying the is_error discriminator.
            let block = events::tool_result_block(&ret.id, &ret.output, ret.is_error);
            self.state.emit(&events::tool_returned(
                &self.state.run_id,
                &self.state.trace_id,
                &new_span_id(),
                &pending.tool_span,
                pending.step,
                &ret.id,
                &pending.name,
                duration_ms,
                block,
            ))?;
            // A summon call additionally closes its subagent frame. The
            // subagent_returned reuses the frame span and mirrors the tool's
            // error via `reason = error` (the error string rides on result.text).
            if let Some(frame) = pending.subagent {
                let reason =
                    if ret.is_error { StopReason::Error } else { StopReason::Converged };
                self.state.emit(&events::subagent_returned(
                    &self.state.run_id,
                    &self.state.trace_id,
                    &frame.span,
                    &frame.parent,
                    pending.step,
                    &ret.id,
                    &frame.name,
                    duration_ms,
                    &ret.output,
                    reason,
                ))?;
            }
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
