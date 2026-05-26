# AVP Agent Descriptor Spec, v0.1

**Status:** Draft
**Stability:** alpha. JSON shape works for the reference agents but is newer than Trajectory / Commission; capabilities vocabulary and field set may still change.
**Umbrella version:** v0.1 (see [`README.md`](./README.md))
**Schema:** [`agent-descriptor.schema.json`](./agent-descriptor.schema.json)
**$id base:** `https://avp.dev/schema/v0.1/`

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

---

## 1. Scope

The Agent Descriptor Spec defines an agent's **self-description**: the static surface the agent ships with — identity, capabilities, supported models, system prompt, baked-in user prompt (for autonomous agents), MCP servers, tools, skills, subagents. Everything on the descriptor is *what's in the agent*, regardless of whether it came from an SDK preset (`Grep`), a runtime-bundled skill, or hard-coded in the agent's own source. Provenance inside the agent doesn't matter on the wire; the agent's contribution is uniform from the outside.

It is a data-shape spec: it specifies the JSON object's structure, but no wire-level protocol.

An Agent Descriptor can be:

- Printed to stdout by a `<agent> describe` command for pre-flight introspection (Descriptor alone, useful for agent catalogs and discovery surfaces).
- Carried on the wire as part of [Trajectory](./trajectory.md)'s `agent_described` event so the trajectory is a complete record of the agent that ran (composes with Trajectory).
- Combined at startup with a [Commission](./commission.md): the supervisor's contribution (additional MCP servers, skills, subagents — by ref) is merged with the descriptor's by id/name; collisions fail-fast (see §2.7).

The pre-flight and run-time views SHOULD be consistent: `<agent> describe` SHOULD emit the same payload `agent_described.data["avp.descriptor"]` carries for the same agent build. The relaxation from a strict MUST: pre-flight `describe` MAY omit MCP-surfaced tool entries (those whose `avp.mcp_server_id` is set), since populating them requires dialing the agent's MCP servers and running `tools/list` — work the agent only needs to do at run-time. Every other Descriptor field MUST be identical between the two views.

### 1.1 Non-goals

The Agent Descriptor Spec explicitly does **not** define:

- **Per-invocation overrides.** The Descriptor is *substantially static* — identical bytes across runs of the same build, with one carve-out: MCP-surfaced tool entries in `tools[]` are populated from each server's `tools/list` at startup, so they can vary if the server's catalog changes. The [Commission](./commission.md) carries what varies per invocation: per-call prompt, run_id, thread_id, tags, additional managed assets the supervisor wants to add. Anything that varies between runs belongs on the Commission, not the Descriptor.
- **The event stream.** Run-time fact emission → see [`trajectory.md`](./trajectory.md).
- **Discovery / publication mechanism.** v0.1 descriptors are local; `<agent> describe` prints to stdout. No registry, no network discovery protocol. A future spec MAY define one.
- **Capability negotiation.** A supervisor reads the Descriptor and decides whether to commission the agent. There is no back-and-forth negotiation on the wire.
- **Versioning of individual built-ins.** v0.1 has no notion of "this tool changed semantics between agent versions"; that's deferred. Bumps to `agent_version` are the granularity supervisors get.

---

## 2. The Agent Descriptor shape

An Agent Descriptor is a single JSON document validating against [`agent-descriptor.schema.json`](./agent-descriptor.schema.json):

```jsonc
{
  "agent_name":       "avp-claude-agent-sdk",
  "agent_version":    "0.1.0",
  "avp_spec_version": "0.1",

  "default_model":    null,
  "supported_models": ["claude-*"],

  "system_prompt":    null,
  "prompt":           null,

  "mcp_servers": null,

  "tools": [
    { "name": "Read"  },
    { "name": "Write" },
    { "name": "Bash"  }
  ],

  "subagents": [
    { "name": "general-purpose", "avp.agent_type": "general-purpose" }
  ],

  "skills": null,

  "capabilities": [
    "skills:progressive",
    "thinking",
    "filesystem-discovery-available"
  ]
}
```

An autonomous helpdesk agent with a fixed persona, an internal MCP server, and a baked-in user prompt:

```jsonc
{
  "agent_name":       "acme-helpdesk-agent",
  "agent_version":    "1.4.0",
  "avp_spec_version": "0.1",

  "system_prompt": "You are a helpdesk agent for ACME Corp. ...",
  "prompt":        "Pull today's open tickets and triage them.",

  "mcp_servers": [
    { "id": "acme_kb", "description": "ACME internal knowledge base" }
  ],
  "tools":     null,
  "skills":    [ { "name": "triage" } ],
  "subagents": null,

  "capabilities": []
}
```

### 2.1 Required fields

| Field | Type | Notes |
|---|---|---|
| `agent_name` | string | The agent's package / binary name (e.g., `"avp-claude-agent-sdk"`). Stable across versions. |
| `agent_version` | string | Semver-compatible. Bumped on any wire-affecting change. |
| `avp_spec_version` | string | The AVP umbrella version the agent conforms to (`"0.1"` for this spec). |

### 2.2 Optional fields

`null` and absent are equivalent for the optional fields below; agents SHOULD prefer explicit `null` for the list-valued fields when they have no entries (so the wire records the intentional empty surface).

| Field | Type | Notes |
|---|---|---|
| `default_model` | `string \| null` | The model the agent picks when `Commission.model` is absent. `null` = no default; the Commission MUST specify. |
| `supported_models` | `string[] \| null` | Glob patterns the agent's `Commission.model` validates against (e.g., `["claude-*"]`). `null` = no constraint. Mismatch at startup → `error_occurred(code: "unsupported_model")`. |
| `system_prompt` | `string \| null` | A system prompt the agent ships with. Commission's `system_prompt` overrides if both are set; see §2.7. |
| `prompt` | `string \| null` | A baked-in user prompt for autonomous agents (e.g., cron-style runs with no per-call user message). Commission's `prompt` overrides if both are set; see §2.7. |
| `mcp_servers` | `Array<McpServer> \| null` | MCP servers the agent dials at startup. The descriptor records only the server's identity — connection material (URLs, auth, command-lines) stays inside the agent process. See §2.6. |
| `tools` | `Array<Tool> \| null` | The agent's full tool catalog: local tools (code compiled into the agent package, including provider-hosted tools the SDK wires) AND MCP-surfaced tools sourced from each entry in `mcp_servers[]` at startup. MCP-surfaced entries carry `avp.mcp_server_id`; local entries omit it. See §2.3. |
| `subagents` | `Array<Subagent> \| null` | Subagent delegates the agent ships with. See §2.4. |
| `skills` | `Array<Skill> \| null` | Skills the agent ships with. See §2.5. |
| `capabilities` | `string[] \| null` | See §3. |

### 2.3 Tool

Each entry in `tools[]` is a tool the agent can dispatch — either **locally** (code compiled into the agent package, including provider-hosted tools (Anthropic `web_search`, `code_execution`, etc.) that the agent's SDK wires) or via an **MCP server** (an entry in `mcp_servers[]` that the agent dials at startup). Dispatch is discriminated by the optional `avp.mcp_server_id` field on each entry: local entries omit it; MCP-surfaced entries set it to the `id` of the source server in `mcp_servers[]`.

```jsonc
// Local tool: no avp.mcp_server_id.
{
  "name": "Read",
  "description": "Read a file from disk.",         // optional
  "inputSchema": { /* MCP-shaped JSON Schema */ }  // optional
}

// MCP-surfaced tool: avp.mcp_server_id points at an entry in mcp_servers[].
{
  "name": "kb_search",
  "description": "Search the ACME knowledge base.",
  "inputSchema": { /* ... */ },
  "avp.mcp_server_id": "acme_kb"
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Model-facing tool name. Stable across versions. Unique within `tools[]`. |
| `description` | string | Optional. Human/model description. |
| `inputSchema` | object | Optional. JSON Schema for the tool's input, in MCP's `inputSchema` shape (camelCase). |
| `avp.mcp_server_id` | string | Optional. When set, the tool is dispatched via the MCP server with that `id` in `mcp_servers[]`. When absent, the tool is dispatched locally in the agent's process. |

The per-invocation discriminator `avp.tool.dispatch_target` (`"local"` / `"mcp_server"`) lives on each `tool_invoked` event and mirrors the presence or absence of `avp.mcp_server_id` on the decl.

### 2.4 Subagent

Each entry in `subagents[]`:

```jsonc
{
  "name": "general-purpose",
  "description": "General-purpose subagent for multi-step research.", // optional
  "inputSchema": { /* ... */ },                                       // optional
  "avp.agent_type": "general-purpose"                                 // optional
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Model-facing subagent name. Unique within `subagents[]`. |
| `description` | string | Optional. |
| `inputSchema` | object | Optional. JSON Schema for the subagent's invocation input. |
| `avp.agent_type` | string | Optional. Agent-specific identifier (e.g., Claude Agent SDK's `agent_type`). |

### 2.5 Skill

Each entry in `skills[]`:

```jsonc
{
  "name": "auth-checklist",
  "description": "Checklist for auth changes.",  // optional
  "version": "1.0"                               // optional
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Skill name (matches SKILL.md frontmatter `name`). Unique within `skills[]`. |
| `description` | string | Optional. |
| `version` | string | Optional. The skill's own version. |

### 2.6 McpServer

Each entry in `mcp_servers[]`:

```jsonc
{
  "id": "acme_kb",
  "name": "ACME KB",                              // optional
  "description": "ACME internal knowledge base",  // optional
  "status": "connected"                           // optional; pre-flight describe MAY omit
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string | Server identifier. Stable across versions. Unique within `mcp_servers[]`. Tools sourced from this server appear in `tools[]` with `avp.mcp_server_id` matching this `id`. |
| `name` | string | Optional. Display name when distinct from `id`. |
| `description` | string | Optional. Human-readable summary. |
| `status` | string | Optional. Terminal dial state at startup: one of `"connected"`, `"failed"`, `"needs-auth"`, `"pending"`, `"disabled"`. Pre-flight `<agent> describe` MAY omit it (no dial has happened); on-the-wire `agent_described` and `agent_started.data["avp.mcp_servers"]` populate it after startup. Only `"connected"` servers contribute tools to `tools[]`. |

**Connection material is not on the wire.** The agent dials its MCP servers using configuration internal to its build — URLs, auth, command-lines stay in the agent's process. The descriptor records only what the supervisor / auditor needs to see: the server's identity and its terminal dial status. The tools the server surfaces are enumerated in `tools[]` with `avp.mcp_server_id` set to this server's `id`.

### 2.7 Merge with Commission

When a [Commission](./commission.md) is in play at run time, descriptor entries and Commission entries combine at startup. The merged state is what `agent_started.data` records (per [trajectory.md §2.1](./trajectory.md)).

**Prompt-shaped fields (`system_prompt`, `prompt`):** Commission's value overrides the descriptor's if both are set; if only one is set, that one applies.

**List-shaped fields (`mcp_servers`, `skills`, `subagents`):** the effective set for the run is

```
(descriptor.<field> filtered by Commission.enabled_builtin_<field>) ∪ Commission.<field>
```

- `Commission.enabled_builtin_*` is **subtractive-only over the descriptor**. It never enables a Commission-supplied asset; those are always active by virtue of being present in the Commission.
- Descriptor entries are agent-internal. Commission entries carry inline connection material and are always active by virtue of being present.
- An id/name collision between a descriptor entry and a Commission entry MUST emit `error_occurred(code: "commission_collision")` and `agent_stopped(reason: "error")` before any model turn. Specifically: `descriptor.mcp_servers[].id` vs `Commission.mcp_servers[].id`; `descriptor.skills[].name` vs `Commission.skills[].id`.
- A name in `Commission.enabled_builtin_*` that doesn't appear in the corresponding `descriptor.*` field is the same `commission_collision`.

**Tools:** the effective `agent_started.data["avp.tools"]` for the run is `descriptor.tools` (filtered for entries without `avp.mcp_server_id` against `Commission.enabled_builtin_tools`), unioned with the live `tools/list` output from each MCP server whose dial reached `status: "connected"` — descriptor-internal servers post-`enabled_builtin_mcp_servers` filter, plus all `Commission.mcp_servers`. Disabling a server via `Commission.enabled_builtin_mcp_servers` prevents the dial, so its tools never become available for the run; a Commission-declared server that fails to dial still appears in `mcp_servers[]` with its terminal `status`, but contributes no tools.

---

## 3. Capabilities

`capabilities[]` is a flat array of strings. Each string is a **capability flag** that varies between AVP agents and is meaningful to Commission-aware tooling (e.g., "skip this Commission if the agent doesn't support thinking blocks"). The vocabulary is open; AVP defines well-known flags but does not constrain the set.

### 3.1 Well-known capability flags (v0.1)

| Flag | Meaning |
|---|---|
| `thinking` | The agent parses and emits provider-side extended-thinking blocks (Anthropic thinking, o-series reasoning) as `reasoning_emitted` events. |
| `skills:eager` | The agent injects resolved SKILL.md bodies into the model's context at startup. `skill_loaded` fires once per skill, `step=0`. See [`trajectory.md`](./trajectory.md) §6. |
| `skills:progressive` | The agent's SDK loads skill bodies on demand per turn (progressive disclosure). `skill_loaded` fires when the body actually enters context, with `step=N`. |
| `filesystem-discovery-available` | The agent's SDK *can* auto-discover skills / subagents from local filesystem paths (e.g., `~/.claude/skills/`, `.claude/agents/`). Informational disclosure; actual behavior is controlled by SDK-level configuration the supervisor sets. |

Implementations MAY publish additional vendor-namespaced flags (e.g., `vendor.acme.fast-mode`). Consumers MUST ignore flags they don't recognize.

---

## 4. How Agent Descriptor composes with the other specs

| Composes with | How |
|---|---|
| [Trajectory](./trajectory.md) | The Descriptor payload is the body of `agent_described.data["avp.descriptor"]`. The pre-flight `describe` surface and the run-time `agent_described` event SHOULD be consistent for the same agent build; pre-flight describe MAY omit MCP-surfaced tool entries (those whose `avp.mcp_server_id` is set), which require a startup dial. |
| [Commission](./commission.md) | Commission's `enabled_builtin_*` allow-lists reference Descriptor-declared `name`/`id`s (subtractive-only over the descriptor). Prompt-shaped fields override per §2.7; list-shaped fields merge as `(descriptor filtered by enabled_builtin_*) ∪ Commission` with id-collision = `commission_collision` fail-fast. |

A consumer that adopts only the Agent Descriptor Spec can run an agent's `describe` command and ingest the result for catalog/discovery purposes without ever sending a Commission or reading a trajectory.

---

## 5. Conformance

An agent (or any Descriptor publisher) is conforming to the Agent Descriptor Spec if and only if:

1. Every Descriptor it emits validates against [`agent-descriptor.schema.json`](./agent-descriptor.schema.json).
2. `avp_spec_version` equals `"0.1"`.
3. The Descriptor's **static portion** (every field except MCP-surfaced `tools[]` entries and `mcp_servers[].status`) MUST be identical across runs of the same build. No environment reads, no filesystem walks, no random ids in the static portion. MCP-surfaced `tools[]` entries (those with `avp.mcp_server_id`) and per-server `status` are populated from each MCP server's startup `tools/list` and may legitimately vary if the server's catalog changes.
4. Within each list-valued field, identifiers are unique: `tools[].name`, `subagents[].name`, `skills[].name`, `mcp_servers[].id`.
5. Every `tools[]` entry with `avp.mcp_server_id` set MUST match an `id` in `mcp_servers[]`. Conversely, an MCP server whose `status` is anything other than `"connected"` MUST NOT have any `tools[]` entries carrying its `id`.
6. If composed with [Trajectory](./trajectory.md): `agent_described.data["avp.descriptor"]` SHOULD be consistent with what `<agent> describe` prints for the same build. Pre-flight describe MAY omit MCP-surfaced tool entries; every other field MUST be identical.
7. If composed with [Commission](./commission.md): descriptor entries and Commission entries merge per §2.7 — prompt-shaped fields are overridden by Commission; list-shaped fields are unioned (descriptor side filtered by `enabled_builtin_*` first). An id/name collision across descriptor and Commission MUST emit `error_occurred(code: "commission_collision")` and `agent_stopped(reason: "error")` before any model turn.
