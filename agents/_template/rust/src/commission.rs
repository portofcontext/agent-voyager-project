//! Commission -> the harness's own configuration. REPLACE the body.
//!
//! Map every Commission field the harness can honor (model, system prompt,
//! the `enabled_builtin_*` allow-lists under this agent's key, inline
//! `mcp_servers` and `skills`) onto the harness's config before the run.

use avp::trajectory::ErrorCode;
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

/// Commission checks the spec requires before any model turn: a version pin
/// for a different build, an allow-list map without this agent's key, or an
/// allow-listed tool the agent doesn't offer.
pub fn fail_fast(commission: &Commission, agent_version: &str) -> Option<(ErrorCode, String)> {
    if let Some(pin) = commission
        .agent_versions
        .as_ref()
        .and_then(|m| m.get(AGENT_NAME))
    {
        if pin != agent_version {
            return Some((
                ErrorCode::UnsupportedAgentVersion,
                format!("Commission pins {AGENT_NAME} at {pin:?}"),
            ));
        }
    }
    let missing: Vec<&str> = [
        (
            "enabled_builtin_tools",
            commission.enabled_builtin_tools.as_ref(),
        ),
        (
            "enabled_builtin_subagents",
            commission.enabled_builtin_subagents.as_ref(),
        ),
        (
            "enabled_builtin_skills",
            commission.enabled_builtin_skills.as_ref(),
        ),
        (
            "enabled_builtin_mcp_servers",
            commission.enabled_builtin_mcp_servers.as_ref(),
        ),
    ]
    .into_iter()
    .filter_map(|(field, m)| {
        m.is_some_and(|m| !m.contains_key(AGENT_NAME))
            .then_some(field)
    })
    .collect();
    if !missing.is_empty() {
        return Some((
            ErrorCode::CommissionCollision,
            format!("no {AGENT_NAME:?} entry in: {}", missing.join(", ")),
        ));
    }
    let unknown: Vec<&String> = commission
        .enabled_builtin_tools
        .as_ref()
        .and_then(|m| m.get(AGENT_NAME))
        .into_iter()
        .flatten()
        .filter(|t| !BUILTIN_TOOLS.contains(&t.as_str()))
        .collect();
    if !unknown.is_empty() {
        let names: Vec<&str> = unknown.iter().map(|s| s.as_str()).collect();
        return Some((
            ErrorCode::CommissionCollision,
            format!("tools not offered: {}", names.join(", ")),
        ));
    }
    None
}
