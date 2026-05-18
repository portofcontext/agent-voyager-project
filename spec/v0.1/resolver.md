# AVP Resolver API, v0.1

**Status:** Draft
**Stability:** alpha. Method shapes and per-kind result schemas work end-to-end against the reference resolver but have limited adoption beyond it; error-code vocabulary and auth conventions may still change.
**Umbrella version:** v0.1 (see [`README.md`](./README.md))
**Transport:** JSON-RPC 2.0 over an env-var bootstrapped URL (HTTP, HTTPS, or `unix://`)

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

---

## 1. Scope

The Resolver API is the only spec under the AVP v0.1 umbrella that is **actually a wire-level protocol**: it defines request/response semantics between an agent and a supervisor-stood-up service. The other three specs (Trajectory, Commission, Agent Descriptor) are data-shape specs.

The Resolver API exists because [Commission](./commission.md) carries managed assets as opaque `{id, ref}` pairs. To use them, the agent calls the resolver to dereference the opaque ref into the connection material / content / metadata it needs to actually run.

v0.1 specifies:

- **`avp.resolve`**: startup-only. Called once per `Commission.{mcp_servers, skills, subagents}[]` entry to dereference its ref.
- **`avp.spawn_subagent`**: on-demand. Called when the parent agent's model invokes a managed subagent; returns the child run's id plus an inline result summary.

Transport, authentication, and deployment of the resolver service itself are out of scope (see §7).

### 1.1 Non-goals

The Resolver API explicitly does **not** define:

- **Authentication / authorization.** Bearer tokens, mTLS, OAuth: the supervisor configures what its deployment requires via env vars; AVP does not constrain them.
- **Transport encryption.** Inherited from the URL scheme.
- **Caching / TTLs / invalidation.** v0.1 mandates fresh resolution at every startup. Resolvers MAY return material with TTL hints inside that the downstream client (e.g., an MCP client) honors; the Resolver API itself doesn't define caching.
- **Push from resolver to agent.** The resolver is a request/response service the agent dials. There is no resolver → agent push channel.
- **Service discovery.** The agent learns the resolver's URL from `AVP_RESOLVER_URL`; AVP does not define how that URL is computed or distributed.
- **Multi-tenancy / authorization model.** Whether the resolver enforces per-run access controls is the resolver's concern.
- **JSON-RPC batch mode.** Each request/response is a single object.
- **The shape of refs themselves.** `ref` is `JsonValue` from AVP's POV: opaque. The supervisor and its resolver agree on whatever structure makes sense for them.

---

## 2. Bootstrap

The agent learns the resolver's location from the **environment**, not from the Commission. The supervisor sets these variables in the agent process's environment before sending the Commission:

| Env var | Required | Meaning |
|---|---|---|
| `AVP_RESOLVER_URL` | iff Commission has any managed assets | The endpoint the agent dials for `avp.resolve` / `avp.spawn_subagent`. Any URL the agent's HTTP client can reach (HTTP, HTTPS, Unix domain socket via `unix://`). |

Authentication, transport selection (TLS vs unencrypted, mTLS vs bearer), and any other deployment knobs are configured by the supervisor through whatever additional environment variables it chooses to set; AVP does not constrain them. A common pattern is `AVP_RESOLVER_TOKEN` for a bearer token, but no env var beyond `AVP_RESOLVER_URL` is normative.

If the Commission has any non-empty asset list (`mcp_servers`, `skills`, or `subagents`) but `AVP_RESOLVER_URL` is unset or empty, the agent MUST emit `error_occurred` with `data["avp.error.code"]: "resolver_not_configured"` and `agent_stopped(reason: "error")` before any model turn. v0.1-conforming agents are expected to honor managed assets when given a wired resolver; agents that intentionally never engage with the Resolver API simply never receive a managed-asset Commission (the supervisor's deployment topology decides what each agent is given).

---

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

The `result` payload depends on `kind`. v0.1 normative shapes:

#### `mcp_server`

**HTTP:**

```jsonc
{
  "transport": "http",
  "url": "<string>",
  "auth": {"token": "<string>"}
  // OR: "auth": {"header_name": "<string>", "header_value": "<string>"}
  // optional headers:
  "headers": { "<name>": "<value>" }
}
```

**stdio:**

```jsonc
{
  "transport": "stdio",
  "command": ["<argv0>"],
  "args":    ["<flag>", ...],   // optional
  "env":     { "<name>": "<value>" }  // optional
}
```

The agent's MCP client consumes this material. `auth.token` materializes as `Authorization: Bearer <token>` for HTTP. Supervisors that need a different auth shape can pass headers directly via `headers` or `auth.header_name` / `auth.header_value`.

#### `skill`

```jsonc
{
  "name": "<string>",          // optional; defaults to the Commission entry's id
  "description": "<string>",   // optional
  "content": "<SKILL.md body>"
}
```

The agent injects `content` into the model's context per agentskills.io semantics. Agents claiming `skills:eager` MUST emit `skill_loaded` once per resolved skill; `skills:progressive` agents MAY skip emission. See [`trajectory.md`](./trajectory.md) §6.

#### `subagent`

```jsonc
{
  "name": "<string>",                  // optional; defaults to the Commission entry's id
  "description": "<string>",           // optional
  "inputSchema": { /* JSON Schema */ },// optional; MCP-shaped
  "system_prompt": "<string>",         // optional
  "model": "<string>",                 // optional
  "tools": ["<name>", ...]             // optional
}
```

Model-facing metadata and (optionally) the subagent's environment slice. The actual sub-loop runs behind `avp.spawn_subagent` (§4). Resolvers MAY include `system_prompt` / `model` / `tools` so the agent SDK can configure the SDK-side subagent definition (e.g. Claude Agent SDK's `AgentDefinition`); agents that don't use them ignore them.

### 3.3 Extension fields

Resolvers MAY return additional fields beyond those listed; consumers MUST ignore unknown keys. AVP does not define an extension namespace for resolver results; the supervisor and its resolver control the shape end-to-end.

### 3.4 Error response

Standard JSON-RPC 2.0 error object. The agent treats any non-success response as a fatal startup error per §5.

---

## 4. The `avp.spawn_subagent` method

Called when the parent agent's model invokes a managed subagent. Unlike `avp.resolve`, `avp.spawn_subagent` is an **on-demand** call: once per invocation, not at startup.

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
      "reason":     "<StopReason>"
    }
  }
}
```

The subagent's child run is its own complete trajectory commissioned by the supervisor; the supervisor handled `run_requested` → `agent_stopped` for the child independently. The parent agent records the child's `run_id` in its `subagent_invoked.data["avp.subagent.run_id"]` so consumers can correlate the two trajectories. The parent receives the inline summary above for ergonomics; the full child trajectory is for auditors.

See [`trajectory.md`](./trajectory.md) §5 for the parent-side event flow (`subagent_invoked` / `subagent_returned` / `subagent_failed`).

---

## 5. Resolution timing and error handling

For `mcp_servers` and `skills`, the agent MUST resolve all entries at startup, before any model turn:

```
read Commission from stdin
emit run_requested, agent_described, agent_started

# Startup-only resolve
for each entry in commission.mcp_servers + commission.skills + commission.subagents:
    call avp.resolve(...)
    if success:
        emit avp.managed_ref_resolved
    else:
        emit avp.managed_ref_resolve_failed
        emit agent_stopped(reason: "error")
        return

# Materialize: dial MCP servers, load SKILL.md content, register subagent metadata
... emit mcp_server_connected, skill_loaded as appropriate ...

# Run the loop
loop:
    ...
```

For `subagents`, the startup `avp.resolve` returns metadata only; the actual sub-loop is invoked at runtime via `avp.spawn_subagent` when the model picks the subagent. A spawn failure is a tool-call-shaped error: the parent emits `subagent_failed` and the model receives an `Error: …` tool result.

---

## 6. Conformance

### 6.1 Resolver service

A resolver service is conforming if and only if:

1. It exposes JSON-RPC 2.0 at the URL the supervisor configures via `AVP_RESOLVER_URL`.
2. It implements `avp.resolve` per §3 for every `kind` that may appear in `Commission.{mcp_servers, skills, subagents}[]`. Per-kind result shapes MUST match §3.2.
3. If the Commission may carry `subagents`, it MUST additionally implement `avp.spawn_subagent` per §4.
4. Non-resolvable refs return a JSON-RPC error response (any reasonable code; the agent fails the run on any non-success).

### 6.2 Resolver client (typically an agent)

A resolver client is conforming if and only if (when consuming a Commission with any managed assets):

R1. It reads `AVP_RESOLVER_URL` from its environment. If absent or empty, it emits `error_occurred(code: "resolver_not_configured")` + `agent_stopped(reason: "error")` before any model turn.
R2. It calls `avp.resolve` once per `Commission.{mcp_servers, skills, subagents}[]` entry, between `agent_started` and the first `model_turn_started`.
R3. On any resolver error, it emits `managed_ref_resolve_failed` and `agent_stopped(reason: "error")` before any model turn.
R4. For supervisor-managed subagent invocations, it calls `avp.spawn_subagent` and sets `subagent_invoked.data["avp.subagent.run_id"]` to the returned child `run_id`. The supervisor reads the child's trajectory directly (cost / token totals come from reducing the child's `model_turn_ended` deltas); the parent MUST NOT publish a cumulative rollup on the wire.

---

## 7. What the Resolver API does NOT specify

- **Authentication.** Bearer tokens, mTLS, or unauthenticated loopback: the supervisor configures whatever the deployment requires and the agent dials whatever its environment tells it to dial.
- **Transport encryption.** Inherited from the URL scheme.
- **Resolver service availability or HA.** A supervisor-side concern.
- **Caching.** v0.1 mandates no caching: every startup resolves fresh. Resolvers MAY return material with TTL hints inside; that's a runtime concern between the resolved client (e.g., the MCP client) and the resolver.
- **Push notifications from resolver to agent.** The resolver is a request/response service; the agent calls it. There is no resolver → agent push channel.
- **JSON-RPC batch mode.** Each request/response is a single object.
