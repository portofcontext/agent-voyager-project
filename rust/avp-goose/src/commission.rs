//! Map an AVP `Commission` onto Goose `Agent` configuration.
//!
//! The runner applies the result to a fresh `Agent`: model via the provider,
//! `extensions` via `add_extensions_bulk`, `system_prompt` via
//! `extend_system_prompt`, structured output via `add_final_output_tool`, and
//! `prompt` as the first user message to `reply`.
//!
//! Provider is intentionally not derived here: a Commission carries `model` but
//! not a provider, so the runner resolves the provider from the Goose
//! environment (`GOOSE_PROVIDER`), the same way the CLI does.
//!
//! Inline `skills` enable the `skills` platform extension here; the runner
//! materializes their SKILL.md files under the working dir's `.agents/skills`
//! so Goose discovers them. Not yet mapped: per-server `env` / `headers`
//! (carried as empty until the secret-handling story is settled).

use std::collections::HashMap;

use avp::commission::{AvpV01CommissionMcpServersItem, McpServerHttp, McpServerStdio};
use avp::Commission;
use goose::agents::extension::{Envs, ExtensionConfig};
use goose::recipe::Response;

/// Goose-side run configuration derived from a Commission.
pub struct GooseRunConfig {
    pub model: Option<String>,
    pub system_prompt: Option<String>,
    pub prompt: Option<String>,
    pub extensions: Vec<ExtensionConfig>,
    pub response: Option<Response>,
}

/// Project a Commission into Goose run configuration.
pub fn from_commission(commission: &Commission) -> GooseRunConfig {
    let mut extensions = Vec::new();

    // Built-in extensions the Commission enables. AVP `enabled_builtin_tools`
    // is an allowlist of names; Goose enables whole extensions, so each name is
    // treated as a builtin extension to load.
    for name in commission.enabled_builtin_tools.iter().flatten() {
        extensions.push(ExtensionConfig::Builtin {
            name: name.clone(),
            description: String::new(),
            display_name: None,
            timeout: None,
            bundled: None,
            available_tools: Vec::new(),
        });
    }

    // Commission-supplied MCP servers carry inline connection material.
    for server in commission.mcp_servers.iter().flatten() {
        extensions.push(match server {
            AvpV01CommissionMcpServersItem::Stdio(s) => stdio_extension(s),
            AvpV01CommissionMcpServersItem::Http(h) => http_extension(h),
        });
    }

    // Inline skills: enable the skills platform extension so Goose discovers
    // the files the runner writes to the working dir's `.agents/skills`.
    if commission.skills.as_ref().is_some_and(|s| !s.is_empty()) {
        extensions.push(ExtensionConfig::Platform {
            name: "skills".to_string(),
            description: "Discover and load skills from the filesystem".to_string(),
            display_name: None,
            bundled: None,
            available_tools: Vec::new(),
        });
    }

    let response = commission.output_schema.as_ref().map(|schema| Response {
        json_schema: Some(serde_json::Value::Object(schema.clone())),
    });

    GooseRunConfig {
        model: commission.model.clone(),
        system_prompt: commission.system_prompt.clone(),
        prompt: commission.prompt.clone(),
        extensions,
        response,
    }
}

fn stdio_extension(s: &McpServerStdio) -> ExtensionConfig {
    // `command` is argv: the first element is the executable, the rest precede
    // any explicit `args`.
    let (cmd, head) = match s.command.split_first() {
        Some((first, rest)) => (first.clone(), rest.to_vec()),
        None => (String::new(), Vec::new()),
    };
    let mut args = head;
    if let Some(extra) = &s.args {
        args.extend(extra.iter().cloned());
    }
    ExtensionConfig::Stdio {
        name: s.id.to_string(),
        description: String::new(),
        cmd,
        args,
        envs: Envs::new(HashMap::new()),
        env_keys: Vec::new(),
        timeout: None,
        bundled: None,
        available_tools: Vec::new(),
    }
}

fn http_extension(h: &McpServerHttp) -> ExtensionConfig {
    ExtensionConfig::StreamableHttp {
        name: h.id.to_string(),
        description: String::new(),
        uri: h.url.to_string(),
        envs: Envs::new(HashMap::new()),
        env_keys: Vec::new(),
        headers: HashMap::new(),
        timeout: None,
        socket: None,
        bundled: None,
        available_tools: Vec::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn commission(v: serde_json::Value) -> Commission {
        serde_json::from_value(v).expect("valid Commission")
    }

    fn ext_names(cfg: &GooseRunConfig) -> Vec<String> {
        cfg.extensions
            .iter()
            .map(|e| e.name().to_string())
            .collect()
    }

    #[test]
    fn maps_builtins_mcp_and_skills_to_extensions() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m",
            "enabled_builtin_tools": ["developer"],
            "mcp_servers": [
                { "type": "stdio", "id": "gtm", "command": ["uv", "run"] },
                { "type": "http", "id": "web", "url": "https://example.com/mcp" }
            ],
            "skills": [{ "id": "researcher", "files": { "SKILL.md": "# research" } }]
        })));
        let names = ext_names(&cfg);
        assert!(
            names.contains(&"developer".to_string()),
            "builtin: {names:?}"
        );
        assert!(names.contains(&"gtm".to_string()), "stdio mcp: {names:?}");
        assert!(names.contains(&"web".to_string()), "http mcp: {names:?}");
        assert!(
            names.contains(&"skills".to_string()),
            "skills platform: {names:?}"
        );
    }

    #[test]
    fn stdio_command_splits_into_cmd_and_args() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m",
            "mcp_servers": [{ "type": "stdio", "id": "x",
                "command": ["uv", "run", "server.py"], "args": ["--flag"] }]
        })));
        match &cfg.extensions[0] {
            ExtensionConfig::Stdio { cmd, args, .. } => {
                assert_eq!(cmd, "uv");
                assert_eq!(
                    args,
                    &vec![
                        "run".to_string(),
                        "server.py".to_string(),
                        "--flag".to_string()
                    ]
                );
            }
            other => panic!("expected stdio, got {other:?}"),
        }
    }

    #[test]
    fn output_schema_becomes_response() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m",
            "output_schema": { "type": "object", "properties": { "answer": { "type": "string" } } }
        })));
        let response = cfg.response.expect("response set");
        assert!(response.json_schema.is_some());
    }

    #[test]
    fn no_skills_means_no_skills_extension() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m"
        })));
        assert!(!ext_names(&cfg).contains(&"skills".to_string()));
    }
}
