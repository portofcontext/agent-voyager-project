//! Turn runtime reports into one run's Trajectory.

use std::collections::HashSet;

use chrono::{DateTime, Utc};
use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::{
    Result,
    commission::{Commission, ModelRef},
    descriptor::AgentDescriptor,
    trajectory::{
        AgentStarted, ContentBlock, Event, StopReason, SubagentUsage, ToolContent,
        parse_trajectory_event,
    },
    utils::{
        preflight::check_commission,
        pricing::{self, Prices, Tokens},
    },
};

pub const ABANDONED_TEXT: &str = "The run ended while the subagent was still running.";
pub const UNRETURNED_TEXT: &str = "The run ended before the tool returned.";
pub const STOPPED_BEFORE_START_TEXT: &str = "The run stopped before agent_started.";

#[derive(Debug, thiserror::Error)]
#[error("{0}")]
pub struct RecorderError(pub String);

pub trait EventSink {
    fn write(&mut self, event: Event) -> Result<()>;
}

impl<F: FnMut(Event) -> Result<()>> EventSink for F {
    fn write(&mut self, event: Event) -> Result<()> {
        self(event)
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct UsageReport {
    pub input_tokens: u64,
    pub output_tokens: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache_read_input_tokens: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache_creation_input_tokens: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reasoning_output_tokens: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cost_usd: Option<f64>,
}

impl UsageReport {
    fn check(&self) -> Result<()> {
        if self
            .input_tokens
            .checked_sub(self.cache_read_input_tokens.unwrap_or(0))
            .and_then(|n| n.checked_sub(self.cache_creation_input_tokens.unwrap_or(0)))
            .is_none()
        {
            return Err("cache read and creation tokens exceed input_tokens".into());
        }
        if self
            .cost_usd
            .is_some_and(|cost| cost.is_nan() || cost < 0.0)
        {
            return Err("cost_usd must be non-negative".into());
        }
        Ok(())
    }
}

#[derive(Default)]
pub struct RecorderOptions {
    pub run_id: Option<String>,
    pub prices: Option<Prices>,
    pub now: Option<Box<dyn FnMut() -> DateTime<Utc>>>,
    pub new_id: Option<Box<dyn FnMut() -> String>>,
}

#[derive(Default)]
pub struct ResponseOptions {
    pub usage: Option<UsageReport>,
    pub model: Option<ModelRef>,
    pub response_model: Option<String>,
    pub finish_reasons: Option<Vec<String>>,
    pub duration_ms: Option<u64>,
    pub subagent_invocation_id: Option<String>,
    pub key: Option<String>,
    pub meta: Option<Map<String, Value>>,
}

struct Call {
    name: String,
    input: Value,
    parent: Option<String>,
    time: DateTime<Utc>,
    returned: bool,
}

struct Subagent {
    name: String,
    parent: Option<String>,
    time: DateTime<Utc>,
    reason: Option<StopReason>,
}

struct Response {
    options: ResponseOptions,
    model: ModelRef,
    opened: DateTime<Utc>,
    last: DateTime<Utc>,
    content: Vec<ContentBlock>,
    call_ids: HashSet<String>,
    waiting: Vec<Event>,
    tool_returned: bool,
}

pub struct Recorder<S: EventSink> {
    sink: S,
    prices: Option<Prices>,
    now: Box<dyn FnMut() -> DateTime<Utc>>,
    new_id: Box<dyn FnMut() -> String>,
    pub run_id: String,
    pub ended: bool,
    begun: bool,
    started: Option<AgentStarted>,
    response: Option<Response>,
    calls: IndexMap<String, Call>,
    subagents: IndexMap<String, Subagent>,
    reported_responses: HashSet<String>,
}

impl<S: EventSink> Recorder<S> {
    pub fn new(sink: S) -> Self {
        Self::with_options(sink, RecorderOptions::default())
    }

    pub fn with_options(sink: S, options: RecorderOptions) -> Self {
        let mut new_id = options
            .new_id
            .unwrap_or_else(|| Box::new(|| uuid::Uuid::new_v4().to_string()));
        let run_id = options
            .run_id
            .filter(|id| !id.is_empty())
            .unwrap_or_else(&mut new_id);
        Self {
            sink,
            prices: options.prices,
            now: options.now.unwrap_or_else(|| Box::new(Utc::now)),
            new_id,
            run_id,
            ended: false,
            begun: false,
            started: None,
            response: None,
            calls: IndexMap::new(),
            subagents: IndexMap::new(),
            reported_responses: HashSet::new(),
        }
    }

    fn check(&self, report: &str, started: bool) -> Result<()> {
        if self.ended {
            return Err(RecorderError(format!("{report}: the run has ended")).into());
        }
        if started && self.started.is_none() {
            return Err(RecorderError(format!("{report}: called before start")).into());
        }
        Ok(())
    }

    fn event(
        &mut self,
        kind: &str,
        data: Value,
        time: Option<DateTime<Utc>>,
        meta: Option<Map<String, Value>>,
    ) -> Result<Event> {
        let event = json!({ "avp_version": crate::AVP_VERSION, "id": (self.new_id)(),
            "time": time.unwrap_or_else(&mut self.now), "run_id": self.run_id,
            "type": kind, "data": data, "meta": meta });
        parse_trajectory_event(event)?.ok_or_else(|| "Recorder produced an unknown event".into())
    }

    fn write(&mut self, event: Event) -> Result<()> {
        if let Some(response) = &mut self.response {
            response.waiting.push(event);
            Ok(())
        } else {
            self.sink.write(event)
        }
    }

    pub fn begin(
        &mut self,
        received: Value,
        descriptor: AgentDescriptor,
    ) -> Result<Option<Commission>> {
        self.check("begin", false)?;
        if self.begun || self.started.is_some() {
            return Err(RecorderError("begin: called twice, or after start".into()).into());
        }
        self.begun = true;
        let mut refusal = None;
        let commission: Option<Commission> = if received.is_null() {
            None
        } else {
            match serde_json::from_value(received.clone()) {
                Ok(commission) => Some(commission),
                Err(error) => {
                    refusal = Some(format!("the Commission doesn't match the spec: {error}"));
                    None
                }
            }
        };
        if let Some(run_id) = received.get("run_id").and_then(Value::as_str) {
            self.run_id = run_id.into();
        }
        let requested = self.event("run_requested", json!({"commission": received}), None, None)?;
        self.sink.write(requested)?;
        let described = self.event(
            "agent_described",
            json!({"descriptor": descriptor}),
            None,
            None,
        )?;
        self.sink.write(described)?;
        if let Some(commission) = &commission {
            refusal = check_commission(commission, &descriptor);
        }
        if let Some(refusal) = refusal {
            self.error("invalid_commission", &refusal, None)?;
            return Ok(None);
        }
        Ok(commission)
    }

    pub fn start(&mut self, started: AgentStarted, meta: Option<Map<String, Value>>) -> Result<()> {
        self.check("start", false)?;
        if self.started.is_some() {
            return Err(RecorderError("start: called twice".into()).into());
        }
        let event = self.event("agent_started", serde_json::to_value(&started)?, None, meta)?;
        self.started = Some(started);
        self.sink.write(event)
    }

    pub fn error(&mut self, code: &str, message: &str, parent: Option<&str>) -> Result<()> {
        self.check("error", false)?;
        let event = self.event(
            "error_occurred",
            json!({"error_code": code,
            "error_message": message, "subagent_invocation_id": parent}),
            None,
            None,
        )?;
        if self.started.is_none() {
            self.ended = true;
            self.sink.write(event)
        } else {
            self.write(event)
        }
    }

    pub fn stop(&mut self, mut reason: StopReason, output: Value) -> Result<()> {
        if self.ended {
            return Ok(());
        }
        if self.started.is_none() {
            return self.error("agent_crash", STOPPED_BEFORE_START_TEXT, None);
        }
        self.close_response()?;
        let running: Vec<_> = self
            .subagents
            .iter()
            .filter(|(_, s)| s.reason.is_none())
            .map(|(id, _)| id.clone())
            .collect();
        for id in &running {
            self.subagent_returned(id, ABANDONED_TEXT, StopReason::Abandoned, None)?;
        }
        let calls: Vec<_> = self
            .calls
            .iter()
            .filter(|(_, c)| !c.returned)
            .map(|(id, _)| id.clone())
            .collect();
        for id in calls {
            self.tool_returned(
                &id,
                serde_json::from_value(json!(UNRETURNED_TEXT))?,
                Some(true),
                None,
            )?;
        }
        if !running.is_empty() && reason == StopReason::Converged {
            reason = StopReason::Abandoned;
        }
        let event = self.event(
            "agent_stopped",
            json!({"reason": reason, "output": output}),
            None,
            None,
        )?;
        self.ended = true;
        self.sink.write(event)
    }

    pub fn response(
        &mut self,
        content: Vec<ContentBlock>,
        mut options: ResponseOptions,
    ) -> Result<()> {
        self.check("response", true)?;
        if let Some(usage) = &options.usage {
            usage.check()?;
        }
        let calls: Vec<_> = content
            .iter()
            .filter_map(|block| {
                if let ContentBlock::ToolUseBlock(call) = block {
                    Some(call.clone())
                } else {
                    None
                }
            })
            .collect();
        let mut ids = HashSet::new();
        for call in &calls {
            if self.calls.contains_key(&call.id) || !ids.insert(call.id.clone()) {
                return Err(RecorderError(format!(
                    "response: tool_use id '{}' was already used",
                    call.id
                ))
                .into());
            }
        }
        if self.response.as_ref().is_some_and(|open| {
            options.key.is_none()
                || options.key != open.options.key
                || open.tool_returned
                || options.subagent_invocation_id != open.options.subagent_invocation_id
        }) {
            self.close_response()?;
        }
        let now = (self.now)();
        if self.response.is_none() {
            let model = options
                .model
                .take()
                .unwrap_or_else(|| self.started.as_ref().unwrap().model.clone());
            self.response = Some(Response {
                options: ResponseOptions {
                    key: options.key.clone(),
                    subagent_invocation_id: options.subagent_invocation_id.clone(),
                    ..Default::default()
                },
                model,
                opened: now,
                last: now,
                content: Vec::new(),
                call_ids: HashSet::new(),
                waiting: Vec::new(),
                tool_returned: false,
            });
        }
        let response = self.response.as_mut().unwrap();
        response.last = now;
        response.content.extend(content);
        if options.usage.is_some() {
            response.options.usage = options.usage;
        }
        if response.options.response_model.is_none() {
            response.options.response_model = options.response_model;
        }
        if options.finish_reasons.is_some() {
            response.options.finish_reasons = options.finish_reasons;
        }
        if options.duration_ms.is_some() {
            response.options.duration_ms = options.duration_ms;
        }
        if let Some(meta) = options.meta.filter(|meta| !meta.is_empty()) {
            response
                .options
                .meta
                .get_or_insert_with(Map::new)
                .extend(meta);
        }
        if let Some(parent) = &options.subagent_invocation_id {
            self.reported_responses.insert(parent.clone());
        }
        for call in calls {
            let server = self
                .started
                .as_ref()
                .unwrap()
                .tools
                .iter()
                .flatten()
                .rev()
                .find(|t| t.name == call.name)
                .and_then(|t| t.mcp_server_id.clone());
            let input = serde_json::to_value(&call.input)?;
            self.calls.insert(
                call.id.clone(),
                Call {
                    name: call.name.clone(),
                    input: input.clone(),
                    parent: options.subagent_invocation_id.clone(),
                    time: now,
                    returned: false,
                },
            );
            self.response
                .as_mut()
                .unwrap()
                .call_ids
                .insert(call.id.clone());
            let event = self.event(
                "tool_invoked",
                json!({"tool_call_id": call.id, "tool_name": call.name,
                "tool_input": input, "mcp_server_id": server,
                "subagent_invocation_id": options.subagent_invocation_id}),
                None,
                None,
            )?;
            self.response.as_mut().unwrap().waiting.push(event);
        }
        if options.key.is_none() {
            self.close_response()?;
        }
        Ok(())
    }

    pub fn usage(&mut self, usage: UsageReport, key: Option<&str>) -> Result<()> {
        self.check("usage", true)?;
        usage.check()?;
        let Some(response) = self
            .response
            .as_mut()
            .filter(|r| key.is_none() || key == r.options.key.as_deref())
        else {
            let key = key.map_or("None".into(), |k| format!("'{k}'"));
            return Err(RecorderError(format!("usage: no open response with key {key}")).into());
        };
        response.options.usage = Some(usage);
        Ok(())
    }

    pub fn close_response(&mut self) -> Result<()> {
        let Some(response) = self.response.take() else {
            return Ok(());
        };
        if response
            .content
            .iter()
            .any(|block| !matches!(block, ContentBlock::TextBlock(t) if t.text.is_empty()))
        {
            let usage = if let Some(report) = &response.options.usage {
                if self.prices.is_none() && report.cost_usd.is_none() {
                    self.prices = Some(pricing::load_prices(None, None)?);
                }
                let empty = self.prices.is_none().then(|| Prices {
                    source: "https://models.dev/api.json".into(),
                    fetched: (self.now)(),
                    models: Default::default(),
                });
                let (cost, source) = pricing::compute_cost(
                    self.prices.as_ref().or(empty.as_ref()).unwrap(),
                    &response.model,
                    &Tokens {
                        input_tokens: report.input_tokens,
                        output_tokens: report.output_tokens,
                        cache_read_input_tokens: report.cache_read_input_tokens.unwrap_or(0),
                        cache_creation_input_tokens: report
                            .cache_creation_input_tokens
                            .unwrap_or(0),
                    },
                    response.options.response_model.as_deref(),
                    report.cost_usd,
                )?;
                let mut usage = serde_json::to_value(report)?;
                usage["cost_usd"] = json!(cost);
                usage["cost_source"] = serde_json::to_value(source)?;
                usage
            } else {
                json!({"input_tokens": 0, "output_tokens": 0, "cost_usd": 0, "cost_source": "unknown"})
            };
            let event = self.event("assistant_message", json!({"content": response.content,
                "model": response.model, "response_model": response.options.response_model,
                "finish_reasons": response.options.finish_reasons,
                "duration_ms": response.options.duration_ms.unwrap_or_else(|| ms(response.opened, response.last)),
                "usage": usage, "subagent_invocation_id": response.options.subagent_invocation_id}),
                Some(response.last), response.options.meta)?;
            self.sink.write(event)?;
        }
        for event in response.waiting {
            self.sink.write(event)?;
        }
        Ok(())
    }

    pub fn tool_returned(
        &mut self,
        id: &str,
        content: ToolContent,
        mut is_error: Option<bool>,
        structured: Option<Map<String, Value>>,
    ) -> Result<()> {
        self.check("tool_returned", true)?;
        let Some(call) = self.calls.get_mut(id).filter(|c| !c.returned) else {
            let state = if self.calls.contains_key(id) {
                "already returned"
            } else {
                "unknown"
            };
            return Err(
                RecorderError(format!("tool_returned: tool call '{id}' is {state}")).into(),
            );
        };
        call.returned = true;
        if let Some(reason) = self.subagents.get(id).and_then(|s| s.reason.as_ref()) {
            is_error = Some(*reason != StopReason::Converged);
        }
        if let Some(response) = self.response.as_mut().filter(|r| r.call_ids.contains(id)) {
            response.tool_returned = true;
        }
        let data = json!({"tool_call_id": id, "tool_name": call.name, "duration_ms": ms(call.time, (self.now)()),
            "tool_result": {"type": "tool_result", "tool_use_id": id, "content": content,
                "structured_content": structured, "is_error": is_error}, "subagent_invocation_id": call.parent});
        let event = self.event("tool_returned", data, None, None)?;
        self.write(event)
    }

    pub fn subagent_invoked(
        &mut self,
        id: &str,
        name: &str,
        input: Option<Map<String, Value>>,
        parent: Option<String>,
    ) -> Result<()> {
        self.check("subagent_invoked", true)?;
        if self.subagents.contains_key(id) {
            return Err(RecorderError(format!("subagent_invoked: '{id}' was already used")).into());
        }
        let call = self.calls.get(id);
        let input = input
            .map(Value::Object)
            .or_else(|| call.map(|c| c.input.clone()))
            .unwrap_or(json!({}));
        let parent = if let Some(call) = call {
            parent
                .filter(|p| !p.is_empty())
                .or_else(|| call.parent.clone())
        } else {
            parent
        };
        self.subagents.insert(
            id.into(),
            Subagent {
                name: name.into(),
                parent: parent.clone(),
                time: (self.now)(),
                reason: None,
            },
        );
        let event = self.event(
            "subagent_invoked",
            json!({"subagent_name": name, "invocation_id": id,
            "subagent_input": input, "subagent_invocation_id": parent}),
            None,
            None,
        )?;
        self.write(event)
    }

    pub fn subagent_returned(
        &mut self,
        id: &str,
        text: &str,
        reason: StopReason,
        mut usage: Option<SubagentUsage>,
    ) -> Result<()> {
        self.check("subagent_returned", true)?;
        let Some(subagent) = self.subagents.get_mut(id).filter(|s| s.reason.is_none()) else {
            let state = if self.subagents.contains_key(id) {
                "already returned"
            } else {
                "unknown"
            };
            return Err(
                RecorderError(format!("subagent_returned: subagent '{id}' is {state}")).into(),
            );
        };
        subagent.reason = Some(reason);
        if self.reported_responses.contains(id) {
            usage = None;
        }
        let data = json!({"subagent_name": subagent.name, "invocation_id": id,
            "subagent_invocation_id": subagent.parent, "duration_ms": ms(subagent.time, (self.now)()),
            "subagent_reason": reason, "subagent_result_text": text, "subagent_usage": usage});
        let event = self.event("subagent_returned", data, None, None)?;
        self.write(event)
    }
}

fn ms(start: DateTime<Utc>, end: DateTime<Utc>) -> u64 {
    ((end - start).num_microseconds().unwrap_or(0) as f64 / 1000.0)
        .round_ties_even()
        .max(0.0) as u64
}
