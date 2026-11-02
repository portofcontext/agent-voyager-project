use serde::Serialize;
use serde_json::{Value, json};

use super::skill_md::frontmatter_value;
use crate::{commission::Commission, descriptor::AgentDescriptor, trajectory::AgentStarted};

#[derive(Debug, Serialize)]
pub struct TurnedOff {
    pub tools: Vec<String>,
    pub subagents: Vec<String>,
    pub skills: Vec<String>,
    pub mcp_servers: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct RunPlan {
    pub started: AgentStarted,
    pub turned_off: TurnedOff,
}

pub fn plan_run(commission: &Commission, descriptor: &AgentDescriptor) -> RunPlan {
    let settings = commission.agents.as_ref().and_then(|agents| {
        agents
            .iter()
            .find(|(key, _)| key.as_str() == descriptor.agent_name.as_str())
            .map(|(_, v)| v)
    });
    let allowed = |field: &str, name: &str| -> bool {
        let list = settings.and_then(|s| match field {
            "tools" => s.enabled_tools.as_ref(),
            "mcp_servers" => s.enabled_mcp_servers.as_ref(),
            "skills" => s.enabled_skills.as_ref(),
            "subagents" => s.enabled_subagents.as_ref(),
            _ => unreachable!(),
        });
        list.is_none_or(|list| list.iter().any(|n| n == name))
    };
    let tool_on = |tool: &crate::descriptor::Tool| {
        tool.mcp_server_id.as_ref().map_or_else(
            || allowed("tools", &tool.name),
            |id| allowed("mcp_servers", id),
        )
    };
    let tools: Vec<_> = descriptor
        .tools
        .iter()
        .flatten()
        .filter(|t| tool_on(t))
        .cloned()
        .collect();
    let mut servers: Vec<_> = descriptor
        .mcp_servers
        .iter()
        .flatten()
        .filter(|s| allowed("mcp_servers", &s.id))
        .cloned()
        .collect();
    for server in commission.mcp_servers.iter().flatten() {
        let (id, name, description) = match server {
            crate::commission::McpServer::Http(s) => (s.id.as_str(), &s.name, &s.description),
            crate::commission::McpServer::Stdio(s) => (s.id.as_str(), &s.name, &s.description),
        };
        servers.push(crate::descriptor::McpServer {
            id: id.into(),
            name: name.clone(),
            description: description.clone(),
            status: None,
        });
    }
    let mut skills: Vec<_> = descriptor
        .skills
        .iter()
        .flatten()
        .filter(|s| allowed("skills", &s.name))
        .cloned()
        .collect();
    for skill in commission.skills.iter().flatten() {
        skills.push(crate::descriptor::Skill {
            name: skill.name.to_string(),
            description: frontmatter_value(&skill.files.skill_md, "description")
                .unwrap_or_default(),
            source: None,
            extra: Default::default(),
        });
    }
    let subagents: Vec<_> = descriptor
        .subagents
        .iter()
        .flatten()
        .filter(|s| allowed("subagents", &s.name))
        .cloned()
        .collect();
    let mut model = serde_json::to_value(&commission.model).unwrap();
    model.as_object_mut().unwrap().remove("credential");
    let started = serde_json::from_value(json!({
        "prompt": commission.prompt,
        "system_prompt": commission.system_prompt.as_ref().filter(|s| !s.is_empty()).or(descriptor.system_prompt.as_ref()),
        "model": model, "tools": nonempty(tools), "mcp_servers": nonempty(servers),
        "skills": nonempty(skills), "subagents": nonempty(subagents),
    })).unwrap();
    RunPlan {
        started,
        turned_off: TurnedOff {
            tools: descriptor
                .tools
                .iter()
                .flatten()
                .filter(|t| !tool_on(t))
                .map(|t| t.name.clone())
                .collect(),
            subagents: descriptor
                .subagents
                .iter()
                .flatten()
                .filter(|s| !allowed("subagents", &s.name))
                .map(|s| s.name.clone())
                .collect(),
            skills: descriptor
                .skills
                .iter()
                .flatten()
                .filter(|s| !allowed("skills", &s.name))
                .map(|s| s.name.clone())
                .collect(),
            mcp_servers: descriptor
                .mcp_servers
                .iter()
                .flatten()
                .filter(|s| !allowed("mcp_servers", &s.id))
                .map(|s| s.id.clone())
                .collect(),
        },
    }
}

fn nonempty<T: Serialize>(items: Vec<T>) -> Option<Value> {
    (!items.is_empty()).then(|| serde_json::to_value(items).unwrap())
}
