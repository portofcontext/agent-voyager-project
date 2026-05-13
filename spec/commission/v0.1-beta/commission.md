# AVP Commission Spec, v0.1-beta

**Status:** Beta
**Stability:** JSON shape, ref model, and allowlist semantics are stable in the reference implementation; breaking changes possible before promotion to Stable.
**Schema:** [`commission.schema.json`](./commission.schema.json)
**$id:** `https://raw.githubusercontent.com/portofcontext/agent-voyager-project/main/spec/commission/v0.1-beta/commission.schema.json`

## 1. Scope

The Commission Spec defines the **run-config object** a supervisor hands an agent at startup. It is a data-shape spec; no wire-level protocol.

A Commission can be sent over stdio or HTTP to an agent that will execute it (composes with [Trajectory](../../trajectory/v0.1/trajectory.md)), validated or rendered by tooling that never runs the agent loop (Commission alone), or embedded in audit records.

When Trajectory is in scope, the Commission travels verbatim in `run_requested.data["avp.commission"]`. When [Resolver API](../../resolver/v0.1-beta/resolver.md) is in scope, the refs in `mcp_servers` / `skills` / `subagents` are what the protocol dereferences. When [Agent Descriptor](../../agent-descriptor/v0.1/agent-descriptor.md) is in scope, the optional `enabled_builtin_*` allowlists reference descriptor-declared names.

## 2. The Commission shape

```jsonc
{
  "schema_version": "0.1",
  "run_id": "auth-refactor-20260502-abc123",

  "supervisor": { "name": "acme-engineering-supervisor", "version": "2.4.1" },

  "prompt":        "Refactor the auth module to use JWT.",
  "system_prompt": "You are a senior Rust developer.",
  "model":         "claude-sonnet-4-6",

  "mcp_servers": [
    { "id": "github", "ref": { "vault": "prod", "key": "gh-mcp-v2" } }
  ],
  "skills": [
    { "id": "style-guide",     "ref": "sha256:abc..." },
    { "id": "domain-glossary", "ref": { "vault": "prod", "key": "skill-glossary-v2" } }
  ],
  "subagents": [
    { "id": "researcher", "ref": "sk_subagent_abc123" }
  ],

  "enabled_builtin_tools":     ["Read", "Grep", "Glob"],
  "enabled_builtin_subagents": null,
  "enabled_builtin_skills":    null,

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
| `model` | string | Provider-qualified model id (e.g., `"claude-sonnet-4-6"`, `"gpt-5"`). Validated against the Descriptor's `supported_models`. |

### 2.2 Optional fields

| Field | Type | Notes |
|---|---|---|
| `supervisor` | `{ name: string, version?: string }` | Attribution for `run_requested`. Agents emit `name="unknown"` when absent. |
| `system_prompt` | string | Prepended to the model's system context. |
| `mcp_servers` | `Array<{ id, ref }>` | Managed MCP server refs. See §3. |
| `skills` | `Array<{ id, ref }>` | Managed Agent Skill refs. See §3. |
| `subagents` | `Array<{ id, ref }>` | Managed subagent refs. See §3. |
| `enabled_builtin_tools` | `string[] \| null` | Allowlist over `descriptor.built_in_tools[].name`. See §4. |
| `enabled_builtin_subagents` | `string[] \| null` | Allowlist over `descriptor.built_in_subagents[].name`. See §4. |
| `enabled_builtin_skills` | `string[] \| null` | Allowlist over `descriptor.built_in_skills[].name`. See §4. |
| `thread_id` | string | Free-form correlation id. |
| `tags` | `string[]` | Free-form labels. |
| `meta` | `object` | Free-form key/value bag. |
| `output_schema` | `object \| null` | JSON Schema the supervisor wants the agent's final output to validate against. Agents that don't support structured output ignore it. |

## 3. Managed assets (refs only)

`mcp_servers`, `skills`, and `subagents` carry **only opaque refs**. Each entry is:

```jsonc
{ "id": "<stable identifier the supervisor picked>", "ref": <JsonValue> }
```

- **`id`**: a string the supervisor chooses. Becomes the model-facing name once resolved (or the resolver MAY override via its `name` field for `subagent` / `skill` results). Stable across the run.
- **`ref`**: an arbitrary JSON value the supervisor's resolver service understands. Strings, objects, arrays, numbers, booleans, and `null` are all legal. The agent MUST NOT inspect `ref`; it passes the value verbatim to the resolver.

The Commission carries **no inline connection material**: no URLs, no auth tokens, no SKILL.md bodies, no subagent system prompts. All of that arrives via the Resolver API at startup. This keeps the Commission auditable without secret redaction.

If a Commission carries any non-empty asset list, the agent MUST be configured with a reachable resolver service (the `AVP_RESOLVER_URL` env var).

### 3.1 Asset-id collisions

The agent MUST detect the following at startup and fail with `error_occurred(code: "commission_collision")` followed by `agent_stopped(reason: "error")`:

- `Commission.subagents[].id` matching a Descriptor-declared `built_in_tools[].name`.
- `Commission.subagents[].id` matching a Descriptor-declared `built_in_subagents[].name`.
- `Commission.mcp_servers[].id` matching a Descriptor-declared `built_in_subagents[].name`.

Tool-name collisions across distinct MCP servers (e.g. agent-internal `github_v1` and Commission-managed `github_v2` both exposing `list_prs`) are an agent-runtime concern outside AVP's wire.

## 4. Built-in surface allowlists

Three optional allowlists gate which agent **built-ins** surface to the model for the run:

| Field | Gates | Source of truth |
|---|---|---|
| `enabled_builtin_tools` | `descriptor.built_in_tools[].name` | Agent Descriptor |
| `enabled_builtin_subagents` | `descriptor.built_in_subagents[].name` | Agent Descriptor |
| `enabled_builtin_skills` | `descriptor.built_in_skills[].name` | Agent Descriptor |

Semantics, identical across all three:

- **Absent (null)** → every built-in of that kind is exposed (default).
- **`[]`** → no built-in of that kind is exposed.
- **`[n1, n2, …]`** → only the listed names are exposed; the rest are hidden from the model and runtime-blocked if invoked.

These fields gate **agent built-ins only**. Supervisor-managed assets (`mcp_servers`, `skills`, `subagents` refs) are gated by their presence/absence in the Commission and are never affected.

### 4.1 Validation at startup (MUST)

The agent MUST validate every name in each allowlist against the corresponding Descriptor list. Names that don't match emit `error_occurred` with `data["avp.error.code"]: "commission_collision"` and the agent stops with `reason: "error"` before any model turn. Fail-loud-on-drift: a Commission referencing a built-in the agent no longer ships is a contract violation.

### 4.2 Two-layer enforcement (MUST)

- **Visibility (primary).** When the agent constructs `agent_started.data.tools[]` / `data.subagents[]` / `data.skills[]`, entries not in the allowlist MUST be omitted. The model literally doesn't see disabled built-ins.
- **Runtime block (defense in depth).** If the model invokes an allow-listed-out built-in (hallucination, prompt injection, prior-context leakage), the agent MUST emit `tool_failed` (or `subagent_failed`) after `tool_invoked` (or `subagent_invoked`) and not execute the built-in.

## 5. Conformance

A supervisor (or any Commission producer) is conforming if and only if:

1. Every Commission it emits validates against [`commission.schema.json`](./commission.schema.json).
2. `schema_version` equals `"0.1"`.
3. `run_id` is unique within the supervisor's namespace.
4. If `mcp_servers` / `skills` / `subagents` are non-empty, the supervisor stands up a resolver service and configures `AVP_RESOLVER_URL` in the agent's environment.
5. Every name in `enabled_builtin_*` matches a corresponding entry in the target agent's Descriptor. (When pre-validation isn't possible, the agent catches mismatches at startup and emits `error_occurred(code: "commission_collision")`.)

An agent that consumes Commissions and composes with Trajectory MUST additionally enforce §3.1 (collisions) and §4 (allowlists) at startup.
