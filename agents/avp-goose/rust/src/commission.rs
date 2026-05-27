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

    // Goose's built-in tool surface is the `developer` extension (goose's
    // DEFAULT_EXTENSION), loaded by default — as the real goose CLI does, where
    // `developer` ships enabled. AVP `enabled_builtin_tools` subtractively
    // filters that surface (per spec; the claude-agent-sdk is the reference for
    // this semantic): `None` exposes all developer tools, `[]` exposes none
    // (developer not loaded), and a list exposes only the named tools via the
    // extension's own `available_tools` allow-list.
    match commission.enabled_builtin_tools.as_deref() {
        None => extensions.push(developer_extension(Vec::new())),
        Some([]) => {}
        Some(names) => extensions.push(developer_extension(names.to_vec())),
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

    // Subagents: enable the `summon` platform extension so the model can
    // delegate to subagent recipes (scanned from the working dir's
    // `.agents/recipes`). AVP's `enabled_builtin_subagents` is the signal to turn
    // the capability on; the summonable recipes themselves come from the
    // environment (the Commission carries names, not inline recipe definitions
    // — see TECH_DEBT).
    if commission.enabled_builtin_subagents.as_ref().is_some_and(|s| !s.is_empty()) {
        extensions.push(ExtensionConfig::Platform {
            name: "summon".to_string(),
            description: "Load knowledge and delegate tasks to subagents".to_string(),
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

/// Goose's default built-in tool extension (`developer`), optionally restricted
/// to `available_tools` (empty = expose all of its tools). `developer` is a
/// first-class PLATFORM extension served in-process from the goose library
/// (`PLATFORM_EXTENSIONS`), like `skills`/`summon` above — NOT a `Builtin` (those
/// resolve through the `goose-mcp` registry, which this embedding doesn't load).
fn developer_extension(available_tools: Vec<String>) -> ExtensionConfig {
    ExtensionConfig::Platform {
        name: "developer".to_string(),
        description: "Core developer tools".to_string(),
        display_name: Some("Developer".to_string()),
        bundled: Some(true),
        available_tools,
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

    fn developer_available_tools(cfg: &GooseRunConfig) -> Option<Vec<String>> {
        cfg.extensions.iter().find_map(|e| match e {
            ExtensionConfig::Platform {
                name,
                available_tools,
                ..
            } if name == "developer" => Some(available_tools.clone()),
            _ => None,
        })
    }

    #[test]
    fn maps_builtins_mcp_and_skills_to_extensions() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m",
            "mcp_servers": [
                { "type": "stdio", "id": "avptest", "command": ["uv", "run"] },
                { "type": "http", "id": "web", "url": "https://example.com/mcp" }
            ],
            "skills": [{ "id": "researcher", "files": { "SKILL.md": "# research" } }]
        })));
        let names = ext_names(&cfg);
        // `developer` loads by default (no enabled_builtin_tools override).
        assert!(names.contains(&"developer".to_string()), "builtin: {names:?}");
        assert!(names.contains(&"avptest".to_string()), "stdio mcp: {names:?}");
        assert!(names.contains(&"web".to_string()), "http mcp: {names:?}");
        assert!(names.contains(&"skills".to_string()), "skills platform: {names:?}");
    }

    #[test]
    fn enabled_builtin_tools_default_loads_developer_unfiltered() {
        // None -> all built-in tools (developer with an empty allow-list).
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m"
        })));
        assert_eq!(developer_available_tools(&cfg), Some(vec![]));
    }

    #[test]
    fn empty_enabled_builtin_tools_omits_developer() {
        // [] -> no built-in tools: developer is not loaded at all.
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m",
            "enabled_builtin_tools": []
        })));
        assert!(!ext_names(&cfg).contains(&"developer".to_string()));
    }

    #[test]
    fn enabled_builtin_tools_subset_sets_available_tools() {
        // [names] -> developer restricted to those tools via available_tools.
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m",
            "enabled_builtin_tools": ["developer__shell"]
        })));
        assert_eq!(
            developer_available_tools(&cfg),
            Some(vec!["developer__shell".to_string()])
        );
    }

    #[test]
    fn stdio_command_splits_into_cmd_and_args() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m",
            "mcp_servers": [{ "type": "stdio", "id": "x",
                "command": ["uv", "run", "server.py"], "args": ["--flag"] }]
        })));
        let stdio = cfg
            .extensions
            .iter()
            .find(|e| matches!(e, ExtensionConfig::Stdio { .. }))
            .expect("stdio extension present");
        match stdio {
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

    #[test]
    fn enabled_builtin_subagents_enables_summon() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m",
            "enabled_builtin_subagents": ["echoer"]
        })));
        assert!(ext_names(&cfg).contains(&"summon".to_string()), "{:?}", ext_names(&cfg));
    }

    #[test]
    fn no_subagents_means_no_summon() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "m"
        })));
        assert!(!ext_names(&cfg).contains(&"summon".to_string()));
    }
}
