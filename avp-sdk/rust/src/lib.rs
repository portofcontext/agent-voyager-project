//! AVP wire types and shared agent helpers.

pub mod agent_cli;
pub mod recorder;
pub mod utils;
mod validation;
pub mod wire;

pub const AVP_VERSION: &str = "0.1";
pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

pub mod commission {
    pub use crate::wire::{
        AgentSettings, AvpCommissionSkill as Skill, Commission,
        CommissionMcpServersItem as McpServer, EnvSecret, McpServerHttp, McpServerStdio, Model,
        ModelCredential as SecretRef, ModelRef, ProxySecret, Supervisor,
    };
}

pub mod descriptor {
    pub use crate::wire::{
        AgentDescriptor, AvpDescriptorSkill as Skill, McpServer, ModelPattern, Subagent, Tool,
    };
}

pub mod trajectory {
    pub use crate::wire::{
        AgentDescribed, AgentDescribedEvent, AgentStarted, AgentStartedEvent, AgentStopped,
        AgentStoppedEvent, AssistantMessage, AssistantMessageContentItem as ContentBlock,
        AssistantMessageEvent, Citation, CostSource, ErrorCode, ErrorOccurred, ErrorOccurredEvent,
        Event, ImageBlock, RefusalBlock, RunRequested, RunRequestedEvent, ServerToolResultBlock,
        ServerToolUseBlock, Source, StopReason, SubagentInvoked, SubagentInvokedEvent,
        SubagentReturned, SubagentReturnedEvent, SubagentUsage, TextBlock, ThinkingBlock,
        ToolInvoked, ToolInvokedEvent, ToolResultBlock, ToolResultBlockContent as ToolContent,
        ToolReturned, ToolReturnedEvent, ToolUseBlock, Usage,
    };

    /// Skip an unknown event type; reject a malformed event of a known type.
    pub fn parse_trajectory_event(value: serde_json::Value) -> crate::Result<Option<Event>> {
        let Some(kind) = value.get("type").and_then(serde_json::Value::as_str) else {
            return Err("event has no string type".into());
        };
        if crate::validation::event_name(kind).is_none() {
            return Ok(None);
        }
        Ok(Some(serde_json::from_value(value)?))
    }
}
