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
| `model` | string | Provider-qualified model id (e.g., `"claude-sonnet-4-6"`, `"gpt-5"`). Agents validate against their Descriptor's `supported_models`. |

### 2.2 Optional fields

| Field | Type | Notes |
|---|---|---|
| `supervisor` | `{ name: string, version?: string }` | Attribution for `run_requested`. Agents emit `name="unknown"` when absent. |
| `system_prompt` | string | Prepended to the model's system context. |
| `mcp_servers` | `Array<{ id: string, ref: JsonValue }>` | Managed MCP server refs. See §3. |
| `skills` | `Array<{ id: string, ref: JsonValue }>` | Managed Agent Skill refs. See §3. |
| `subagents` | `Array<{ id: string, ref: JsonValue }>` | Managed subagent refs. See §3. |
| `enabled_builtin_tools` | `string[] \| null` | Allowlist over `descriptor.built_in_tools[].name`. See §4. |
| `enabled_builtin_subagents` | `string[] \| null` | Allowlist over `descriptor.built_in_subagents[].name`. See §4. |
| `enabled_builtin_skills` | `string[] \| null` | Allowlist over `descriptor.built_in_skills[].name`. See §4. |
| `thread_id` | string | Free-form correlation id (multi-turn conversation, parent context, etc.). |
| `tags` | `string[]` | Free-form labels. |
| `meta` | `object` | Free-form key/value bag. |
| `output_schema` | `object \| null` | A JSON Schema the supervisor wants the agent's final output to validate against. Agents that don't support structured output ignore it. |
| `resume` | `ResumeBlock \| null` | Set by the supervisor when re-dispatching a run after a mid-trajectory rescue (see [`trajectory.md`](./trajectory.md) §7.3, §7.5). Absent on fresh dispatches. Agents that ignore it degrade to cold-rescue semantics — they restart the conversation from `prompt` and re-execute any side-effecting tools. Agents that honor it pick up at `from_seq + 1`. Full shape in §2.3 below. |

### 2.3 `ResumeBlock`

Optional Commission field set by the supervisor when re-dispatching a rescued run. Carries everything the new runner needs to continue the trajectory without restarting from scratch.

```jsonc
{
  "from_seq":      <integer ≥ 0>,
  "replay_policy": "context_only" | "skip_completed",
  "context":       { "messages": [ {"role": "<string>", "content": "<string>"}, ... ] },
  "tool_cache":    [ ToolCacheEntry, ... ],
  "in_flight_tool_call": <InFlightToolCall | null>
}
```

| Field | Required | Notes |
|---|---|---|
| `from_seq` | yes | The rescued runner MUST NOT emit any event with `seq <= from_seq`. Equal to the highest `seq` the supervisor persisted before the rescue. |
| `replay_policy` | yes | `context_only` (default — runner seeds its model call with `context.messages`, no other enforcement) or `skip_completed` (stricter: runner asserts every emitted event has `seq > from_seq`). |
| `context.messages` | yes | Reconstructed conversation messages in chronological order. Each entry is `{role, content}` where `role ∈ {"system","user","assistant","tool"}`. The runner SHOULD use this as the seed for its model call rather than rebuilding from `prompt`. |
| `tool_cache` | yes | List of prior tool invocations. The runner matches its model-emitted `tool_invoked` events against entries by `tool_name + canonical-equal args`. On match: emit `tool_returned` (or `tool_failed`) from the cache instead of dispatching to the tool. |
| `in_flight_tool_call` | optional | The most recent `tool_invoked` from the prior runner that had no matching `tool_returned` / `tool_failed`. v0.1 is informational: the runner sees it and decides whether to re-invoke or skip. |

#### `ToolCacheEntry`

```jsonc
{
  "tool_name":        "<string>",
  "args":             <JsonValue>,        // canonical form (whitespace + key-order normalized)
  "result":           <JsonValue | null>, // present iff the original tool_invoked produced a tool_returned
  "failure":          <{message: string, code?: string} | null>, // present iff produced tool_failed
  "tier":             "idempotent" | "replay_only" | "needs_approval",
  "original_span_id": "<string>"
}
```

`tier` governs cache-miss behavior (the model invokes a tool whose `tool_name + args` *doesn't* match any cache entry):

| Tier | On cache miss |
|---|---|
| `idempotent` | Re-execute the tool. Safe for reads / deterministic transforms. |
| `replay_only` | Emit `tool_failed` with `code: "replay_required_cache_missed"`. The model sees the failure and adapts. **Default for unclassified tools.** |
| `needs_approval` | Block on the existing `approval_requested` RPC before re-executing. Human-in-the-loop. |

#### `InFlightToolCall`

```jsonc
{
  "tool_name":   "<string>",
  "args":        <JsonValue>,
  "span_id":     "<string>",   // original tool_invoked's span_id
  "invoked_at":  "<ISO 8601>"
}
```

### 2.4 Determinism contract for rescued runners

A conforming runner that receives a Commission with `resume` set:

1. MUST NOT emit any event whose `seq <= resume.from_seq`.
2. MUST skip the prelude (`avp.run_requested`, `avp.agent_described`, `avp.agent_started`) — those events already exist in the trajectory from the prior runner. The new runner inherits the agent span opened by the original `agent_started` (see [`trajectory.md`](./trajectory.md) §7.3).
3. MUST seed its model call with `resume.context.messages` rather than rebuilding the conversation from `prompt` alone.
4. When the model emits a `tool_invoked` that matches a `resume.tool_cache[N]` by `tool_name + canonical-equal args`, the runner MUST emit `tool_returned` (or `tool_failed`) with the cached payload rather than dispatching to the tool.
5. Cache-miss behavior is governed by the tier (see `ToolCacheEntry.tier` above).
6. The new runner SHOULD attempt to resume `resume.in_flight_tool_call` if present, but v0.1 treats it as informational — the runner MAY re-invoke or skip.

Runners that don't implement this contract degrade gracefully to cold rescue: they restart the conversation, re-fire any side-effecting tools, and the rescue still completes — just with the user-visible problems that warm rescue exists to solve.

---

## 3. Managed assets (refs only)

`mcp_servers`, `skills`, and `subagents` carry **only opaque refs** in v0.1. Each entry is:

```jsonc
{ "id": "<stable identifier the supervisor picked>", "ref": <JsonValue> }
```

- **`id`**: a string the supervisor chooses. Becomes the model-facing name once resolved (or the resolver MAY override via its `name` field for `subagent` / `skill` results). Stable across the run.
- **`ref`**: an arbitrary JSON value the supervisor's resolver service understands. Strings, objects, arrays, numbers, booleans, and `null` are all legal. The agent MUST NOT inspect `ref`; it passes the value verbatim to the resolver.

The Commission carries **no inline connection material**: no URLs, no auth tokens, no SKILL.md bodies, no subagent system prompts. All of that arrives via the [Resolver API](./resolver.md) at startup. This keeps the Commission auditable without secret redaction.

If a Commission carries any non-empty asset list, the agent MUST be configured with a reachable resolver service (the `AVP_RESOLVER_URL` env var); see [`resolver.md`](./resolver.md) §2. The Trajectory Spec's run-prelude rules (§2.2 of [`trajectory.md`](./trajectory.md)) describe the resolution events that fire before the first model turn.

### 3.1 Asset-id collisions

The agent MUST detect the following at startup and fail with `error_occurred(code: "commission_collision")` followed by `agent_stopped(reason: "error")`:

- `Commission.subagents[].id` matching a Descriptor-declared `built_in_tools[].name`.
- `Commission.subagents[].id` matching a Descriptor-declared `built_in_subagents[].name`.
- `Commission.mcp_servers[].id` matching a Descriptor-declared `built_in_subagents[].name`.

These collisions are configuration errors; the supervisor referenced an id the agent reserves. Fail-fast surfaces the conflict before any model turn.

Tool-name collisions across distinct MCP servers (e.g. agent-internal `github_v1` and Commission-managed `github_v2` both exposing `list_prs`) are an agent-runtime concern outside AVP's wire. The agent's MCP client surfaces names to the model however it normally does.

---

## 4. Built-in surface allowlists

`Commission` carries three optional allowlists that gate which agent **built-ins** surface to the model for the run:

| Field | Gates | Source of truth |
|---|---|---|
| `enabled_builtin_tools` | `descriptor.built_in_tools[].name` | The agent's [Agent Descriptor](./agent-descriptor.md) |
| `enabled_builtin_subagents` | `descriptor.built_in_subagents[].name` | The agent's [Agent Descriptor](./agent-descriptor.md) |
| `enabled_builtin_skills` | `descriptor.built_in_skills[].name` | The agent's [Agent Descriptor](./agent-descriptor.md) |

Semantics, identical across all three:

- **Absent (null)** → every built-in of that kind is exposed (default; backwards-compatible).
- **`[]`** → no built-in of that kind is exposed.
- **`[n1, n2, …]`** → only the listed names are exposed; the rest are hidden from the model and runtime-blocked if invoked.

These fields gate **agent built-ins only**. Supervisor-managed assets (`mcp_servers`, `skills`, `subagents` refs) are gated by their presence/absence in the Commission and are never affected. Tools surfaced post-handshake by a managed MCP server are controlled by which MCP server the supervisor declared.

### 4.1 Validation at startup (MUST)

The agent MUST validate every name in each allowlist against the corresponding Descriptor list. Names that don't match emit `error_occurred` with `data["avp.error.code"]: "commission_collision"` and the agent stops with `reason: "error"` before any model turn. Fail-loud-on-drift: a Commission referencing a built-in the agent no longer ships is a contract violation; supervisors find out at startup, not via silent surface degradation.

### 4.2 Two-layer enforcement (MUST)

- **Visibility (primary).** When the agent constructs `agent_started.data.tools[]` / `data.subagents[]` / `data.skills[]` from its built-in surface, entries not in the allowlist MUST be omitted. The model literally doesn't see disabled built-ins.
- **Runtime block (defense in depth).** If the model invokes a built-in name that's been allow-listed out (hallucination, prompt injection from tool output, prior-context leakage), the agent MUST emit `tool_failed` (or `subagent_failed`) after `tool_invoked` (or `subagent_invoked`) and not execute the built-in. The trajectory faithfully records the attempt.

### 4.3 Common patterns

- Read-only audit run → `enabled_builtin_tools: ["Read", "Glob", "Grep"]`
- No network egress → omit `WebFetch`, `WebSearch` from the tools list
- Pure delegation (force the model into managed assets) → `enabled_builtin_tools: []`

---

## 5. How Commission composes with the other sub-specs

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
5. Every name in `enabled_builtin_tools` / `enabled_builtin_subagents` / `enabled_builtin_skills` matches a corresponding entry in the target agent's Descriptor. (When the supervisor cannot pre-validate against the Descriptor, the agent will catch mismatches at startup and emit `error_occurred(code: "commission_collision")`.)

An agent that consumes Commissions and composes with the Trajectory Spec MUST additionally enforce §3.1 (collisions) and §4 (allowlists) at startup; see the corresponding conformance criteria in [`trajectory.md`](./trajectory.md) §8 and the Resolver API's R1–R4 in [`resolver.md`](./resolver.md).
