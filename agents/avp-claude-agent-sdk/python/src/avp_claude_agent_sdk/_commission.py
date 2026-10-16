"""Commission → ClaudeAgentOptions translation for the Claude Agent SDK.

## Commission → ClaudeAgentOptions mapping

| Commission field              | ClaudeAgentOptions field        | Notes                                                                        |
|-------------------------------|---------------------------------|------------------------------------------------------------------------------|
| `model`                       | `model`                         | Slug split: `"anthropic/claude-opus-4-8"` → SDK `model="claude-opus-4-8"`.   |
| `provider`                    | *(env, set by supervisor)*      | Only `id: "anthropic"` is supported (the SDK speaks Anthropic protocol);     |
|                               |                                 | `base_url`/`credential` reach the SDK via ANTHROPIC_BASE_URL/ANTHROPIC_API_KEY|
|                               |                                 | set by the supervisor. Any other `id` → `UnsupportedProvider` (fail-fast).   |
| `system_prompt`               | `system_prompt`                 | Direct.                                                                      |
| `prompt`                      | *(query call arg)*              | Direct.                                                                      |
| `mcp_servers` (inline)        | `mcp_servers` dict              | `id` becomes the dict key. `McpServerHttp` → `McpHttpServerConfig`;           |
|                               |                                 | `McpServerStdio.command[0]` → SDK `command`, `command[1:] + args` → SDK      |
|                               |                                 | `args`. Connection material comes inline off the Commission.                 |
| `skills` (inline)             | `skills` list + files on disk   | The SDK `skills` field is a name-based context filter that cannot ingest      |
|                               |                                 | inline content, so each `Skill.files` is materialized to                      |
|                               |                                 | `<cwd>/.claude/skills/<id>/` (where the CLI discovers project skills once     |
|                               |                                 | `skills` is set) and the `skill.name` (frontmatter, fallback `skill.id`) is   |
|                               |                                 | passed in `skills`, merged with `enabled_builtin_skills`.                     |
| `enabled_builtin_tools`       | `tools`                         | `None` → leave `options.tools` untouched (AVP spec: expose all); `[]` →      |
|                               |                                 | `tools=[]` (expose none); `[...]` → `tools=[...]` (expose only the listed). |
| `enabled_builtin_skills`      | `skills`                        | Absent → `"all"` when the Commission brings skills, else unset; present →    |
|                               |                                 | the Commission's skill names plus the listed built-ins (`[]` exposes none).  |
| `enabled_builtin_mcp_servers` | `mcp_servers`                   | Filters the base options' servers (the built-ins); Commission servers stay.  |
|                               |                                 | Callers pass `strict_mcp_config` so the CLI loads no others.                 |
| `enabled_builtin_subagents`   | `disallowed_tools`              | `Agent(<name>)` for each probed built-in subagent the list leaves out; `[]`  |
|                               |                                 | disallows the `Agent` tool. Set in `connect()`, after the probe.             |
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
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import ClaudeAgentOptions, McpServerConfig

from avp.commission import Commission
from avp.commission import McpServerHttp as AVPMcpServerHttp
from avp.commission import McpServerStdio as AVPMcpServerStdio
from avp_claude_agent_sdk._translator import _AGENT_NAME


class UnsupportedProvider(Exception):
    """The Commission requests a provider this agent cannot speak.

    The Claude Agent SDK speaks the Anthropic protocol only, so any
    `provider.id` other than `"anthropic"` is unsatisfiable. The run loop
    catches this and emits `error_occurred` + `agent_stopped(reason=error)`
    rather than silently running on the wrong endpoint.
    """

    def __init__(self, provider_id: str) -> None:
        super().__init__(
            f"provider {provider_id!r} is not supported by the Claude Agent SDK "
            "(Anthropic protocol only); use provider.id 'anthropic' or an "
            "Anthropic-compatible gateway via base_url"
        )
        self.provider_id = provider_id


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
    - `mcp_servers` (inline)  → `mcp_servers`
    - `skills` (inline)       → files materialized to `<cwd>/.claude/skills/<id>/`
                                + `skills` (names), merged with `enabled_builtin_skills`
    - `enabled_builtin_skills`→ `skills` (see `_map_skills`)
    - `enabled_builtin_mcp_servers` → filters the base `mcp_servers`

    `enabled_builtin_subagents` needs the probed surface, so
    `AVPClaudeSDKClient.connect` applies it.
    """
    if commission is None:
        return options

    # The SDK speaks Anthropic protocol only. A non-anthropic provider is
    # unsatisfiable; fail fast rather than silently using the native endpoint.
    if commission.provider is not None and commission.provider.id != "anthropic":
        raise UnsupportedProvider(commission.provider.id)

    base = options if options is not None else ClaudeAgentOptions()
    updates: dict[str, Any] = {}

    # model is a canonical "origin/model" slug; the SDK wants the bare model id.
    updates["model"] = commission.model.split("/", 1)[1]
    if commission.system_prompt is not None:
        updates["system_prompt"] = commission.system_prompt
    # Per AVP spec §4: the allowlist maps are keyed by descriptor.agent_name;
    # we read only our own key. No map / no key here = leave options.tools
    # alone ([] = expose none; [...] = expose only the listed names). A
    # present map MISSING our key is a commission_collision, but that
    # fail-fast lands in the client's query() so it reaches the trajectory;
    # options construction stays total (the run aborts before any model call).
    allow_tools = (commission.enabled_builtin_tools or {}).get(_AGENT_NAME)
    if allow_tools is not None:
        updates["tools"] = list(allow_tools)
    if commission.output_schema is not None:
        updates["output_format"] = {
            "type": "json_schema",
            "schema": commission.output_schema,
        }
    # Inline MCP servers: merge the Commission's onto the base ones the
    # allow-list keeps (Commission id wins on collision). The SDK dials them; they surface on
    # agent_started.data.avp.mcp_servers.
    base_servers = base.mcp_servers if isinstance(base.mcp_servers, dict) else {}
    allow_servers = (commission.enabled_builtin_mcp_servers or {}).get(_AGENT_NAME)
    if allow_servers is not None:
        base_servers = {k: v for k, v in base_servers.items() if k in allow_servers}
    if commission.mcp_servers or allow_servers is not None:
        updates["mcp_servers"] = {**base_servers, **_map_mcp_servers(commission)}

    # Inline skills: the SDK `skills` field is a name-based context filter that
    # cannot ingest inline content, so the files must exist on disk where the CLI
    # discovers them. Materialize each Skill's files under the run cwd's
    # `.claude/skills/<id>/` (the SDK loads project skills from there once
    # `skills` is set) and pass the names. enabled_builtin_skills merge in too.
    if commission.skills:
        _materialize_skills(commission, _run_cwd(base))
        # The materialized skill lives in the run cwd's `.claude/skills/`, a
        # PROJECT skill. Project skills load only when `setting_sources` includes
        # "project" — and a caller may pass `setting_sources=[]` for host
        # isolation (the conformance run does, to avoid inheriting ~/.claude).
        # Add "project" so the inline skill is discovered, without adding "user"
        # (which would re-inherit the host settings the caller isolated from).
        sources = list(base.setting_sources or [])
        if "project" not in sources:
            sources.append("project")
        updates["setting_sources"] = sources
    skills = _map_skills(commission)
    if skills is not None:
        updates["skills"] = skills

    return dataclasses.replace(base, **updates) if updates else base


def _run_cwd(options: ClaudeAgentOptions) -> Path:
    """The directory the SDK subprocess will run in (and where it discovers
    project skills): `options.cwd` if set, else the current process cwd."""
    return Path(options.cwd).expanduser() if options.cwd else Path.cwd()


def _materialize_skills(commission: Commission, base_dir: Path) -> None:
    """Write each inline Skill's files under `<base_dir>/.claude/skills/<id>/`.

    The SDK discovers project skills from the run cwd's `.claude/skills/` once
    `ClaudeAgentOptions.skills` is set (it then defaults `setting_sources` to
    include "project"). `Skill.files` always contains "SKILL.md" (validated on
    the wire model); any companion files are written alongside it.
    """
    for skill in commission.skills or []:
        dest = base_dir / ".claude" / "skills" / skill.id
        dest.mkdir(parents=True, exist_ok=True)
        for filename, content in skill.files.items():
            (dest / filename).write_text(content)


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
            # `auth` is a SecretRef the supervisor resolves out of band (the avp
            # CLI injects it at its credential broker); the agent only forwards
            # the connection material it is given and never resolves handles.
            cfg: dict[str, McpServerConfig] = {"type": "http", "url": server.url}
            if server.headers:
                cfg["headers"] = dict(server.headers)
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


def _map_skills(commission: Commission) -> list[str] | Literal["all"] | None:
    """The SDK `skills` filter for the Commission.

    The filter hides every skill it does not name, so an absent
    `enabled_builtin_skills` becomes `"all"` when the Commission brings skills
    (keeping the built-ins) and stays unset otherwise. A present list names the
    Commission's skills (SKILL.md frontmatter `name`, else `skill.id`) plus the
    allowed built-ins, so `[]` with no Commission skills exposes none.
    """
    allowed = (commission.enabled_builtin_skills or {}).get(_AGENT_NAME)
    if allowed is None:
        return "all" if commission.skills else None
    names: list[str] = []
    for name in [*(skill.name or skill.id for skill in commission.skills or []), *allowed]:
        if name not in names:
            names.append(name)
    return names
