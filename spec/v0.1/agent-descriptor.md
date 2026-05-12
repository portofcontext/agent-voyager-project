# AVP Agent Descriptor Spec, v0.1

**Status:** Draft
**Stability:** alpha. JSON shape works for the reference agents but is newer than Trajectory / Commission; capabilities vocabulary and field set may still change.
**Umbrella version:** v0.1 (see [`README.md`](./README.md))
**Schema:** [`agent-descriptor.schema.json`](./agent-descriptor.schema.json)
**$id base:** `https://avp.dev/schema/v0.1/`

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

---

## 1. Scope

The Agent Descriptor Spec defines an agent's **self-description**: the catalog of built-in tools, subagents, and skills the agent can run without supervisor configuration, plus its identity, capabilities, and supported models. It is a data-shape spec: it specifies the JSON object's structure, but no wire-level protocol.

An Agent Descriptor can be:

- Printed to stdout by a `<agent> describe` command for pre-flight introspection (Descriptor alone, useful for agent catalogs and discovery surfaces).
- Carried on the wire as part of [Trajectory](./trajectory.md)'s `agent_described` event so the trajectory is a complete record of the agent that ran (composes with Trajectory).
- Validated by tooling that compares declared `enabled_builtin_*` names from a [Commission](./commission.md) against a target agent's surface (composes with Commission).

The pre-flight and run-time views are normatively the same payload: `<agent> describe` MUST emit exactly what `agent_described.data["avp.descriptor"]` carries for the same agent build.

### 1.1 Non-goals

The Agent Descriptor Spec explicitly does **not** define:

- **Run configuration.** The Descriptor describes what the agent *can* do; the Commission describes what the agent *should* do this run → see [`commission.md`](./commission.md).
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

  "built_in_tools": [
    { "name": "Read",  "avp.dispatch_target": "local" },
    { "name": "Write", "avp.dispatch_target": "local" },
    { "name": "Bash",  "avp.dispatch_target": "local" }
  ],

  "built_in_subagents": [
    { "name": "general-purpose", "avp.agent_type": "general-purpose" }
  ],

  "built_in_skills": null,

  "capabilities": [
    "skills:progressive",
    "thinking",
    "filesystem-discovery-available"
  ]
}
```

### 2.1 Required fields

| Field | Type | Notes |
|---|---|---|
| `agent_name` | string | The agent's package / binary name (e.g., `"anthropic-reference-agent"`, `"avp-claude-agent-sdk"`). Stable across versions. |
| `agent_version` | string | Semver-compatible. Bumped on any wire-affecting change. |
| `avp_spec_version` | string | The AVP umbrella version the agent conforms to (`"0.1"` for this spec). |
| `built_in_tools` | `Array<BuiltinTool> \| null` | Tool catalog. `null` means the agent has no built-in tools (vs. `[]` meaning it has a tool surface but no entries; semantically the same here but `null` is preferred for "none"). |
| `built_in_subagents` | `Array<BuiltinSubagent> \| null` | Subagent catalog. Same `null` vs `[]` convention. |
| `built_in_skills` | `Array<BuiltinSkill> \| null` | Skill catalog. Same `null` vs `[]` convention. |
| `capabilities` | `string[]` | See §3. MAY be `[]`. |

### 2.2 Optional fields

| Field | Type | Notes |
|---|---|---|
| `default_model` | `string \| null` | The model the agent picks when `Commission.model` is absent. `null` = no default; Commission MUST specify. |
| `supported_models` | `string[] \| null` | Glob patterns the agent's `Commission.model` validates against (e.g., `["claude-*"]`). `null` = no constraint. Commissions with `model` not matching any pattern fail at startup with `error_occurred(code: "unsupported_model")`. |

### 2.3 BuiltinTool

Each entry in `built_in_tools[]`:

```jsonc
{
  "name": "Read",
  "description": "Read a file from disk.",   // optional
  "inputSchema": { /* MCP-shaped JSON Schema */ },  // optional
  "avp.dispatch_target": "local"             // required
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Model-facing tool name. Stable across versions. |
| `description` | string | Optional. Human/model description. |
| `inputSchema` | object | Optional. JSON Schema for the tool's input, in MCP's `inputSchema` shape (camelCase). |
| `avp.dispatch_target` | `"local"` | Required. v0.1 only `"local"` is meaningful for built-ins (compiled into the agent package). Provider-side hosted tools (Anthropic `web_search`, `code_execution`, etc.) tag as `"local"` from AVP's POV (the agent SDK wires the hosted execution). |

### 2.4 BuiltinSubagent

Each entry in `built_in_subagents[]`:

```jsonc
{
  "name": "general-purpose",
  "description": "General-purpose subagent for multi-step research.",  // optional
  "inputSchema": { /* ... */ },                                         // optional
  "avp.agent_type": "general-purpose"                                   // optional
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Model-facing subagent name. |
| `description` | string | Optional. |
| `inputSchema` | object | Optional. JSON Schema for the subagent's invocation input. |
| `avp.agent_type` | string | Optional. Agent-specific identifier (e.g., for Claude Agent SDK's `agent_type`). |

### 2.5 BuiltinSkill

Each entry in `built_in_skills[]`:

```jsonc
{
  "name": "auth-checklist",
  "description": "Checklist for auth changes.",   // optional
  "version": "1.0"                                 // optional
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Skill name (matches SKILL.md frontmatter `name`). |
| `description` | string | Optional. |
| `version` | string | Optional. The skill's own version. |

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
| [Trajectory](./trajectory.md) | The Descriptor payload is the body of `agent_described.data["avp.descriptor"]`. The pre-flight `describe` surface and the run-time `agent_described` event MUST emit byte-identical JSON for the same agent build. |
| [Commission](./commission.md) | Commission's `enabled_builtin_tools` / `enabled_builtin_subagents` / `enabled_builtin_skills` allowlists reference Descriptor-declared `name`s. The agent validates them against the Descriptor at startup. |
| [Resolver API](./resolver.md) | No direct composition; the Descriptor describes only built-ins, never managed assets. |

A consumer that adopts only the Agent Descriptor Spec can run an agent's `describe` command and ingest the result for catalog/discovery purposes without ever sending a Commission or reading a trajectory.

---

## 5. Conformance

An agent (or any Descriptor publisher) is conforming to the Agent Descriptor Spec if and only if:

1. Every Descriptor it emits validates against [`agent-descriptor.schema.json`](./agent-descriptor.schema.json).
2. `avp_spec_version` equals `"0.1"`.
3. The Descriptor is **pure**: the publisher MUST produce identical bytes for identical builds. No environment reads, no filesystem walks, no random ids in the payload. This is what makes the pre-flight `describe` and run-time `agent_described` payloads equal.
4. `built_in_tools[].name` values are unique within the array. Same for `built_in_subagents[].name` and `built_in_skills[].name`.
5. If composed with [Trajectory](./trajectory.md): `agent_described.data["avp.descriptor"]` MUST be byte-identical to what `<agent> describe` prints for the same build.
