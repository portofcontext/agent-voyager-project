use super::skill_md::frontmatter_value;
use crate::{commission::Commission, descriptor::AgentDescriptor};

fn settings<'a>(
    commission: &'a Commission,
    descriptor: &AgentDescriptor,
) -> Option<&'a crate::commission::AgentSettings> {
    commission
        .agents
        .as_ref()?
        .iter()
        .find(|(key, _)| key.as_str() == descriptor.agent_name.as_str())
        .map(|(_, v)| v)
}

pub fn check_agent_entry(commission: &Commission, descriptor: &AgentDescriptor) -> Option<String> {
    (commission.agents.is_some() && settings(commission, descriptor).is_none()).then(|| {
        format!(
            "agents has no entry for '{}'",
            descriptor.agent_name.as_str()
        )
    })
}

pub fn check_agent_version(
    commission: &Commission,
    descriptor: &AgentDescriptor,
) -> Option<String> {
    let version = settings(commission, descriptor)?.version.as_ref()?;
    (version != &descriptor.agent_version).then(|| {
        format!(
            "agents.{}.version is '{}', but this agent is version '{}'",
            descriptor.agent_name.as_str(),
            version,
            descriptor.agent_version
        )
    })
}

pub fn check_enabled_items(
    commission: &Commission,
    descriptor: &AgentDescriptor,
) -> Option<String> {
    let entry = settings(commission, descriptor)?;
    let tools: Vec<_> = descriptor
        .tools
        .iter()
        .flatten()
        .filter(|t| t.mcp_server_id.is_none())
        .map(|t| t.name.as_str())
        .collect();
    let subagents: Vec<_> = descriptor
        .subagents
        .iter()
        .flatten()
        .map(|s| s.name.as_str())
        .collect();
    let skills: Vec<_> = descriptor
        .skills
        .iter()
        .flatten()
        .map(|s| s.name.as_str())
        .collect();
    let servers: Vec<_> = descriptor
        .mcp_servers
        .iter()
        .flatten()
        .map(|s| s.id.as_str())
        .collect();
    for (field, enabled, offered) in [
        ("enabled_tools", &entry.enabled_tools, tools),
        ("enabled_subagents", &entry.enabled_subagents, subagents),
        ("enabled_skills", &entry.enabled_skills, skills),
        ("enabled_mcp_servers", &entry.enabled_mcp_servers, servers),
    ] {
        let unknown: Vec<_> = enabled
            .iter()
            .flatten()
            .filter(|n| !offered.contains(&n.as_str()))
            .map(String::as_str)
            .collect();
        if !unknown.is_empty() {
            return Some(format!(
                "agents.{}.{field} names items the agent doesn't have: {}",
                descriptor.agent_name.as_str(),
                unknown.join(", ")
            ));
        }
    }
    None
}

pub fn check_skill_names(commission: &Commission, _descriptor: &AgentDescriptor) -> Option<String> {
    for skill in commission.skills.iter().flatten() {
        let found = frontmatter_value(&skill.files.skill_md, "name");
        if found.as_deref() != Some(skill.name.as_str()) {
            let found = found.map_or("has no name".into(), |n| format!("names '{n}'"));
            return Some(format!(
                "skill '{}': the frontmatter of its SKILL.md {found}",
                skill.name.as_str()
            ));
        }
    }
    None
}

pub fn check_added_items_clash(
    commission: &Commission,
    descriptor: &AgentDescriptor,
) -> Option<String> {
    for server in commission.mcp_servers.iter().flatten() {
        let id = match server {
            crate::commission::McpServer::Http(s) => s.id.as_str(),
            crate::commission::McpServer::Stdio(s) => s.id.as_str(),
        };
        if descriptor.mcp_servers.iter().flatten().any(|s| s.id == id) {
            return Some(format!(
                "MCP server '{id}' has the same id as one the agent comes with"
            ));
        }
    }
    for skill in commission.skills.iter().flatten() {
        if descriptor
            .skills
            .iter()
            .flatten()
            .any(|s| s.name == skill.name.as_str())
        {
            return Some(format!(
                "skill '{}' has the same name as one the agent comes with",
                skill.name.as_str()
            ));
        }
    }
    None
}

pub const CHECKS: [fn(&Commission, &AgentDescriptor) -> Option<String>; 5] = [
    check_agent_entry,
    check_agent_version,
    check_enabled_items,
    check_skill_names,
    check_added_items_clash,
];

pub fn check_commission(commission: &Commission, descriptor: &AgentDescriptor) -> Option<String> {
    CHECKS
        .iter()
        .find_map(|check| check(commission, descriptor))
}
