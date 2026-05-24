//! Per-run state and turn buffering.
//!
//! An assistant turn accumulates its content blocks and the events it spawns
//! (tool invocations, returns, subagent frames); `drain` closes the turn by
//! emitting a single `assistant_message` (with computed cost) followed by those
//! buffered events in arrival order. This preserves the AVP ordering invariant:
//! the model's message lands before the tool activity it triggered.
//!
//! Goose yields a complete `Message` per assistant turn (not streamed chunks),
//! so a turn maps to one `AgentEvent::Message`. The emitter (separate layer)
//! decides when to open a turn, feeds content/usage/events here, and calls
//! `drain` at the turn boundary.

use std::time::Instant;

use avp::ids::new_span_id;
use avp::pricing::{compute_cost, CostSource, PriceTable};
use avp::sink::Sink;
use avp::trajectory::{AvpContentItem, Usage};
use avp::Event;

use crate::events;

fn zero_usage() -> Usage {
    Usage {
        input_tokens: 0,
        output_tokens: 0,
        cache_read_input_tokens: None,
        cache_creation_input_tokens: None,
        reasoning_output_tokens: None,
    }
}

/// Buffered state for one open assistant turn.
struct Turn {
    step: u64,
    span_id: String,
    started_at: Instant,
    content: Vec<AvpContentItem>,
    usage: Usage,
    response_model: Option<String>,
    /// Events spawned during the turn (tool_invoked / tool_returned /
    /// subagent_*), flushed after the turn's `assistant_message`.
    emissions: Vec<Event>,
}

/// Flat per-run state. One instance per agent run.
pub struct RunState<S: Sink> {
    /// Supervisor-issued run id; CloudEvents `subject` on every event.
    pub run_id: String,
    /// OTel trace id stamped on every event's `data`.
    pub trace_id: String,
    /// Root agent span; parent of every turn / tool / subagent frame.
    pub agent_span_id: String,
    /// Provider name for `assistant_message` (e.g. "anthropic"); `None` if unknown.
    pub provider: Option<String>,
    prices: PriceTable,
    /// 1-based turn counter.
    step: u64,
    turn: Option<Turn>,
    sink: S,
}

impl<S: Sink> RunState<S> {
    pub fn new(
        sink: S,
        run_id: impl Into<String>,
        trace_id: impl Into<String>,
        agent_span_id: impl Into<String>,
        provider: Option<String>,
        prices: PriceTable,
    ) -> Self {
        Self {
            run_id: run_id.into(),
            trace_id: trace_id.into(),
            agent_span_id: agent_span_id.into(),
            provider,
            prices,
            step: 0,
            turn: None,
            sink,
        }
    }

    /// The open turn, opening a fresh one (next step, new span) on first use.
    fn turn_mut(&mut self) -> &mut Turn {
        if self.turn.is_none() {
            self.step += 1;
            self.turn = Some(Turn {
                step: self.step,
                span_id: new_span_id(),
                started_at: Instant::now(),
                content: Vec::new(),
                usage: zero_usage(),
                response_model: None,
                emissions: Vec::new(),
            });
        }
        self.turn.as_mut().expect("just opened")
    }

    /// Open (or reuse) the current turn, returning its `(step, span_id)`. The
    /// emitter uses the span as the `parent_span_id` for the turn's tool /
    /// subagent events.
    pub fn open_turn(&mut self) -> (u64, String) {
        let turn = self.turn_mut();
        (turn.step, turn.span_id.clone())
    }

    /// Emit an event straight through the sink, bypassing the turn buffer. For
    /// lifecycle events and for tool returns that arrive after their turn has
    /// already drained.
    pub fn emit(&self, event: &Event) -> std::io::Result<()> {
        self.sink.emit(event)
    }

    /// Append an assistant content block to the open turn.
    pub fn push_content(&mut self, block: AvpContentItem) {
        self.turn_mut().content.push(block);
    }

    /// Set the open turn's usage and response model (last write wins).
    pub fn set_usage(&mut self, usage: Usage, response_model: Option<String>) {
        let turn = self.turn_mut();
        turn.usage = usage;
        turn.response_model = response_model;
    }

    /// Buffer an event spawned during the turn; flushed after the turn's
    /// `assistant_message` on `drain`.
    pub fn buffer_event(&mut self, event: Event) {
        self.turn_mut().emissions.push(event);
    }

    /// Close the open turn: emit one `assistant_message`, then every buffered
    /// event in arrival order. No-op when no turn is open.
    pub fn drain(&mut self) -> std::io::Result<()> {
        let Some(turn) = self.turn.take() else {
            return Ok(());
        };
        let duration_ms = turn.started_at.elapsed().as_millis() as u64;
        let model = turn.response_model.unwrap_or_default();
        // A turn with no observed usage reports `unknown` rather than a
        // misleading `computed $0` (e.g. an intermediate turn whose tokens
        // Goose has not yet flushed to the session — see TECH_DEBT).
        let (cost_usd, cost_source) =
            if turn.usage.input_tokens == 0 && turn.usage.output_tokens == 0 {
                (0.0, CostSource::Unknown)
            } else {
                compute_cost(
                    &model,
                    turn.usage.input_tokens,
                    turn.usage.output_tokens,
                    turn.usage.cache_read_input_tokens.unwrap_or(0),
                    turn.usage.cache_creation_input_tokens.unwrap_or(0),
                    &self.prices,
                )
            };
        let message = events::assistant_message(
            &self.run_id,
            &self.trace_id,
            &turn.span_id,
            &self.agent_span_id,
            turn.step,
            duration_ms,
            turn.content,
            turn.usage,
            cost_usd,
            cost_source,
            self.provider.as_deref(),
            (!model.is_empty()).then_some(model.as_str()),
        );
        self.sink.emit(&message)?;
        for event in turn.emissions {
            self.sink.emit(&event)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testkit::CapturingSink;
    use avp::pricing::load_default_prices;
    use avp::trajectory::{AvpContentItem, TextBlock};

    fn text(s: &str) -> AvpContentItem {
        AvpContentItem::TextBlock(TextBlock {
            text: s.to_string(),
            citations: None,
            type_: "text".to_string(),
        })
    }

    fn usage(input: u64, output: u64, cache_read: u64, cache_write: u64) -> Usage {
        Usage {
            input_tokens: input,
            output_tokens: output,
            cache_read_input_tokens: Some(cache_read),
            cache_creation_input_tokens: Some(cache_write),
            reasoning_output_tokens: None,
        }
    }

    fn run(sink: CapturingSink) -> RunState<CapturingSink> {
        RunState::new(
            sink,
            "r1",
            "0".repeat(32),
            "1".repeat(16),
            Some("anthropic".to_string()),
            load_default_prices(),
        )
    }

    #[test]
    fn drain_emits_assistant_message_then_buffered_events_in_order() {
        let sink = CapturingSink::default();
        let mut rs = run(sink.clone());

        rs.push_content(text("hello"));
        rs.set_usage(
            usage(1000, 500, 200, 100),
            Some("claude-opus-4-7".to_string()),
        );
        // A buffered tool-ish event (any event; we assert ordering, not shape).
        let buffered: Event = serde_json::from_str(
            r#"{"specversion":"1.0","id":"x","time":"2026-01-01T00:00:00Z","subject":"r1",
                "type":"avp.agent_stopped","source":"avp://agent",
                "data":{"trace_id":"00000000000000000000000000000000",
                "span_id":"2222222222222222","parent_span_id":"0000000000000000",
                "avp.reason":"converged"}}"#,
        )
        .unwrap();
        rs.buffer_event(buffered);

        rs.drain().unwrap();

        let evs = sink.events.lock().unwrap();
        assert_eq!(evs.len(), 2, "assistant_message + 1 buffered event");
        // Assistant message comes first.
        assert_eq!(evs[0]["type"], "avp.assistant_message");
        assert_eq!(evs[0]["data"]["avp.step"], 1);
        assert_eq!(evs[0]["data"]["avp.content"][0]["text"], "hello");
        assert_eq!(evs[0]["data"]["avp.cost.source"], "computed");
        // fresh=700 -> 700*5 + 200*0.5 + 100*6.25 + 500*25 = 16725 (per 1e6).
        let cost = evs[0]["data"]["avp.cost_usd"].as_f64().unwrap();
        assert!((cost - 0.016725).abs() < 1e-9, "got {cost}");
        assert_eq!(evs[0]["data"]["avp.response.model"], "claude-opus-4-7");
        // Buffered event flushed after.
        assert_eq!(evs[1]["type"], "avp.agent_stopped");
    }

    #[test]
    fn drain_clears_turn_and_increments_step() {
        let sink = CapturingSink::default();
        let mut rs = run(sink.clone());

        rs.push_content(text("one"));
        rs.set_usage(usage(10, 5, 0, 0), Some("claude-opus-4-7".to_string()));
        rs.drain().unwrap();

        // Second drain with no open turn is a no-op.
        rs.drain().unwrap();
        assert_eq!(sink.events.lock().unwrap().len(), 1);

        // Next turn gets step 2 and a distinct span.
        rs.push_content(text("two"));
        rs.drain().unwrap();
        let evs = sink.events.lock().unwrap();
        assert_eq!(evs.len(), 2);
        assert_eq!(evs[1]["data"]["avp.step"], 2);
        assert_ne!(evs[0]["data"]["span_id"], evs[1]["data"]["span_id"]);
        // Turn span sits under the agent span.
        assert_eq!(evs[1]["data"]["parent_span_id"], "1".repeat(16));
    }

    #[test]
    fn unknown_model_costs_zero_unknown() {
        let sink = CapturingSink::default();
        let mut rs = run(sink.clone());
        rs.push_content(text("x"));
        rs.set_usage(usage(100, 50, 0, 0), Some("mystery/model".to_string()));
        rs.drain().unwrap();
        let evs = sink.events.lock().unwrap();
        assert_eq!(evs[0]["data"]["avp.cost_usd"], 0.0);
        assert_eq!(evs[0]["data"]["avp.cost.source"], "unknown");
    }
}
