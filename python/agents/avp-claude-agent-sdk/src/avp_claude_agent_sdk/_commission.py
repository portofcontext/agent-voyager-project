"""Commission → ClaudeAgentOptions translation for the Claude Agent SDK.

## Commission → ClaudeAgentOptions mapping

| Commission field              | ClaudeAgentOptions field        | Notes                                                                        |
|-------------------------------|---------------------------------|------------------------------------------------------------------------------|
| `model`                       | `model`                         | Direct.                                                                      |
| `system_prompt`               | `system_prompt`                 | Direct.                                                                      |
| `prompt`                      | *(query call arg)*              | Direct.                                                                      |
| `mcp_servers` (inline)        | `mcp_servers` dict              | `id` becomes the dict key. `McpServerHttp` → `McpHttpServerConfig`;           |
|                               |                                 | `McpServerStdio.command[0]` → SDK `command`, `command[1:] + args` → SDK      |
|                               |                                 | `args`. No resolver round-trip; connection material is inline on the wire.   |
| `skills` (inline)             | `skills` list                   | `skill.name` (SKILL.md frontmatter, fallback to `skill.id`) merged with      |
|                               |                                 | `enabled_builtin_skills`. The SDK `skills` field is a name-based context      |
|                               |                                 | filter and cannot ingest inline file content; skills with `files` content       |
|                               |                                 | must also exist on disk where the SDK can discover them. TODO: write inline  |
|                               |                                 | `Skill.files` to a temp dir and add via `setting_sources` / `add_dirs`.       |
| `enabled_builtin_tools`       | `tools`                         | `None` → leave `options.tools` untouched (AVP spec: expose all); `[]` →      |
|                               |                                 | `tools=[]` (expose none); `[...]` → `tools=[...]` (expose only the listed). |
| `enabled_builtin_skills`      | `skills`                        | Merged with Commission-supplied skill names.                                 |
| `enabled_builtin_mcp_servers` | *(no clean mapping)*            | No per-server filter in SDK options. Workaround: `strict_mcp_config=True`   |
|                               |                                 | + pass only the listed server configs in `mcp_servers`. Loses built-in CLI  |
|                               |                                 | servers not in the Commission. TODO: confirm with SDK team.                  |
| `enabled_builtin_subagents`   | *(no clean mapping)*            | `options.agents` defines custom agents, not filters built-in ones. The SDK  |
|                               |                                 | has no `disallowed_agents` / `allowed_agents` knob. Enforcement would have  |
|                               |                                 | to be in-loop (reject hallucinated Agent calls not in the allowlist).        |
| `output_schema`               | `output_format`                 | Wrapped as `{"type": "json_schema", "schema": output_schema}`.              |
| `run_id`                      | *(AVP-only)*                    | Used as the trajectory run_id; not passed to SDK `session_id` (avoids       |
|                               |                                 | namespace coupling / UUID-format conflicts).                                 |
| `supervisor`                  | *(AVP-only)*                    | Stamped on `run_requested` event; no SDK field.                              |
| `thread_id`                   | *(AVP-only)*                    | Stamped on `agent_started` event; no SDK field.                              |
| `tags`                        | *(AVP-only)*                    | Stamped on `agent_started` event; no SDK field.                              |
| `meta`                        | *(no equivalent)*               | No SDK field. AVP metadata only.                                             |

Note: AVP v0.1 dropped the Resolver API and the `Commission.subagents` field.
Commission-managed assets (`mcp_servers`, `skills`) carry inline connection
material; the agent dials and loads them directly.
"""

import dataclasses
from collections.abc import AsyncIterable
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, McpServerConfig

from avp.commission import Commission
from avp.commission import McpServerHttp as AVPMcpServerHttp
from avp.commission import McpServerStdio as AVPMcpServerStdio


def apply_commission(
    commission: Commission | None,
    options: ClaudeAgentOptions | None,
) -> ClaudeAgentOptions | None:
    """Merge Commission overrides into caller-supplied ClaudeAgentOptions.

    Commission fields take precedence; caller options are preserved when the
    Commission doesn't speak to them. Returns `options` unchanged when no
    commission is provided.

    Implemented:
    - `model`                 → `model`
    - `system_prompt`         → `system_prompt`
    - `enabled_builtin_tools` → `tools`
    - `output_schema`         → `output_format` (wrapped as json_schema)

    TODO:
    - `mcp_servers` (inline) + `enabled_builtin_mcp_servers` filter
    - `skills` (inline) + `enabled_builtin_skills` filter
    """
    if commission is None:
        return options

    base = options if options is not None else ClaudeAgentOptions()
    updates: dict[str, Any] = {}

    if commission.model is not None:
        updates["model"] = commission.model
    if commission.system_prompt is not None:
        updates["system_prompt"] = commission.system_prompt
    # Per AVP spec: None = expose all (leave options.tools alone);
    # [] = expose none; [...] = expose only the listed names.
    if commission.enabled_builtin_tools is not None:
        updates["tools"] = list(commission.enabled_builtin_tools)
    if commission.output_schema is not None:
        updates["output_format"] = {
            "type": "json_schema",
            "schema": commission.output_schema,
        }

    return dataclasses.replace(base, **updates) if updates else base


def apply_prompt(
    commission: Commission | None,
    original_prompt: str | AsyncIterable[dict[str, Any]],
) -> str | AsyncIterable[dict[str, Any]]:
    if commission is not None and commission.prompt is not None:
        return commission.prompt
    return original_prompt


def _map_mcp_servers(commission: Commission) -> dict[str, McpServerConfig]:
    """Map Commission.mcp_servers inline entries to the SDK mcp_servers dict.

    `McpServerHttp` → `McpHttpServerConfig`; `McpServerStdio.command` (list)
    is split into SDK `command: str` (first element) + `args: list[str]`
    (rest, concatenated with Commission `args`).
    """
    result: dict[str, McpServerConfig] = {}
    for server in commission.mcp_servers or []:
        if isinstance(server, AVPMcpServerHttp):
            cfg: dict[str, McpServerConfig] = {"type": "http", "url": server.url}
            if server.headers:
                cfg["headers"] = server.headers
            result[server.id] = cfg
        elif isinstance(server, AVPMcpServerStdio):
            cmd, *rest = server.command
            args = rest + (server.args or [])
            cfg = {"command": cmd}
            if args:
                cfg["args"] = args
            if server.env:
                cfg["env"] = server.env
            result[server.id] = cfg
    return result


def _map_skills(commission: Commission) -> list[str]:
    """Merge Commission-supplied skill names with `enabled_builtin_skills`.

    Each `Skill` carries inline `files` content; the SDK `skills` field
    accepts only names (it's a context filter, not a content injector). We
    use the SKILL.md frontmatter `name` (fallback to `skill.id` when the
    frontmatter doesn't provide one) and union with `enabled_builtin_skills`.
    """
    names: list[str] = []
    for skill in commission.skills or []:
        name = skill.name or skill.id
        if name not in names:
            names.append(name)
    for name in commission.enabled_builtin_skills or []:
        if name not in names:
            names.append(name)
    return names
