# AVP Resolver API, v0.1-beta

**Status:** Beta
**Stability:** Method shapes and per-kind result schemas work end to end against the reference resolver but have limited adoption beyond it; breaking changes possible before promotion to Stable.
**Transport:** JSON-RPC 2.0 over an env-var bootstrapped URL (HTTP, HTTPS, or `unix://`)

## 1. Scope

The Resolver API is the only AVP spec that is **actually a wire-level protocol**: it defines request/response semantics between an agent and a supervisor-stood-up service. The other three specs (Trajectory, Commission, Agent Descriptor) are data-shape specs.

It exists because [Commission](../../commission/v0.1-beta/commission.md) carries managed assets as opaque `{id, ref}` pairs. To use them, the agent calls the resolver to dereference the opaque ref into the connection material / content / metadata it needs.

v0.1 specifies two methods:

- **`avp.resolve`** (startup-only). Called once per `Commission.{mcp_servers, skills, subagents}[]` entry to dereference its ref.
- **`avp.spawn_subagent`** (on-demand). Called when the parent agent's model invokes a managed subagent; returns the child run's id plus an inline result summary.

Authentication, transport encryption, caching, service discovery, multi-tenancy, and JSON-RPC batch mode are out of scope. The supervisor configures whatever its deployment requires; AVP does not constrain them.

## 2. Bootstrap

The agent learns the resolver's location from the **environment**, not from the Commission:

| Env var | Required | Meaning |
|---|---|---|
| `AVP_RESOLVER_URL` | iff Commission has any managed assets | The endpoint the agent dials. Any URL the agent's HTTP client can reach (HTTP, HTTPS, `unix://`). |

Authentication and other deployment knobs are configured by the supervisor through additional environment variables it chooses to set; a common pattern is `AVP_RESOLVER_TOKEN` for a bearer token, but no env var beyond `AVP_RESOLVER_URL` is normative.

If the Commission has any non-empty asset list but `AVP_RESOLVER_URL` is unset or empty, the agent MUST emit `error_occurred` with `data["avp.error.code"]: "resolver_not_configured"` and `agent_stopped(reason: "error")` before any model turn.

## 3. The `avp.resolve` method

Called once per managed-asset ref, at startup, before any model turn.

### 3.1 Request

```jsonc
{
  "jsonrpc": "2.0",
  "id": "<unique per call>",
  "method": "avp.resolve",
  "params": {
    "run_id": "<Commission.run_id>",
    "kind":   "mcp_server" | "skill" | "subagent",
    "id":     "<Commission entry's id>",
    "ref":    <opaque JsonValue from the Commission entry, verbatim>
  }
}
```

### 3.2 Successful response: per-kind result schemas

The `result` payload depends on `kind`.

#### `mcp_server`

HTTP:

```jsonc
{
  "transport": "http",
  "url": "<string>",
  "auth": {"token": "<string>"}
  // OR: "auth": {"header_name": "<string>", "header_value": "<string>"}
  "headers": { "<name>": "<value>" }   // optional
}
```

stdio:

```jsonc
{
  "transport": "stdio",
  "command": ["<argv0>"],
  "args":    ["<flag>", ...],          // optional
  "env":     { "<name>": "<value>" }   // optional
}
```

The agent's MCP client consumes this material. `auth.token` materializes as `Authorization: Bearer <token>` for HTTP. Supervisors needing a different auth shape pass headers via `headers` or `auth.header_name` / `auth.header_value`.

#### `skill`

```jsonc
{
  "name": "<string>",          // optional; defaults to the Commission entry's id
  "description": "<string>",   // optional
  "content": "<SKILL.md body>"
}
```

The agent injects `content` into the model's context per agentskills.io semantics. Agents claiming `skills:eager` MUST emit `skill_loaded` once per resolved skill; `skills:progressive` agents MAY skip emission.

#### `subagent`

```jsonc
{
  "name": "<string>",                   // optional; defaults to the Commission entry's id
  "description": "<string>",            // optional
  "inputSchema": { /* JSON Schema */ }, // optional; MCP-shaped
  "system_prompt": "<string>",          // optional
  "model": "<string>",                  // optional
  "tools": ["<name>", ...]              // optional
}
```

Model-facing metadata and (optionally) the subagent's environment slice. The actual sub-loop runs behind `avp.spawn_subagent`. Resolvers MAY include `system_prompt` / `model` / `tools` so the agent SDK can configure the SDK-side subagent definition (e.g. Claude Agent SDK's `AgentDefinition`); agents that don't use them ignore them.

### 3.3 Extension fields

Resolvers MAY return additional fields beyond those listed; consumers MUST ignore unknown keys. AVP does not define an extension namespace; the supervisor and its resolver control the shape end-to-end.

### 3.4 Error response

Standard JSON-RPC 2.0 error object. The agent treats any non-success response as a fatal startup error.

## 4. The `avp.spawn_subagent` method

Called on-demand when the parent agent's model invokes a managed subagent.

### 4.1 Request

```jsonc
{
  "jsonrpc": "2.0",
  "id": "<unique per call>",
  "method": "avp.spawn_subagent",
  "params": {
    "run_id": "<parent Commission.run_id>",
    "id":     "<Commission.subagents[].id>",
    "ref":    <opaque ref from the Commission entry, verbatim>,
    "input":  <invocation input the model produced>
  }
}
```

### 4.2 Successful response

```jsonc
{
  "jsonrpc": "2.0",
  "id": "<matches request>",
  "result": {
    "subagent_run_id": "<child run_id>",
    "result": {
      "text":       "<subagent's final result text>",
      "structured": <optional structured result>,
      "reason":     "<StopReason>",
      "usage":      <RunStateSnapshot of the subagent's spend>
    }
  }
}
```

The subagent's child run is its own complete trajectory commissioned by the supervisor; the supervisor handled `run_requested` → `agent_stopped` for the child independently. The parent agent records the child's `run_id` in its `subagent_invoked.data["avp.subagent.run_id"]` so consumers can correlate. See [Trajectory §5](../../trajectory/v0.1/trajectory.md#5-subagents) for the parent-side event flow.

## 5. Resolution timing

For `mcp_servers` and `skills`, the agent MUST resolve all entries at startup, between `agent_started` and the first `model_turn_started`. On success, emit `managed_ref_resolved`; on failure, emit `managed_ref_resolve_failed` followed by `agent_stopped(reason: "error")` before any model turn.

For `subagents`, startup `avp.resolve` returns metadata only; the actual sub-loop is invoked at runtime via `avp.spawn_subagent` when the model picks the subagent. A spawn failure is a tool-call-shaped error: the parent emits `subagent_failed` and the model receives an `Error: …` tool result.

## 6. Conformance

### 6.1 Resolver service

A resolver service is conforming if and only if:

1. It exposes JSON-RPC 2.0 at the URL the supervisor configures via `AVP_RESOLVER_URL`.
2. It implements `avp.resolve` per §3 for every `kind` that may appear in `Commission.{mcp_servers, skills, subagents}[]`. Per-kind result shapes MUST match §3.2.
3. If the Commission may carry `subagents`, it MUST additionally implement `avp.spawn_subagent` per §4.
4. Non-resolvable refs return a JSON-RPC error response (any reasonable code; the agent fails the run on any non-success).

### 6.2 Resolver client (typically an agent)

A resolver client is conforming if and only if (when consuming a Commission with any managed assets):

R1. Reads `AVP_RESOLVER_URL` from its environment. If absent or empty: `error_occurred(code: "resolver_not_configured")` + `agent_stopped(reason: "error")` before any model turn.
R2. Calls `avp.resolve` once per `Commission.{mcp_servers, skills, subagents}[]` entry, between `agent_started` and the first `model_turn_started`.
R3. On any resolver error: `managed_ref_resolve_failed` + `agent_stopped(reason: "error")` before any model turn.
R4. For supervisor-managed subagent invocations: calls `avp.spawn_subagent`, sets `subagent_invoked.data["avp.subagent.run_id"]` to the returned child `run_id`, and rolls the child's `usage` into the parent's `RunStateSnapshot`.
