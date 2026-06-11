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

When [Trajectory](./trajectory.md) is in scope, the Commission travels in the snapshot embedded in `run_requested.data["avp.commission"]`. When [Agent Descriptor](./agent-descriptor.md) is in scope, the optional `enabled_builtin_*` allowlists reference descriptor-declared names.

### 1.1 Non-goals

The Commission Spec explicitly does **not** define:

- **The event stream the agent emits.** What flows *back* to the supervisor → see [`trajectory.md`](./trajectory.md).
- **What agents declare about themselves.** Pre-flight self-description → see [`agent-descriptor.md`](./agent-descriptor.md).
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
  "model":         "anthropic/claude-sonnet-4-6",

  "provider": { "id": "anthropic", "credential": { "vault": "anthropic" } },

  "mcp_servers": [
    { "id": "github", "type": "http", "url": "https://mcp.example.com/github", "auth": { "vault": "github" } }
  ],
  "skills": [
    { "id": "style-guide", "files": { "SKILL.md": "---\nname: Style Guide\n---\n…" } },
    { "id": "code-runner", "files": { "SKILL.md": "---\nname: Code Runner\n---\n…", "scripts/run.sh": "#!/bin/sh\n…" } }
  ],
  "enabled_builtin_tools":       { "my-agent": ["Read", "Grep", "Glob"] },
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
| `model` | string | Canonical [models.dev](https://models.dev) slug `"<origin>/<model>"` (e.g. `"anthropic/claude-sonnet-4-6"`, `"openai/gpt-5"`). MUST match `^[^/]+/.+$`. The origin segment is the model's home namespace and the pricing key; it is independent of the storefront that serves the tokens (see `provider`, §2.3). Agents split off the origin to get the SDK-native model id and validate against their Descriptor's `supported_models`. |

### 2.2 Optional fields

| Field | Type | Notes |
|---|---|---|
| `supervisor` | `{ name: string, version?: string }` | Attribution for `run_requested`. When absent, the corresponding `avp.supervisor.*` fields on `run_requested` are omitted (absence is the canonical signal; the prior `"unknown"` placeholder is superseded). |
| `system_prompt` | string | The agent's system context. Overrides `descriptor.system_prompt` when both are set. |
| `provider` | `Provider \| null` | LLM routing override (which storefront serves `model`). Absent → the agent's native default. See §2.3. |
| `mcp_servers` | `Array<McpServerHttp \| McpServerStdio>` | Inline MCP server connection material, discriminated on `type`. See §3. |
| `skills` | `Array<Skill>` | Inline Agent Skills (SKILL.md content). See §3. |
| `enabled_builtin_tools` | `object<agent_name, string[]> \| null` | Per-agent allowlists over `descriptor.tools[].name`, keyed by `descriptor.agent_name`. See §4. |
| `enabled_builtin_subagents` | `object<agent_name, string[]> \| null` | Per-agent allowlists over `descriptor.subagents[].name`. See §4. |
| `enabled_builtin_skills` | `object<agent_name, string[]> \| null` | Per-agent allowlists over `descriptor.skills[].name`. See §4. |
| `enabled_builtin_mcp_servers` | `object<agent_name, string[]> \| null` | Per-agent allowlists over `descriptor.mcp_servers[].id`. Disabling a server prevents the agent from dialing it, so the tools that server would have surfaced are also unavailable for the run. See §4. |
| `agent_versions` | `object<agent_name, string> \| null` | Exact `descriptor.agent_version` pins per agent; mismatch fails fast with `unsupported_agent_version`. See §4.0. |
| `thread_id` | string | Free-form correlation id (multi-turn conversation, parent context, etc.). |
| `tags` | `string[]` | Free-form labels. |
| `meta` | `object` | Free-form key/value bag. |
| `output_schema` | `object \| null` | A JSON Schema the supervisor wants the agent's final output to validate against. Agents that don't support structured output ignore it. |

### 2.3 Provider routing

`provider` directs the agent at a specific LLM storefront. When absent, the
agent uses its **native default** (whatever its own environment configures).

```jsonc
{
  "id":         "openrouter",                         // protocol/auth family; MUST match ^[a-z0-9_-]+$
  "base_url":   "https://openrouter.ai/api/v1",        // optional endpoint override
  "credential": { "vault": "openrouter" }              // optional SecretRef (§2.4); never the value
}
```

The model's **origin** (the `model` slug's first segment) and the storefront
**`id`** are independent axes. `model: "openai/gpt-4o"` with
`provider.id: "openrouter"` reads as "OpenAI's gpt-4o, bought through
OpenRouter": the pricing key stays `openai/gpt-4o`, the tokens are bought from
OpenRouter.

`provider` is a **request, not a guarantee**. An agent that cannot speak the
requested provider's protocol (e.g. an Anthropic-protocol-only agent asked for
`id: "openrouter"`) MUST emit `error_occurred` and stop with `reason: "error"`,
never silently run on a different endpoint.

### 2.4 Secrets are references, never values

Credentials never appear on the wire. Both `provider.credential` and
`McpServerHttp.auth` carry a **`SecretRef`**: `{ "vault": "<handle>" }`, where
the handle MUST match `^[a-z0-9_-]+$`. The supervisor resolves the handle to
secret material out of band (env var, secrets file, credential broker) at run
time; the value MUST NOT appear in the Commission or in any trajectory event.

A conforming supervisor SHOULD resolve handles **outside the agent's reach** so
the agent can *use* a credential it can never *read*. How it does so is a
supervisor concern; the wire only requires that handles, not values, travel on
the Commission. Credentials MUST be carried as `auth` (a `SecretRef`), never
inlined into `McpServerHttp.headers` (which is for non-secret headers only).

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
  "auth": { "vault": "github" },           // optional SecretRef (§2.4); injected as a bearer credential
  "headers": { "X-Trace-Id": "abc" }       // optional; non-secret headers only
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
- `auth` is optional. A `SecretRef` (§2.4) the supervisor resolves and injects as the server's credential (a bearer `Authorization` header). Carry credentials here, not inline.
- `headers` is optional and is for **non-secret** request headers only. Carry the server's credential in `auth`, not here.

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

`Commission` carries four optional allowlist maps that gate which entries from the agent's [Descriptor](./agent-descriptor.md) surface to the model for the run. Each field is an object keyed by `descriptor.agent_name`, so one Commission carries an explicit list per agent it may run on; built-in names live in each agent's own namespace, and a flat list would inevitably name tools that don't exist on whichever other agent runs it.

| Field | Each list gates | Source of truth |
|---|---|---|
| `enabled_builtin_tools` | `descriptor.tools[].name` | The agent's [Agent Descriptor](./agent-descriptor.md) |
| `enabled_builtin_subagents` | `descriptor.subagents[].name` | The agent's [Agent Descriptor](./agent-descriptor.md) |
| `enabled_builtin_skills` | `descriptor.skills[].name` | The agent's [Agent Descriptor](./agent-descriptor.md) |
| `enabled_builtin_mcp_servers` | `descriptor.mcp_servers[].id` | The agent's [Agent Descriptor](./agent-descriptor.md) |

Semantics, identical across all four. The running agent looks up exactly its own `agent_name`; entries under other agents' keys are ignored:

- **Absent (null)** → every descriptor entry of that kind is exposed (default).
- **Map present, no key for the running agent** → `commission_collision` fail-fast (§4.1): the Commission filters this surface but was not authored for this agent. Running it anyway, unfiltered or guessed, would silently change the experiment.
- **`"<my agent_name>": []`** → none are exposed.
- **`"<my agent_name>": [n1, n2, …]`** → only the listed names are exposed; the rest are hidden from the model and runtime-blocked if invoked.

Names are exact; there is no pattern or wildcard matching. The allowlist is part of the run's definition, and the surface it produces is fully determined by the Commission plus the Descriptor.

### 4.0 Agent version pins (`agent_versions`)

`agent_versions` is an optional map keyed by `descriptor.agent_name` whose values are exact `descriptor.agent_version` strings: the agent builds this Commission was authored and validated against. The allowlist fail-fast catches renamed or removed names; a version pin additionally catches same-name surface drift (a tool that still exists but behaves differently in a newer build), pre-flight instead of via post-hoc trajectory comparison.

- **Absent (null), or map present with no key for the running agent** → no pin declared; the run proceeds. Note the asymmetry with the allowlists: an allowlist without the agent's key means "filtered, but not authored for this agent" (refuse); a pin map without its key just means nobody pinned this agent.
- **Key present and equal to the agent's `agent_version`** → the run proceeds.
- **Key present and different** → the agent MUST emit `error_occurred` with `data["avp.error.code"]: "unsupported_agent_version"` and stop with `reason: "error"` before any model turn.

Values are exact strings; there are no version ranges. A stale pin is a one-field fix, and a loud refusal beats every agent evaluating a range expression identically.

**Subtractive-only over the descriptor.** These fields gate the *agent's own* declarations (the Descriptor). Supervisor-managed assets carried in `Commission.{mcp_servers,skills}` are always active by virtue of being present in the Commission, and are never affected by these allowlists. Tools surfaced post-handshake by a Commission-managed MCP server are similarly controlled by whether the supervisor declared the server.

**Effect on MCP-surfaced tools.** Descriptor `tools[]` is locally-dispatched only (see [agent-descriptor.md §2.3](./agent-descriptor.md)); MCP server tools are not duplicated there. Disabling an `mcp_servers` entry via `enabled_builtin_mcp_servers` prevents the agent from dialing it, so the tools that server would have surfaced never become available for the run. `enabled_builtin_tools` separately gates only the local catalog.

### 4.1 Validation at startup (MUST)

For each allowlist map that is present, the agent MUST find its own `agent_name` among the keys, and MUST validate every name under that key against the corresponding Descriptor list. A missing key, or a name that doesn't match, emits `error_occurred` with `data["avp.error.code"]: "commission_collision"` and the agent stops with `reason: "error"` before any model turn. Fail-loud-on-drift: a Commission referencing a built-in the agent no longer ships, or filtered for agents this one isn't among, is a contract violation; supervisors find out at startup, not via silent surface degradation.

### 4.2 Two-layer enforcement (MUST)

- **Visibility (primary).** When the agent constructs `agent_started.data.tools[]` / `data.skills[]` from its built-in surface, entries not in the allowlist MUST be omitted. The model literally doesn't see disabled built-ins.
- **Runtime block (defense in depth).** If the model invokes a built-in name that's been allow-listed out (hallucination, prompt injection from tool output, prior-context leakage), the agent MUST emit `tool_returned` (with `isError: true`) after `tool_invoked` and not execute the built-in. The trajectory faithfully records the attempt.

### 4.3 Common patterns

- Read-only audit run → `enabled_builtin_tools: {"my-agent": ["Read", "Glob", "Grep"]}`
- No network egress → omit `WebFetch`, `WebSearch` from the agent's list
- Pure delegation (force the model into managed assets) → `enabled_builtin_tools: {"my-agent": []}`
- One commission, two agents → `enabled_builtin_tools: {"avp-claude-agent-sdk": ["Bash", "Read"], "goose": ["developer__shell"]}`

---

## 5. How Commission composes with the other specs

| Composes with | How |
|---|---|
| [Trajectory](./trajectory.md) | The Commission travels verbatim in `run_requested.data["avp.commission"]`. The trajectory's run-prelude records MCP connections and skill loads before the first model turn. |
| [Agent Descriptor](./agent-descriptor.md) | The allowlists in §4 reference Descriptor-declared names. The agent MUST validate them against its own Descriptor at startup. |

A consumer that adopts only the Commission Spec gets a portable JSON document for declaring runs and a validator for it. Agents that consume Commissions adopt at least Trajectory in addition (to emit the run prelude).

---

## 6. Conformance

A supervisor (or any Commission producer) is conforming to the Commission Spec if and only if:

1. Every Commission it emits validates against [`commission.schema.json`](./commission.schema.json).
2. `schema_version` equals `"0.1"`.
3. `run_id` is unique within the supervisor's namespace.
4. In each of `enabled_builtin_tools` / `enabled_builtin_subagents` / `enabled_builtin_skills` / `enabled_builtin_mcp_servers` that is present, the target agent's `agent_name` appears as a key, and every name under it matches a corresponding entry in that agent's Descriptor (by `name` for tools/subagents/skills, by `id` for mcp_servers). When the supervisor cannot pre-validate against the Descriptor, the agent catches mismatches (missing key or unknown name) at startup and emits `error_occurred(code: "commission_collision")`.
5. When `agent_versions` carries a key for the target agent, its value equals that agent's `descriptor.agent_version`; the agent catches mismatches at startup with `error_occurred(code: "unsupported_agent_version")` (§4.0).
6. `model` is a canonical `<origin>/<model>` slug (matches `^[^/]+/.+$`).
7. Credentials are carried only as `SecretRef` handles (`provider.credential`, `McpServerHttp.auth`); the resolved secret value MUST NOT appear in the Commission, in `run_requested.data["avp.commission"]`, or in any other trajectory event.

An agent that consumes Commissions and composes with the Trajectory Spec MUST additionally enforce §3.3 (collisions) and §4 (allowlists) at startup.
