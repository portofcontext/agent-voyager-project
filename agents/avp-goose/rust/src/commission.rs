//! Map an AVP `Commission` onto Goose `Agent` configuration.
//!
//! The runner applies the result to a fresh `Agent`: model via the provider,
//! `extensions` via `add_extensions_bulk`, `system_prompt` via
//! `extend_system_prompt`, structured output via `add_final_output_tool`, and
//! `prompt` as the first user message to `reply`.
//!
//! Provider: a Commission's optional `provider` block names the storefront
//! (`provider.id`). When absent, the runner falls back to the model slug's
//! origin (and, as a transitional bridge, the `GOOSE_PROVIDER` env). The
//! provider's `base_url`/`credential` reach goose via env the supervisor sets
//! (`<ID>_HOST` / `<ID>_API_KEY`), which goose's provider factory reads.
//!
//! The default built-in surface mirrors stock goose: every `default_enabled`
//! platform extension (developer, analyze, todo, apps, ext_manager, summon for
//! subagents, tom, skills, …) plus the bundled goose-mcp built-ins. `skills` and
//! `summon` are therefore on by default (not gated behind Commission fields);
//! the runner still materializes inline `skills` SKILL.md files under the working
//! dir's `.agents/skills` so that extension discovers them. `enabled_builtin_tools`
//! subtractively filters the whole surface. Per-server HTTP `headers` are
//! forwarded; an `auth` SecretRef is resolved from the supervisor-injected
//! `AVP_VAULT_<HANDLE>` env var into a bearer header (the value never appears
//! in the Commission, so it stays out of the trajectory).

use std::collections::HashMap;
use std::sync::Once;

use avp::commission::{AvpV01CommissionMcpServersItem, McpServerHttp, McpServerStdio};
use avp::Commission;
use goose::agents::extension::{Envs, ExtensionConfig};
use goose::recipe::Response;

/// Register goose's bundled built-in extension servers (goose-mcp:
/// computercontroller / memory / tutorial / autovisualiser) into goose's global
/// in-process `BUILTIN_REGISTRY`. Idempotent; MUST run before the agent loads any
/// `Builtin` extension. The goose CLI does this at startup; the library embedding
/// has to do it explicitly, or the registry stays empty and Builtins fail to
/// resolve (which is why this connector historically only exposed `developer`).
pub fn register_builtins() {
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        goose::builtin_extension::register_builtin_extensions(goose_mcp::BUILTIN_EXTENSIONS.clone());
    });
}

/// Goose-side run configuration derived from a Commission.
pub struct GooseRunConfig {
    /// The full canonical `origin/model` slug (the runner splits off the origin
    /// for the SDK-native model id, and keeps the slug for pricing/descriptor).
    pub model: Option<String>,
    /// The storefront `provider.id` from the Commission, if any.
    pub provider_id: Option<String>,
    pub system_prompt: Option<String>,
    pub prompt: Option<String>,
    pub extensions: Vec<ExtensionConfig>,
    pub response: Option<Response>,
}

/// Project a Commission into Goose run configuration.
pub fn from_commission(commission: &Commission) -> GooseRunConfig {
    let mut extensions = Vec::new();

    // Goose's full default built-in surface (every `default_enabled` platform
    // extension + the bundled goose-mcp built-ins; see `builtin_extensions`). AVP
    // `enabled_builtin_tools` subtractively filters it (per spec; claude-agent-sdk
    // is the reference): `None` exposes everything, `[]` exposes none, and a list
    // exposes only the named tools. The names are descriptor-namespace (bare for
    // unprefixed platform extensions like `developer`, `<ext>__<tool>` otherwise);
    // `builtin_extensions` translates each to that extension's bare
    // `available_tools` (see `available_for`). `summon` (subagents) and `skills`
    // are part of this default surface — not gated behind Commission fields.
    match commission.enabled_builtin_tools.as_deref() {
        None => extensions.extend(builtin_extensions(Vec::new())),
        Some([]) => {}
        Some(names) => extensions.extend(builtin_extensions(names.to_vec())),
    }

    // Commission-supplied MCP servers carry inline connection material.
    for server in commission.mcp_servers.iter().flatten() {
        extensions.push(match server {
            AvpV01CommissionMcpServersItem::Stdio(s) => stdio_extension(s),
            AvpV01CommissionMcpServersItem::Http(h) => http_extension(h),
        });
    }

    let response = commission.output_schema.as_ref().map(|schema| Response {
        json_schema: Some(serde_json::Value::Object(schema.clone())),
    });

    GooseRunConfig {
        model: Some(commission.model.to_string()),
        provider_id: commission.provider.as_ref().map(|p| p.id.to_string()),
        system_prompt: commission.system_prompt.clone(),
        prompt: commission.prompt.clone(),
        extensions,
        response,
    }
}

/// A name no goose tool uses. A non-empty `available_tools` holding only this
/// exposes zero tools, which is how we say "this extension contributes nothing"
/// (goose treats an *empty* `available_tools` as "expose all").
const EXPOSE_NONE: &str = "__avp_expose_none__";

/// Translate the AVP `enabled_builtin_tools` allow-list (descriptor-namespace
/// names) into one extension's bare `available_tools`.
///
/// `enabled_builtin_tools` names tools the way the agent surfaces them, matching
/// `descriptor.tools` and the model-facing names (the contract claude-agent-sdk
/// uses): BARE for the unprefixed `developer` platform extension (`shell`), and
/// `<ext>__<tool>` for every prefixed goose-mcp built-in
/// (`computercontroller__pdf_tool`). But goose's own per-extension
/// `available_tools` filter matches the BARE tool name, so we translate here.
///
/// `prefix` is `None` for the unprefixed `developer` extension, `Some("memory")`
/// etc. for a prefixed built-in. An empty `enabled` is the `None` / "expose
/// everything" case and yields an empty list (all tools). A non-empty `enabled`
/// that names nothing in this extension yields `[EXPOSE_NONE]` so the extension
/// is pruned rather than fully exposed.
fn available_for(enabled: &[String], prefix: Option<&str>) -> Vec<String> {
    if enabled.is_empty() {
        return Vec::new(); // None: expose everything
    }
    let bare: Vec<String> = match prefix {
        None => enabled.iter().filter(|n| !n.contains("__")).cloned().collect(),
        Some(p) => {
            let pfx = format!("{p}__");
            enabled.iter().filter_map(|n| n.strip_prefix(&pfx).map(str::to_string)).collect()
        }
    };
    if bare.is_empty() { vec![EXPOSE_NONE.to_string()] } else { bare }
}

/// Goose's full default built-in surface: every `default_enabled` platform
/// extension (developer, analyze, todo, apps, ext_manager, summon, tom, skills, …
/// read live from goose's `PLATFORM_EXTENSIONS` so it tracks the pinned rev) plus
/// every bundled goose-mcp built-in. This mirrors what stock goose loads by
/// default, so `avp agent describe` advertises it and an unfiltered run gets it.
///
/// `enabled` is the AVP allow-list in descriptor namespace; each extension is
/// filtered to its own slice via [`available_for`] (empty `enabled` = every tool
/// of every extension). Platform extensions whose tools surface unprefixed
/// (`unprefixed_tools`, e.g. `developer`) are matched bare; everything else is
/// matched `<ext>__<tool>`. Requires `register_builtins()` to have run before the
/// agent loads the goose-mcp `Builtin`s.
fn builtin_extensions(enabled: Vec<String>) -> Vec<ExtensionConfig> {
    use goose::agents::platform_extensions::PLATFORM_EXTENSIONS;

    let mut exts = Vec::new();

    // Default-enabled platform extensions (goose's real default surface).
    let mut platform: Vec<(&str, bool)> = PLATFORM_EXTENSIONS
        .iter()
        .filter(|(_, def)| def.default_enabled && !def.hidden)
        .map(|(name, def)| (*name, def.unprefixed_tools))
        .collect();
    platform.sort_unstable_by_key(|(name, _)| *name);
    for (name, unprefixed) in platform {
        let prefix = if unprefixed { None } else { Some(name) };
        exts.push(ExtensionConfig::Platform {
            name: name.to_string(),
            description: String::new(),
            display_name: None,
            bundled: Some(true),
            available_tools: available_for(&enabled, prefix),
        });
    }

    // Bundled goose-mcp built-ins (autovisualiser / computercontroller / memory /
    // tutorial); their tools surface prefixed `<ext>__<tool>`.
    let mut names: Vec<&'static str> = goose_mcp::BUILTIN_EXTENSIONS.keys().copied().collect();
    names.sort_unstable();
    for name in names {
        exts.push(ExtensionConfig::Builtin {
            name: name.to_string(),
            description: String::new(),
            display_name: None,
            timeout: None,
            bundled: Some(true),
            available_tools: available_for(&enabled, Some(name)),
        });
    }
    exts
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
    // Forward non-secret headers, then resolve an `auth` SecretRef from the
    // supervisor-injected `AVP_VAULT_<HANDLE>` env into a bearer header. The
    // handle (not the value) is what travels in the Commission.
    let mut headers: HashMap<String, String> = h.headers.clone().unwrap_or_default();
    if let Some(auth) = &h.auth {
        let var = format!("AVP_VAULT_{}", auth.vault.to_uppercase().replace('-', "_"));
        if let Ok(value) = std::env::var(&var) {
            headers.insert("Authorization".to_string(), format!("Bearer {value}"));
        }
    }
    ExtensionConfig::StreamableHttp {
        name: h.id.to_string(),
        description: String::new(),
        uri: h.url.to_string(),
        envs: Envs::new(HashMap::new()),
        env_keys: Vec::new(),
        headers,
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

    fn builtin_available_tools(cfg: &GooseRunConfig, ext: &str) -> Option<Vec<String>> {
        cfg.extensions.iter().find_map(|e| match e {
            ExtensionConfig::Builtin {
                name,
                available_tools,
                ..
            } if name == ext => Some(available_tools.clone()),
            _ => None,
        })
    }

    #[test]
    fn maps_builtins_mcp_and_skills_to_extensions() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "x/m",
            "mcp_servers": [
                { "type": "stdio", "id": "avptest", "command": ["uv", "run"] },
                { "type": "http", "id": "web", "url": "https://example.com/mcp" }
            ],
            "skills": [{ "id": "researcher", "files": { "SKILL.md": "# research" } }]
        })));
        let names = ext_names(&cfg);
        // The full built-in surface loads by default (no enabled_builtin_tools
        // override): developer + the bundled goose-mcp built-ins.
        assert!(names.contains(&"developer".to_string()), "builtin: {names:?}");
        assert!(names.contains(&"memory".to_string()), "goose-mcp builtin: {names:?}");
        assert!(names.contains(&"avptest".to_string()), "stdio mcp: {names:?}");
        assert!(names.contains(&"web".to_string()), "http mcp: {names:?}");
        assert!(names.contains(&"skills".to_string()), "skills platform: {names:?}");
    }

    #[test]
    fn default_loads_full_builtin_catalog() {
        // None -> goose's full default surface: every default-enabled platform
        // extension (incl. summon=subagents and skills) + every goose-mcp built-in.
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "x/m"
        })));
        let names = ext_names(&cfg);
        for platform in ["developer", "summon", "skills"] {
            assert!(names.contains(&platform.to_string()), "missing {platform}: {names:?}");
        }
        for builtin in goose_mcp::BUILTIN_EXTENSIONS.keys() {
            assert!(names.contains(&builtin.to_string()), "missing {builtin}: {names:?}");
        }
        // Every default-enabled platform extension goose ships is loaded.
        use goose::agents::platform_extensions::PLATFORM_EXTENSIONS;
        for (name, def) in PLATFORM_EXTENSIONS.iter() {
            if def.default_enabled && !def.hidden {
                assert!(names.contains(&name.to_string()), "missing default platform {name}: {names:?}");
            }
        }
    }

    #[test]
    fn enabled_builtin_tools_default_loads_developer_unfiltered() {
        // None -> all built-in tools (developer with an empty allow-list).
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "x/m"
        })));
        assert_eq!(developer_available_tools(&cfg), Some(vec![]));
    }

    #[test]
    fn empty_enabled_builtin_tools_omits_all_builtins() {
        // [] -> no built-in tools: neither developer nor any goose-mcp built-in.
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "x/m",
            "enabled_builtin_tools": []
        })));
        let names = ext_names(&cfg);
        assert!(!names.contains(&"developer".to_string()), "{names:?}");
        for builtin in goose_mcp::BUILTIN_EXTENSIONS.keys() {
            assert!(!names.contains(&builtin.to_string()), "leaked {builtin}: {names:?}");
        }
    }

    #[test]
    fn enabled_builtin_tools_subset_sets_available_tools() {
        // A bare name targets the unprefixed `developer` extension; its filter
        // matches the bare tool name. Other extensions get no match, so they are
        // pruned (EXPOSE_NONE) rather than fully exposed.
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "x/m",
            "enabled_builtin_tools": ["shell"]
        })));
        assert_eq!(developer_available_tools(&cfg), Some(vec!["shell".to_string()]));
        assert_eq!(
            builtin_available_tools(&cfg, "computercontroller"),
            Some(vec![EXPOSE_NONE.to_string()])
        );
    }

    #[test]
    fn enabled_builtin_tools_prefixed_name_targets_its_builtin_bare() {
        // A `<ext>__<tool>` descriptor name (what `avp agent describe` shows for a
        // goose-mcp built-in) is translated to that extension's BARE
        // `available_tools` entry, while the unprefixed `developer` is pruned.
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "x/m",
            "enabled_builtin_tools": ["computercontroller__pdf_tool", "computercontroller__web_scrape"]
        })));
        assert_eq!(
            builtin_available_tools(&cfg, "computercontroller"),
            Some(vec!["pdf_tool".to_string(), "web_scrape".to_string()])
        );
        assert_eq!(developer_available_tools(&cfg), Some(vec![EXPOSE_NONE.to_string()]));
    }

    #[test]
    fn stdio_command_splits_into_cmd_and_args() {
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "x/m",
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
            "schema_version": "0.1", "run_id": "r1", "model": "x/m",
            "output_schema": { "type": "object", "properties": { "answer": { "type": "string" } } }
        })));
        let response = cfg.response.expect("response set");
        assert!(response.json_schema.is_some());
    }

    #[test]
    fn summon_and_skills_load_by_default() {
        // Goose enables summon (subagents) and skills by default, so an unfiltered
        // Commission gets both — they are NOT gated behind Commission fields.
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "x/m"
        })));
        let names = ext_names(&cfg);
        assert!(names.contains(&"summon".to_string()), "{names:?}");
        assert!(names.contains(&"skills".to_string()), "{names:?}");
    }

    #[test]
    fn empty_allowlist_omits_summon_and_skills_too() {
        // [] hides the whole built-in surface, including the default platform
        // extensions (summon/skills), not just the goose-mcp built-ins.
        let cfg = from_commission(&commission(json!({
            "schema_version": "0.1", "run_id": "r1", "model": "x/m",
            "enabled_builtin_tools": []
        })));
        let names = ext_names(&cfg);
        assert!(!names.contains(&"summon".to_string()), "{names:?}");
        assert!(!names.contains(&"skills".to_string()), "{names:?}");
    }
}
