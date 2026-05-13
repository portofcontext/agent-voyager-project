# AVP Agent Descriptor Spec, v0.1

**Status:** Stable
**Stability:** JSON shape and field set are committed; additive changes (new capabilities entries, new optional fields) may ship as v0.y, but breaking changes require a new minor or major version.
**Schema:** [`agent-descriptor.schema.json`](./agent-descriptor.schema.json)
**$id:** `https://raw.githubusercontent.com/portofcontext/agent-voyager-project/main/spec/agent-descriptor/v0.1/agent-descriptor.schema.json`

## 1. Scope

The Agent Descriptor Spec defines an agent's **self-description**: the catalog of built-in tools, subagents, and skills the agent can run without supervisor configuration, plus its identity, capabilities, and supported models. It is a data-shape spec; no wire-level protocol.

An Agent Descriptor can be printed to stdout by `<agent> describe` for pre-flight introspection, carried on the wire as the body of [Trajectory](../../trajectory/v0.1/trajectory.md)'s `agent_described` event, or validated by tooling that compares [Commission](../../commission/v0.1-beta/commission.md) `enabled_builtin_*` allowlists against a target agent's surface.

The pre-flight and run-time views are normatively the same payload: `<agent> describe` MUST emit exactly what `agent_described.data["avp.descriptor"]` carries for the same agent build.

## 2. The Agent Descriptor shape

An Agent Descriptor is a single JSON document validating against [`agent-descriptor.schema.json`](./agent-descriptor.schema.json):

```jsonc
{
  "agent_name":       "avp-claude-agent",
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
| `agent_name` | string | Package / binary name. Stable across versions. |
| `agent_version` | string | Semver-compatible. Bumped on any wire-affecting change. |
| `avp_spec_version` | string | `"0.1"` for this spec. |
| `built_in_tools` | `Array<BuiltinTool> \| null` | Tool catalog. `null` = no built-in tools. |
| `built_in_subagents` | `Array<BuiltinSubagent> \| null` | Subagent catalog. |
| `built_in_skills` | `Array<BuiltinSkill> \| null` | Skill catalog. |
| `capabilities` | `string[]` | See §3. MAY be `[]`. |

### 2.2 Optional fields

| Field | Type | Notes |
|---|---|---|
| `default_model` | `string \| null` | The model the agent picks when `Commission.model` is absent. `null` = Commission MUST specify. |
| `supported_models` | `string[] \| null` | Glob patterns `Commission.model` validates against (e.g., `["claude-*"]`). `null` = no constraint. Mismatches fail at startup with `error_occurred(code: "unsupported_model")`. |

### 2.3 BuiltinTool

```jsonc
{
  "name": "Read",
  "description": "Read a file from disk.",
  "inputSchema": { /* MCP-shaped JSON Schema */ },
  "avp.dispatch_target": "local"
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Model-facing tool name. Stable across versions. |
| `description` | string | Optional. |
| `inputSchema` | object | Optional. JSON Schema for the tool's input, MCP's `inputSchema` shape (camelCase). |
| `avp.dispatch_target` | `"local"` | Required. v0.1 only `"local"` is meaningful for built-ins. Provider-side hosted tools (Anthropic `web_search`, `code_execution`) tag as `"local"`. |

### 2.4 BuiltinSubagent

```jsonc
{
  "name": "general-purpose",
  "description": "General-purpose subagent for multi-step research.",
  "inputSchema": { /* ... */ },
  "avp.agent_type": "general-purpose"
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Model-facing subagent name. |
| `description` | string | Optional. |
| `inputSchema` | object | Optional. JSON Schema for invocation input. |
| `avp.agent_type` | string | Optional. Agent-specific identifier (e.g., Claude Agent SDK's `agent_type`). |

### 2.5 BuiltinSkill

```jsonc
{
  "name": "auth-checklist",
  "description": "Checklist for auth changes.",
  "version": "1.0"
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Skill name (matches SKILL.md frontmatter `name`). |
| `description` | string | Optional. |
| `version` | string | Optional. The skill's own version. |

## 3. Capabilities

`capabilities[]` is a flat array of capability flags meaningful to Commission-aware tooling ("skip this Commission if the agent doesn't support thinking blocks"). The vocabulary is open; AVP defines well-known flags but does not constrain the set.

| Flag | Meaning |
|---|---|
| `thinking` | Agent parses and emits provider-side extended-thinking blocks (Anthropic thinking, o-series reasoning) as `reasoning_emitted` events. |
| `skills:eager` | Agent injects resolved SKILL.md bodies into context at startup. `skill_loaded` fires once per skill, `step=0`. |
| `skills:progressive` | Agent's SDK loads skill bodies on demand per turn. `skill_loaded` fires when the body actually enters context, with `step=N`. |
| `filesystem-discovery-available` | Agent's SDK *can* auto-discover skills / subagents from local filesystem paths (e.g., `~/.claude/skills/`). Informational; actual behavior is controlled by SDK-level configuration. |

Implementations MAY publish additional vendor-namespaced flags (e.g., `vendor.acme.fast-mode`). Consumers MUST ignore flags they don't recognize.

## 4. Conformance

An agent (or any Descriptor publisher) is conforming if and only if:

1. Every Descriptor it emits validates against [`agent-descriptor.schema.json`](./agent-descriptor.schema.json).
2. `avp_spec_version` equals `"0.1"`.
3. The Descriptor is **pure**: identical builds produce identical bytes. No environment reads, no filesystem walks, no random ids. This is what makes the pre-flight `describe` and run-time `agent_described` payloads equal.
4. `built_in_tools[].name`, `built_in_subagents[].name`, and `built_in_skills[].name` are unique within their respective arrays.
5. If composed with Trajectory: `agent_described.data["avp.descriptor"]` MUST be byte-identical to what `<agent> describe` prints for the same build.
