//! The Commission checks every agent runs before its first turn.
//!
//! The spec requires an agent to refuse a Commission it can't honor before any
//! model turn, with `error_occurred` + `agent_stopped(error)`:
//!
//! - `agent_versions` pins this agent at a different build
//!   (`unsupported_agent_version`);
//! - an `enabled_builtin_*` allow-list map has no entry under this agent's name
//!   (`commission_collision`);
//! - an allow-list names a tool / subagent / skill / MCP server the agent
//!   doesn't offer (`commission_collision`).
//!
//! Fill in the surfaces the agent offers in [`Offered`]; a surface left `None`
//! is not checked by name. Harness-specific refusals stay in the adapter.
//! Matches the Python `avp.preflight`.

use std::collections::HashMap;

use crate::trajectory::ErrorCode;
use crate::Commission;

/// The names the agent offers per surface; `None` skips the by-name check.
#[derive(Default, Clone, Copy)]
pub struct Offered<'a> {
    pub tools: Option<&'a [String]>,
    pub subagents: Option<&'a [String]>,
    pub skills: Option<&'a [String]>,
    pub mcp_servers: Option<&'a [String]>,
}

/// The first Commission check that fails, as `(code, message)`, or `None`.
pub fn preflight(
    commission: &Commission,
    agent_name: &str,
    agent_version: &str,
    offered: Offered<'_>,
) -> Option<(ErrorCode, String)> {
    if let Some(pin) = commission
        .agent_versions
        .as_ref()
        .and_then(|m| m.get(agent_name))
    {
        if pin != agent_version {
            return Some((
                ErrorCode::UnsupportedAgentVersion,
                format!("Commission pins {agent_name} at {pin:?}; this build is {agent_version:?}"),
            ));
        }
    }
    let lists: [(
        &str,
        Option<&HashMap<String, Vec<String>>>,
        Option<&[String]>,
    ); 4] = [
        (
            "enabled_builtin_tools",
            commission.enabled_builtin_tools.as_ref(),
            offered.tools,
        ),
        (
            "enabled_builtin_subagents",
            commission.enabled_builtin_subagents.as_ref(),
            offered.subagents,
        ),
        (
            "enabled_builtin_skills",
            commission.enabled_builtin_skills.as_ref(),
            offered.skills,
        ),
        (
            "enabled_builtin_mcp_servers",
            commission.enabled_builtin_mcp_servers.as_ref(),
            offered.mcp_servers,
        ),
    ];
    let missing: Vec<&str> = lists
        .iter()
        .filter(|(_, map, _)| map.is_some_and(|m| !m.contains_key(agent_name)))
        .map(|(field, _, _)| *field)
        .collect();
    if !missing.is_empty() {
        return Some((
            ErrorCode::CommissionCollision,
            format!("no {agent_name:?} entry in: {}", missing.join(", ")),
        ));
    }
    for (field, map, names) in lists {
        let (Some(allowed), Some(names)) = (map.and_then(|m| m.get(agent_name)), names) else {
            continue;
        };
        let unknown: Vec<&str> = allowed
            .iter()
            .filter(|n| !names.contains(n))
            .map(String::as_str)
            .collect();
        if !unknown.is_empty() {
            return Some((
                ErrorCode::CommissionCollision,
                format!(
                    "{field} names not offered by the agent: {}",
                    unknown.join(", ")
                ),
            ));
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn commission(extra: serde_json::Value) -> Commission {
        let mut base = json!({"schema_version": "0.1", "run_id": "r", "model": "x/m"});
        base.as_object_mut()
            .unwrap()
            .extend(extra.as_object().unwrap().clone());
        serde_json::from_value(base).unwrap()
    }

    fn check(extra: serde_json::Value) -> Option<ErrorCode> {
        let tools = vec!["read".to_string()];
        let offered = Offered {
            tools: Some(&tools),
            ..Default::default()
        };
        preflight(&commission(extra), "a", "1.0", offered).map(|(code, _)| code)
    }

    #[test]
    fn checks_match_python() {
        assert_eq!(check(json!({})), None);
        assert_eq!(
            check(json!({"agent_versions": {"a": "0.9"}})),
            Some(ErrorCode::UnsupportedAgentVersion)
        );
        assert_eq!(
            check(json!({"enabled_builtin_subagents": {"other": []}})),
            Some(ErrorCode::CommissionCollision)
        );
        assert_eq!(
            check(json!({"enabled_builtin_tools": {"a": ["read", "fly"]}})),
            Some(ErrorCode::CommissionCollision)
        );
        assert_eq!(check(json!({"enabled_builtin_tools": {"a": []}})), None);
        // An unchecked surface (no offered names) is not validated by name.
        assert_eq!(
            check(json!({"enabled_builtin_skills": {"a": ["anything"]}})),
            None
        );
    }
}
