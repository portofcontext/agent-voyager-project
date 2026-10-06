//! Commission -> the harness's own configuration. REPLACE the body.
//!
//! Map every Commission field the harness can honor (model, system prompt,
//! the `enabled_builtin_*` allow-lists under this agent's key, inline
//! `mcp_servers` and `skills`) onto the harness's config before the run.

use avp::Commission;

pub const AGENT_NAME: &str = "avp-agent-template";
pub const BUILTIN_TOOLS: &[&str] = &["echo"];

pub struct HarnessConfig {
    pub model: String,
    pub prompt: String,
    pub system_prompt: Option<String>,
    pub tools: Vec<String>,
}

pub fn from_commission(commission: &Commission) -> HarnessConfig {
    let allow = commission
        .enabled_builtin_tools
        .as_ref()
        .and_then(|m| m.get(AGENT_NAME));
    HarnessConfig {
        model: commission.model.to_string(),
        prompt: commission.prompt.clone().unwrap_or_default(),
        system_prompt: commission.system_prompt.clone(),
        tools: BUILTIN_TOOLS
            .iter()
            .filter(|t| allow.is_none_or(|a| a.iter().any(|n| n == *t)))
            .map(|t| t.to_string())
            .collect(),
    }
}
