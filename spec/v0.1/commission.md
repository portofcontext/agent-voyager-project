# AVP Commission Spec, v0.1

**Status:** Draft
**Stability:** beta. JSON shape, ref model, and allowlist semantics are stable; minor additive changes possible.
**Umbrella version:** v0.1 (see [`README.md`](./README.md))
**Schema:** [`commission.schema.json`](./commission.schema.json)
**$id base:** `https://avp.dev/schema/v0.1/`

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

---

## 1. Scope

The Commission Spec defines the **run-config object** a supervisor hands an agent at startup. It is a data-shape spec: it specifies the JSON object's structure and field semantics, but no wire-level protocol. A Commission can be:

- Sent over stdio or HTTP to an agent that will execute it (composes with [Trajectory](./trajectory.md)).
- Validated, generated, or rendered by tooling that never runs the agent loop (Commission alone).
- Embedded in audit records or transmitted between supervisor components (Commission alone).

When [Trajectory](./trajectory.md) is in scope, the Commission travels in the snapshot embedded in `run_requested.data["avp.commission"]`. When [Resolver API](./resolver.md) is in scope, the refs inside `mcp_servers` / `skills` / `subagents` are what the protocol dereferences. When [Agent Descriptor](./agent-descriptor.md) is in scope, the optional `enabled_builtin_*` allowlists reference descriptor-declared names.

### 1.1 Non-goals

The Commission Spec explicitly does **not** define:

- **The event stream the agent emits.** What flows *back* to the supervisor → see [`trajectory.md`](./trajectory.md).
- **How refs are dereferenced.** The wire protocol for `avp.resolve` / `avp.spawn_subagent` → see [`resolver.md`](./resolver.md).
- **What agents declare about themselves.** Pre-flight self-description → see [`agent-descriptor.md`](./agent-descriptor.md).
- **Inline connection material.** Commission carries opaque refs only, by design: no URLs, tokens, SKILL.md bodies, or subagent system prompts on the wire here. All such material arrives via the Resolver API at runtime.
- **Mid-run reconfiguration.** v0.1 has no supervisor → agent push channel. The Commission is one-shot.
- **Discovery.** How a supervisor finds an agent to send a Commission to is a deployment-layer concern.

---

## 2. The Commission shape

A Commission is a single JSON document validating against [`commission.schema.json`](./commission.schema.json):

```jsonc
{
  "schema_version": "0.1",
  "run_id": "auth-refactor-20260502-abc123",

  "supervisor": { "name": "acme-engineering-supervisor", "version": "2.4.1" },

  "prompt":        "Refactor the auth module to use JWT.",
  "system_prompt": "You are a senior Rust developer.",
  "model":         "claude-sonnet-4-6",

  "mcp_servers": [
    { "id": "github", "type": "http", "url": "https://mcp.example.com/github", "headers": { "Authorization": "Bearer ghp_..." } }
  ],
  "skills": [
    { "id": "style-guide", "files": { "SKILL.md": "---\nname: Style Guide\n---\n…" } },
    { "id": "code-runner", "files": { "SKILL.md": "---\nname: Code Runner\n---\n…", "scripts/run.sh": "#!/bin/sh\n…" } }
  ],
  "subagents": [
    { "id": "researcher", "ref": "sk_subagent_abc123" }
  ],

  "enabled_builtin_tools":       ["Read", "Grep", "Glob"],
  "enabled_builtin_subagents":   null,
  "enabled_builtin_skills":      null,
  "enabled_builtin_mcp_servers": null,

  "thread_id":     "session-xyz",
  "tags":          ["auth", "refactor"],
  "meta":          { "environment": "dev", "triggered_by": "ci" },
  "output_schema": null
}
```

### 2.1 Required fields

| Field | Type | Notes |
|---|---|---|
| `schema_version` | string | MUST equal `"0.1"`. |
| `run_id` | string | MUST be unique per run within the supervisor's namespace. Carried on every event's `subject`. |
| `prompt` | string | The model-facing instruction. |
| `model` | string | Provider-qualified model id (e.g., `"claude-sonnet-4-6"`, `"gpt-5"`). Agents validate against their Descriptor's `supported_models`. |

### 2.2 Optional fields

| Field | Type | Notes |
|---|---|---|
| `supervisor` | `{ name: string, version?: string }` | Attribution for `run_requested`. When absent, the corresponding `avp.supervisor.*` fields on `run_requested` are omitted (absence is the canonical signal; the prior `"unknown"` placeholder is superseded). |
| `system_prompt` | string | The agent's system context. Overrides `descriptor.system_prompt` when both are set. |
| `mcp_servers` | `Array<McpServerHttp \| McpServerStdio>` | Inline MCP server connection material, discriminated on `type`. See §3. |
| `skills` | `Array<Skill>` | Inline Agent Skills (SKILL.md content). See §3. |
| `subagents` | `Array<{ id: string, ref: JsonValue }>` | Managed subagent refs. See §3. |
| `enabled_builtin_tools` | `string[] \| null` | Allowlist over `descriptor.tools[].name`. See §4. |
| `enabled_builtin_subagents` | `string[] \| null` | Allowlist over `descriptor.subagents[].name`. See §4. |
| `enabled_builtin_skills` | `string[] \| null` | Allowlist over `descriptor.skills[].name`. See §4. |
| `enabled_builtin_mcp_servers` | `string[] \| null` | Allowlist over `descriptor.mcp_servers[].id`. Disabling a server prevents the agent from dialing it, so the tools that server would have surfaced are also unavailable for the run. See §4. |
| `thread_id` | string | Free-form correlation id (multi-turn conversation, parent context, etc.). |
| `tags` | `string[]` | Free-form labels. |
| `meta` | `object` | Free-form key/value bag. |
| `output_schema` | `object \| null` | A JSON Schema the supervisor wants the agent's final output to validate against. Agents that don't support structured output ignore it. |

---

## 3. Managed assets (inline)

`mcp_servers` and `skills` carry **inline connection material** in v0.1. No resolver round-trip is needed; the agent dials MCP servers and loads skill content directly from the Commission at startup.

### 3.1 MCP server entries

Each entry in `mcp_servers` is a discriminated union on `type`:

**HTTP transport:**

```jsonc
{
  "id": "github",
  "type": "http",
  "url": "https://mcp.example.com/github",
  "headers": { "Authorization": "Bearer ghp_..." }  // optional
}
```

**stdio transport:**

```jsonc
{
  "id": "fs",
  "type": "stdio",
  "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem"],
  "args": ["/workspace"],    // optional
  "env": { "HOME": "/tmp" }  // optional
}
```

- **`id`**: a string the supervisor chooses. Stable across the run. MUST match `^[a-z0-9_-]+$`.
- `headers` is optional. Pass auth and any other request headers directly (e.g. `"Authorization": "Bearer <token>"`).

### 3.2 Skill entries

Each entry in `skills` carries the full skill inline as a file map:

```jsonc
{
  "id": "code-runner",
  "files": {
    "SKILL.md": "---\nname: Code Runner\ndescription: …\n---\n# Code Runner\n…",
    "scripts/run.sh": "#!/bin/sh\n…"
  }
}
```

Keys in `files` are relative paths; values are file contents as UTF-8 strings. `files` MUST contain a `"SKILL.md"` entry. Additional paths (scripts, config, reference assets) are optional. `name` and `description` are declared in SKILL.md YAML frontmatter; agent SDKs SHOULD extract them from there rather than requiring duplicate top-level fields.

### 3.3 Asset-id collisions

The agent MUST detect the following at startup and fail with `error_occurred(code: "commission_collision")` followed by `agent_stopped(reason: "error")`:

- `Commission.mcp_servers[].id` matching `descriptor.mcp_servers[].id`.
- `Commission.skills[].id` matching `descriptor.skills[].name`.

These collisions are configuration errors; the supervisor referenced an id the agent already declares. Fail-fast surfaces the conflict before any model turn.

Tool-name collisions across distinct MCP servers (e.g. agent-internal `github_v1` and Commission-managed `github_v2` both exposing `list_prs`) are an agent-runtime concern outside AVP's wire. The agent's MCP client surfaces names to the model however it normally does.

---

## 4. Built-in surface allowlists

`Commission` carries four optional allowlists that gate which entries from the agent's [Descriptor](./agent-descriptor.md) surface to the model for the run:

| Field | Gates | Source of truth |
|---|---|---|
| `enabled_builtin_tools` | `descriptor.tools[].name` | The agent's [Agent Descriptor](./agent-descriptor.md) |
| `enabled_builtin_subagents` | `descriptor.subagents[].name` | The agent's [Agent Descriptor](./agent-descriptor.md) |
| `enabled_builtin_skills` | `descriptor.skills[].name` | The agent's [Agent Descriptor](./agent-descriptor.md) |
| `enabled_builtin_mcp_servers` | `descriptor.mcp_servers[].id` | The agent's [Agent Descriptor](./agent-descriptor.md) |

Semantics, identical across all four:

- **Absent (null)** → every descriptor entry of that kind is exposed (default; backwards-compatible).
- **`[]`** → none are exposed.
- **`[n1, n2, …]`** → only the listed names are exposed; the rest are hidden from the model and runtime-blocked if invoked.

**Subtractive-only over the descriptor.** These fields gate the *agent's own* declarations (the Descriptor). Supervisor-managed assets carried in `Commission.{mcp_servers,skills,subagents}` are always active by virtue of being present in the Commission, and are never affected by these allowlists. Tools surfaced post-handshake by a Commission-managed MCP server are similarly controlled by whether the supervisor declared the server.

**Effect on MCP-surfaced tools.** Descriptor `tools[]` is locally-dispatched only (see [agent-descriptor.md §2.3](./agent-descriptor.md)); MCP server tools are not duplicated there. Disabling an `mcp_servers` entry via `enabled_builtin_mcp_servers` prevents the agent from dialing it, so the tools that server would have surfaced never become available for the run. `enabled_builtin_tools` separately gates only the local catalog.

### 4.1 Validation at startup (MUST)

The agent MUST validate every name in each allowlist against the corresponding Descriptor list. Names that don't match emit `error_occurred` with `data["avp.error.code"]: "commission_collision"` and the agent stops with `reason: "error"` before any model turn. Fail-loud-on-drift: a Commission referencing a built-in the agent no longer ships is a contract violation; supervisors find out at startup, not via silent surface degradation.

### 4.2 Two-layer enforcement (MUST)

- **Visibility (primary).** When the agent constructs `agent_started.data.tools[]` / `data.subagents[]` / `data.skills[]` from its built-in surface, entries not in the allowlist MUST be omitted. The model literally doesn't see disabled built-ins.
- **Runtime block (defense in depth).** If the model invokes a built-in name that's been allow-listed out (hallucination, prompt injection from tool output, prior-context leakage), the agent MUST emit `tool_returned` (with `isError: true`) after `tool_invoked` (or `subagent_failed` after `subagent_invoked`) and not execute the built-in. The trajectory faithfully records the attempt.

### 4.3 Common patterns

- Read-only audit run → `enabled_builtin_tools: ["Read", "Glob", "Grep"]`
- No network egress → omit `WebFetch`, `WebSearch` from the tools list
- Pure delegation (force the model into managed assets) → `enabled_builtin_tools: []`

---

## 5. How Commission composes with the other specs

| Composes with | How |
|---|---|
| [Trajectory](./trajectory.md) | The Commission travels verbatim in `run_requested.data["avp.commission"]`. The trajectory's run-prelude rules (§2.1 of `trajectory.md`) describe how managed-ref resolution events fire before the first model turn. |
| [Agent Descriptor](./agent-descriptor.md) | The allowlists in §4 reference Descriptor-declared names. The agent MUST validate them against its own Descriptor at startup. |
| [Resolver API](./resolver.md) | The refs in `mcp_servers` / `skills` / `subagents` are dereferenced via `avp.resolve` at startup. Managed subagent invocations call `avp.spawn_subagent` on demand. |

A consumer that adopts only the Commission Spec gets a portable JSON document for declaring runs and a validator for it. Agents that consume Commissions adopt at least Trajectory in addition (to emit the run prelude); they adopt Resolver when their supervisor uses managed assets.

---

## 6. Conformance

A supervisor (or any Commission producer) is conforming to the Commission Spec if and only if:

1. Every Commission it emits validates against [`commission.schema.json`](./commission.schema.json).
2. `schema_version` equals `"0.1"`.
3. `run_id` is unique within the supervisor's namespace.
4. If `mcp_servers` / `skills` / `subagents` are non-empty, the supervisor stands up a resolver service per [`resolver.md`](./resolver.md) and configures `AVP_RESOLVER_URL` in the agent's environment.
5. Every name in `enabled_builtin_tools` / `enabled_builtin_subagents` / `enabled_builtin_skills` / `enabled_builtin_mcp_servers` matches a corresponding entry in the target agent's Descriptor (by `name` for tools/subagents/skills, by `id` for mcp_servers). When the supervisor cannot pre-validate against the Descriptor, the agent catches mismatches at startup and emits `error_occurred(code: "commission_collision")`.

An agent that consumes Commissions and composes with the Trajectory Spec MUST additionally enforce §3.1 (collisions) and §4 (allowlists) at startup; see the corresponding conformance criteria in [`trajectory.md`](./trajectory.md) §8 and the Resolver API's R1–R4 in [`resolver.md`](./resolver.md).
