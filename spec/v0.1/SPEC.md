# Agent Voyage Protocol — Specification

**Status:** Draft
**Schema:** [`avp.schema.json`](./avp.schema.json) (JSON Schema Draft 2020-12)
**$id base:** `https://avp.dev/schema/v0.1/`

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

## 0. Built on

AVP specializes — it does not reinvent — the following industry specs:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`, `source`, `type`, `subject`, `time`, `datacontenttype`, `data`).
- **OpenTelemetry GenAI semantic conventions** for token / cost / model / tool attribute names inside `data` (e.g., `gen_ai.usage.input_tokens`, `gen_ai.tool.name`).
- **OpenTelemetry span identification** (`trace_id`, `span_id`, `parent_span_id`) on every event so trajectories reconstruct as a span tree.
- **JSON-RPC 2.0** for the AVP resolver protocol — agent → resolver service calls (`avp.resolve`, `avp.spawn_subagent`) that dereference opaque refs in the Commission. See §6.
- **MCP 2025-11-25** for supervisor-side tool dispatch. Commission entries in `mcp_servers[]` are opaque refs the agent resolves (§6) into MCP connection material; the agent then runs MCP's `initialize` + `tools/list` and dispatches `tools/call` against the live server. AVP doesn't redefine the MCP wire; it just references the asset and observes the dispatch.
- **Agent Skills** (agentskills.io) for `SKILL.md` content. Commission `skills[]` entries are refs; the resolver returns SKILL.md content (or a location to fetch).
- **JSON Schema Draft 2020-12** for this specification's machine-readable form.

AVP-specific concepts — the **no-mid-run-reach-in topology** and the **trajectory-as-source-of-truth contract** — live under the `avp.*` attribute namespace.

See [`FOUNDATIONS.md`](../../FOUNDATIONS.md) for the full mapping rationale.

---

## 1. The seam

AVP defines exactly one seam, between two roles, with **two unidirectional flows** crossing it, plus **one agent-initiated callback** to a supervisor-stood-up resolver service:

- **Supervisor** — declares a Commission at startup: prompt, model, and supervisor-managed assets (`mcp_servers`, `skills`, `subagents`) as opaque refs. Once the Commission is sent, the supervisor observes the trajectory; it does not push anything else to the agent.
- **Agent** — runs inside the Commission. Calls the supervisor's resolver service (§6) at startup to dereference managed refs into connection material. Emits a stream of facts (events) the supervisor observes.

```
   supervisor  ──────── Commission ─────────▶  agent
                                                 │
                                                 │  resolves managed refs at
                                                 │  startup via avp.resolve
                                                 │  to a supervisor-stood-up
                                                 │  resolver service
                                                 │
                                                 │  runs the run, emits events
                                                 ▼
   supervisor  ◀──────── trajectory ─────────  agent
```

A **Commission** carries `prompt`, `model`, `mcp_servers`, `subagents`, `skills`, and `output_schema` — sent once at startup. Asset entries are `{id, ref}` pairs where `ref` is opaque to the agent and AVP. The **trajectory** is the stream of CloudEvents the agent emits as it runs; it opens with `run_requested` → `agent_described` (which publishes the agent's **manifest** — built-in tools, capabilities, version) → `agent_started`, and closes with `agent_stopped`.

This is the v0.1 architectural choice: **the supervisor configures, the agent runs, the trajectory is the truth.** No mid-run supervisor → agent push channel. The agent's bounded context is intact because its environment was fully specified up front; runtime resolution of opaque refs is agent-initiated, scoped to startup, and recorded on the trajectory as `managed_ref_resolved` / `managed_ref_resolve_failed` events.

What an agent provides on its own — built-in tools, baked-in skills, in-process subagent definitions — is invisible to AVP and the Commission. It surfaces only on the agent's manifest (`agent_described.data["avp.manifest"]`), which the supervisor and any auditor can read on the trajectory's second event. The agent's runtime layer merges its internal contribution with the resolved managed assets; collisions on `id` are a startup error.

---

## 2. Message classes

| Class | Direction | Cardinality | Schema entry point |
|---|---|---|---|
| `Commission` | supervisor → agent | exactly one, at startup | [`commission.schema.json`](./commission.schema.json) |
| `Event` | agent → supervisor | streamed throughout the run | [`event.schema.json`](./event.schema.json) |

v0.1 has no supervisor → agent push channel. The agent's only outbound direction at runtime is **agent → resolver service** (§6) for dereferencing managed refs declared in the Commission; this is agent-initiated and observed on the trajectory.

---

## 3. The trajectory

The agent's stdout is the **canonical trajectory**. Every event is a CloudEvents 1.0 envelope (per §0). The `source` attribute is a URI that identifies the producer:

- **`source: "avp://agent"`** is the overwhelming majority of events — the agent emitting facts about what it did.
- **`source: "avp://supervisor"`** appears only on the trajectory's opening `avp.run_requested` event (agent-relayed from `Commission.supervisor`; see §3.1). v0.1 has no supervisor → agent push channel — supervisors do not directly emit events.

Every event's `data` payload carries an OpenTelemetry **span triple** — `trace_id` (16 random bytes, 32 lowercase hex chars), `span_id` (8 random bytes, 16 hex chars), and `parent_span_id` (or 16 zeros for the root). The agent span is the run; turn / tool / managed-ref-resolution spans nest inside it. Consumers reconstruct the trajectory as a span tree.

### 3.1 Run prelude

Every conforming trajectory opens with three events, in this exact order:

```
1. avp.run_requested      source=avp://supervisor   (agent-relayed)
2. avp.agent_described    source=avp://agent
3. avp.agent_started      source=avp://agent
```

These are distinct facts the wire records before the agent runs:

- **`avp.run_requested`** anchors the run. The agent emits it from `Commission.supervisor` with `source: avp://supervisor` — agent-relayed; the agent stamps the source URI to attribute the run to the originating supervisor build. `data.avp.commission` carries the full Commission snapshot the supervisor handed in (refs included verbatim, since they are opaque to the agent), so an auditor reading the trajectory can re-derive the run's input surface without an external Commission registry. `data.avp.supervisor.name` and the optional `data.avp.supervisor.version` complete the attribution.

- **`avp.agent_described`** is the agent's "whoami" — its self-published manifest of everything triggerable without supervisor configuration: SDK preset tools, runtime-bundled subagents, runtime-bundled skills, plus the agent's name, version, and supported AVP spec version. The payload (`data.avp.manifest`) MUST equal what `<agent> describe` prints to stdout for the same agent build. This makes the audit trail and pre-flight introspection two views of the same fact. v0.1-conforming agents implicitly speak the resolver protocol — capability is implied by `avp_spec_version: "0.1"` rather than carried as a separate flag.

- **`avp.agent_started`** is the merged-view event, listing what the model will actually see for this specific run: the agent's internal contribution combined with the supervisor's managed assets after they have been resolved (per §6).

`run_requested` and `agent_described` are root-level in the span tree (`parent_span_id = ZERO`). They do NOT pair (each owns its own span); `agent_started` owns the agent span that all subsequent run events nest under.

An agent that cannot identify itself (no manifest available) MUST NOT skip the prelude — instead, emit `agent_described` with the smallest valid manifest it can publish (its own package name, version, and `avp_spec_version`). A supervisor that omits `Commission.supervisor` MUST still see `run_requested` emitted, with `avp.supervisor.name="unknown"`.

### 3.2 Managed-ref resolution events

Between `agent_started` and the first `model_turn_started`, the agent MUST resolve every managed asset declared in the Commission (per §6). Each successful resolution emits one `avp.managed_ref_resolved` event; any failure emits one `avp.managed_ref_resolve_failed` event followed by `agent_stopped(reason: "error")`. These events do not re-record the opaque ref material — `run_requested.data["avp.commission"]` already carries it; the resolution events record only that the round-trip happened.

---

## 4. Conformance — overview

An **agent** is conforming if it reads exactly one valid `Commission` at startup, resolves every managed asset referenced in the Commission per §6, runs the run inside the resolved environment per §10, and emits the events required by §11–§12. See §14.1 for the full checklist.

A **supervisor** is conforming if every `Commission` it sends validates against `commission.schema.json` and it stands up a resolver service the agent can reach (when the Commission carries any managed assets). v0.1 has no supervisor → agent push channel. See §14.2.

---

## 5. Transports

A conforming implementation MUST support at least one transport for the Commission/event pipe. The resolver protocol (§6) rides its own transport, separate from the Commission/event pipe.

### 5.1 stdio (local)

- The supervisor launches the agent as a subprocess.
- The supervisor MUST write a single `Commission` JSON document to the agent's stdin, terminated by `\n`.
- The agent MUST read exactly one `Commission` from stdin before emitting any events.
- After reading `Commission`, stdin is unused — v0.1 has no supervisor → agent push channel.
- The agent MUST emit `Event` documents to stdout as NDJSON, one JSON object per line, no pretty-printing, terminated by `\n`. The agent MUST flush stdout after each line.

### 5.2 HTTP (remote)

- The supervisor POSTs a single `Commission` to start a run; the agent streams events back via Server-Sent Events.
- No back-channel on this transport. Resolver calls (§6) ride the resolver's own transport.

---

## 6. The resolver protocol

The Commission carries supervisor-managed assets as opaque `{id, ref}` pairs, never inline material. To use them, the agent calls a **resolver service** stood up by the supervisor. v0.1 specifies one JSON-RPC 2.0 method for asset resolution (`avp.resolve`) and one for managed subagent invocation (`avp.spawn_subagent`); transport and authentication of the resolver service itself are deployment concerns and out of scope (§15).

### 6.1 Bootstrap

The agent learns the resolver's location from the **environment**, not from the Commission. The supervisor sets these variables in the agent process's environment before sending the Commission:

| Env var | Required | Meaning |
|---|---|---|
| `AVP_RESOLVER_URL` | iff Commission has any managed assets | The endpoint the agent dials for `avp.resolve` / `avp.spawn_subagent`. Any URL the agent's HTTP client can reach (HTTP, HTTPS, Unix domain socket via `unix://`). |

Authentication, transport selection (TLS vs unencrypted, mTLS vs bearer), and any other deployment knobs are configured by the supervisor through whatever additional environment variables it chooses to set; AVP does not constrain them.

If the Commission has any non-empty asset list (`mcp_servers`, `skills`, or `subagents`) but `AVP_RESOLVER_URL` is unset or empty, the agent MUST emit `error_occurred` with `data["avp.error.code"]: "resolver_not_configured"` and `agent_stopped(reason: "error")` before any model turn. v0.1-conforming agents are expected to honor managed assets when given a wired resolver; agents that intentionally never engage with the resolver protocol simply never receive a managed-asset Commission (the supervisor's deployment topology decides what each agent is given).

### 6.2 The `avp.resolve` method

Called once per managed-asset ref, at startup, before any model turn.

**Request:**

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

**Successful response:** `result` payload depends on `kind`:

| Kind | Result schema (informative) |
|---|---|
| `mcp_server` | `{ "transport": "http"\|"stdio", "url"?: string, "auth"?: object, "command"?: string[], "args"?: string[], "env"?: object }` — connection material the agent uses to dial an MCP server. The exact field set is whatever the supervisor's resolver returns; the agent's MCP client consumes it. |
| `skill` | `{ "name": string, "description"?: string, "content": string }` — SKILL.md frontmatter + body. The agent loads `content` into the model's context per agentskills.io semantics. (Alternatively, a `{ "url": "..." }` form the agent fetches; supervisors choose.) |
| `subagent` | `{ "name": string, "description"?: string, "inputSchema"?: object }` — model-facing metadata so the parent's model can decide whether to delegate. The actual sub-loop lives behind `avp.spawn_subagent`. |

Per-kind result schemas are authoritative in `commission.schema.json`'s `$defs` (Phase 2 will pin them precisely; v0.1 leaves the schema permissive while the resolver ecosystem stabilizes).

**Error response:** standard JSON-RPC 2.0 error object. The agent treats any non-success response as a fatal startup error per §6.4.

### 6.3 The `avp.spawn_subagent` method

Called when the parent agent's model invokes a managed subagent. Unlike `avp.resolve`, `avp.spawn_subagent` is an **on-demand** call — once per invocation, not at startup.

**Request:**

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

**Successful response:**

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

The subagent's child run is its own complete trajectory commissioned by the supervisor — the supervisor handled `run_requested` → `agent_stopped` for the child independently. The parent agent records the child's `run_id` in its `subagent_invoked.data["avp.subagent.run_id"]` so consumers can correlate the two trajectories. The parent receives the inline summary above for ergonomics; the full child trajectory is for auditors.

### 6.4 Resolution timing and error handling

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

For `subagents`, the startup `avp.resolve` returns metadata only; the actual sub-loop is invoked at runtime via `avp.spawn_subagent` when the model picks the subagent. A spawn failure is a tool-call-shaped error: the parent emits `subagent_failed` and the model receives an `Error: …` tool result (§9).

### 6.5 What the resolver protocol does NOT specify

- **Authentication.** Bearer tokens, mTLS, or unauthenticated loopback — the supervisor configures whatever the deployment requires and the agent dials whatever its environment tells it to dial.
- **Transport encryption.** Inherited from the URL scheme.
- **Resolver service availability or HA.** A supervisor-side concern.
- **Caching.** v0.1 mandates no caching: every startup resolves fresh. Resolvers MAY return material with TTL hints inside; that's a runtime concern between the resolved client (e.g., the MCP client) and the resolver.
- **Push notifications from resolver to agent.** The resolver is a request/response service; the agent calls it. There is no resolver → agent push channel.

---

## 7. Tool dispatch via MCP

v0.1 has one mechanism for supervisor-side tool dispatch: **MCP** ([Model Context Protocol](https://modelcontextprotocol.io/), 2025-11-25). The supervisor's resolver returns connection material for each `Commission.mcp_servers[]` entry (§6); the agent uses it to dial the actual MCP server, runs MCP's `initialize` + `tools/list`, and dispatches `tools/call` against the server when the model invokes one of those tools.

There is no AVP-flavored RPC channel for tool dispatch — that rides on the existing MCP wire, the same protocol your editor, IDE plugin, or other agent runtime is already speaking. AVP's contribution at the tool-dispatch layer is purely observational: emit `avp.mcp_server_connected` with the live tool catalog on connect, emit `avp.mcp_server_disconnected` on close, and tag each `tool_invoked` / `tool_returned` pair with `avp.tool.dispatch_target = "mcp_server"` and `avp.mcp_server_id` matching the Commission entry.

Tools the agent ships in-process (e.g. avp-anthropic's `bash`/`read_file`/`write_file`) are agent-package built-ins. They appear on the manifest (`agent_described.data.avp.manifest.built_in_tools`) and on `agent_started.data.tools` with `avp.tool.dispatch_target = "local"`. The agent runs them directly; no MCP layer involved.

The result: two well-defined dispatch paths for any tool the model can call — `local` (compiled into the agent) or `mcp_server` (resolved from a Commission ref). Nothing else.

---

## 8. Verifiers (deferred)

v0.1 does not specify verifiers. The deterministic-checks-at-trigger-points concept was carried in early drafts and is removed here so v0.1 stays narrowly focused on observation and tool dispatch. A future revision may reintroduce verifiers (or a slimmer "pre-tool gate" surface) once the wire-level shape has settled. Until then, supervisors that want gating wire it externally — by running the agent inside a constrained workspace, by exposing only safe MCP servers in the Commission, or by reviewing the trajectory after the fact.

---

## 9. Tools

v0.1 has two paths for any tool the model can call:

1. **Agent built-in.** Compiled into the agent package. Examples: avp-anthropic's `bash`/`read_file`/`write_file`, avp-claude-agent's `Read`/`Edit`/`Bash`/etc. Surfaced on the agent's manifest (`agent_described.data.avp.manifest.built_in_tools`) and on `agent_started.data.tools[]` with `avp.tool.dispatch_target = "local"`. The agent runs them directly.
2. **MCP server.** Declared by the supervisor in `Commission.mcp_servers[]` as `{id, ref}`. The agent resolves the ref (§6), dials the resolved endpoint, runs MCP's `tools/list`, and dispatches calls via MCP's `tools/call`. Surfaced on `mcp_server_connected.data.avp.mcp.tools[]` (live tool catalog) and on `agent_started.data.tools[]` with `avp.tool.dispatch_target = "mcp_server"` and `avp.mcp_server_id` matching the Commission entry's `id`.

Wire flow:

1. Model calls a tool. Agent emits `avp.tool_invoked`.
2. Agent dispatches: locally for built-ins, via MCP for MCP-server tools.
3. Agent emits `avp.tool_returned` (or `avp.tool_failed`).

There is no AVP-flavored RPC channel for tool dispatch. Supervisors that want to expose Python (or shell, or HTTP-backed) tools wrap them in an MCP server, declare the server's ref in `Commission.mcp_servers[]`, and have their resolver return the connection material when asked.

**`avp.tool.dispatch_target`.** Every `tool_invoked` event MAY carry `avp.tool.dispatch_target` discriminating the implementation that handled the call:

| Value | Meaning |
|---|---|
| `local` | Tool ran in the agent's own process — code compiled into the agent package (e.g. avp-anthropic's `bash`/`read_file`). Provider-side hosted tools (Anthropic `web_search`, `code_execution`, etc.) are agent built-ins from AVP's POV and tag as `local` — the agent SDK is responsible for actually wiring the provider-hosted execution. |
| `mcp_server` | Tool was dispatched by an MCP server. The event also carries `avp.mcp_server_id` matching a `Commission.mcp_servers[].id`. |

Supervisors building dashboards / audits filter on `dispatch_target` to count tool calls by implementation route and on `avp.mcp_server_id` to break down by server.

### 9.1 Merge semantics: agent-internal ∪ Commission-managed

The agent's loop dispatches against a single bag of tools, regardless of whether each entry was baked into the agent or resolved from a Commission ref. The agent's runtime layer constructs the bag at startup:

1. Start with the agent's internal tools (manifest's `built_in_tools`).
2. For each `Commission.mcp_servers[]` ref, resolve, connect, and add the server's `tools/list` output.
3. If any `id` collision exists between an agent-internal MCP server and a Commission-declared one, emit `error_occurred` with `data["avp.error.code"]: "commission_collision"` and stop. Configuration errors fail-fast.

Tool-name collisions across distinct MCP servers (e.g. agent-internal `github_v1` and Commission-managed `github_v2` both exposing `list_prs`) are an agent-runtime concern outside AVP's wire. The agent's MCP client surfaces names to the model however it normally does (most clients namespace by server id, e.g. `github_v1__list_prs`); AVP records the name the agent dispatched on in `tool_invoked.data["gen_ai.tool.name"]`.

### 9.2 Built-in surface allowlists

`Commission` carries three optional allow-lists that gate which agent **built-ins** surface to the model for the run:

| Field | Gates | Source of truth |
|---|---|---|
| `enabled_builtin_tools` | `manifest.built_in_tools[].name` | The agent's manifest |
| `enabled_builtin_subagents` | `manifest.built_in_subagents[].name` | The agent's manifest |
| `enabled_builtin_skills` | `manifest.built_in_skills[].name` | The agent's manifest |

Semantics, identical across all three:

- **Absent (null)** → every built-in of that kind is exposed (default; backwards-compatible).
- **`[]`** → no built-in of that kind is exposed.
- **`[n1, n2, …]`** → only the listed names are exposed; the rest are hidden from the model and runtime-blocked if invoked.

These fields gate **agent built-ins only**. Supervisor-managed assets (`mcp_servers`, `skills`, `subagents` refs) are gated by their presence/absence in the Commission and are never affected. Tools surfaced post-handshake by a managed MCP server are controlled by which MCP server the supervisor declared.

**Validation at startup (MUST).** The agent MUST validate every name in each allowlist against the corresponding manifest list. Names that don't match emit `error_occurred` with `data["avp.error.code"]: "commission_collision"` and the agent stops with `reason: "error"` before any model turn. Fail-loud-on-drift: a Commission referencing a built-in the agent no longer ships is a contract violation; supervisors find out at startup, not via silent surface degradation.

**Two-layer enforcement (MUST).**

- **Visibility (primary).** When the agent constructs `agent_started.data.tools[]` / `data.subagents[]` / `data.skills[]` from its built-in surface, entries not in the allowlist MUST be omitted. The model literally doesn't see disabled built-ins.
- **Runtime block (defense in depth).** If the model invokes a built-in name that's been allow-listed out (hallucination, prompt injection from tool output, prior-context leakage), the agent MUST emit `tool_failed` (or `subagent_failed`) after `tool_invoked` (or `subagent_invoked`) and not execute the built-in. The trajectory faithfully records the attempt.

Common patterns:
- Read-only audit run → `enabled_builtin_tools: ["Read", "Glob", "Grep"]`
- No network egress → omit `WebFetch`, `WebSearch` from the tools list
- Pure delegation (force the model into managed assets) → `enabled_builtin_tools: []`

---

## 9.5 Subagents

`Commission.subagents[]` declares **delegate agents** the parent agent may invoke by name, as `{id, ref}` pairs. The supervisor stands up the subagent as a managed asset (its own environment slice, its own model, its own tool surface — handled by the supervisor's resolver and child-run commissioning); the parent agent only sees an opaque ref.

**Wire flow.**

1. At startup, the parent agent calls `avp.resolve` for each `subagents[]` entry to obtain model-facing metadata (`name`, `description`, `inputSchema`). The resolved metadata appears on `agent_started.data.subagents[]`.
2. Model invokes a tool whose name matches a resolved subagent. Agent emits `avp.subagent_invoked` (NOT `avp.tool_invoked`). The event's `data.span_id` is the **frame span** for this invocation. Agent calls `avp.spawn_subagent` (§6.3) with the saved ref + input.
3. The supervisor handles the child run as its own commissioned trajectory (separate `run_id`, separate `run_requested` → `agent_stopped`). The parent records the child's `run_id` in `subagent_invoked.data["avp.subagent.run_id"]`.
4. When `avp.spawn_subagent` returns, the parent agent emits `avp.subagent_returned` carrying `data.avp.subagent.result.text` plus a `RunStateSnapshot` rollup at `data.avp.subagent.usage` from the resolver's response. The `data.span_id` MUST equal the matching `subagent_invoked.data.span_id` so consumers pair them.
5. If `avp.spawn_subagent` errors, the parent agent emits `avp.subagent_failed` with `data.avp.subagent.error` instead of `subagent_returned`. The model receives an `Error: …` tool_result for symmetry with §9.
6. The subagent's spend (cost, tokens) MUST be rolled into the parent run's cumulative `RunStateSnapshot`. Per-subagent attribution is preserved on `subagent_returned.data.avp.subagent.usage` and the full child trajectory.

**Trajectory correlation.** Consumers join the parent and child trajectories via `subagent_invoked.data["avp.subagent.run_id"]` matching the child run's `run_id` (carried on every child event's `subject` per CloudEvents). The child trajectory is independently complete; consumers can render it standalone or nested under the parent.

**Subagent ↔ tool collision.** Resolved subagent names MUST NOT collide with agent built-in tool names or with any tool returned by a Commission-managed MCP server. A collision is a configuration conflict — the agent MUST detect this at startup, emit `error_occurred` with `data["avp.error.code"]: "commission_collision"`, and stop with `reason: "error"` before any model turn runs.

**`agent_started.data.subagents`.** The agent MUST surface the resolved subagent declarations on `agent_started.data.subagents[]` (parallel to `data.tools[]` and `data.skills[]`). Each entry carries `name`, `description`, and optional `inputSchema` (MCP-shaped) returned by `avp.resolve`. Consumers can read this without re-resolving.

---

## 9.7 Skills

`Commission.skills[]` declares [Agent Skills](https://agentskills.io/specification) the agent loads into the model's context for the run, as `{id, ref}` pairs. The agent calls `avp.resolve` (§6) at startup to obtain the SKILL.md content (or a location to fetch); agentskills.io's content model then applies. AVP itself does not specify URI schemes for skill sources — that's between the supervisor's resolver and whatever store it pulls from (filesystem, MCP `resources/read`, registry, content-addressed blob, etc.).

### 9.7.1 Loading semantics

The `avp.skill_loaded` event means **the SKILL.md body content has been added to the model's active context window** — NOT a registration acknowledgment. (The registration view is `agent_started.data.skills[]`; the resolution view is `managed_ref_resolved` for each entry.)

Two emission patterns differentiated by an agent's `manifest.capabilities`:

- **`skills:eager`** — agent injects all resolved SKILL.md bodies at startup (typically as a system_prompt suffix). Emit `skill_loaded` once per skill, `step=0`, after `agent_started` and before turn 1. The reference `AVPAgent` and `avp-anthropic` claim this capability.

- **`skills:progressive`** — model decides per-turn which skill bodies to pull into context (Anthropic Skills, Claude Code progressive disclosure). Emit `skill_loaded` when the body actually enters context, with `step=N` matching the turn it loaded in. MAY fire multiple times for the same skill (e.g., re-load after compaction). `avp-claude-agent` claims this capability.

Agents whose SDK does NOT expose progressive-disclosure load events SHOULD NOT emit `skill_loaded` at all — `agent_started.data.skills[]` still records the registration. Honest-silent beats fabricated events.

### 9.7.2 Resolution failures

If a skill ref cannot be resolved (resolver unreachable, skill content malformed, ref not understood by the resolver), the agent MUST emit `managed_ref_resolve_failed` and `agent_stopped` with `reason: "error"` BEFORE any model turn runs. Skill resolution is part of the run prelude, not a runtime concern — supervisors get fail-fast on configuration mistakes.

---

## 10. The agent loop (normative)

A conforming agent MUST behave as if executing the following algorithm. (The agent MAY reorder operations that are not externally observable, provided the emitted event sequence is indistinguishable.)

### 10.1 Run state and the definition of a turn

A **turn** in AVP is exactly one `model_turn_started` / `model_turn_ended` pair where the model produced new output (either text or tool calls or both). Continuations and SDK-internal restatements that do not represent a fresh model call MUST NOT be counted as turns.

This matters most for translator-pattern agents wrapping SDKs that emit "assistant message" objects for things that aren't fresh model calls (e.g., follow-up wrappers around tool results). Translator agents MUST count an event as a turn only when the SDK-reported usage carries non-zero new output tokens (delta-output > 0), or — if the SDK doesn't report per-call usage — when the message includes content the model itself produced.

The agent maintains a `RunStateSnapshot` (see [`avp.schema.json#/$defs/RunStateSnapshot`](./avp.schema.json)) tracking `total_turns`, `total_cost_usd`, `total_tokens`, etc. The snapshot is observability — it travels on `cost_recorded` and `agent_stopped` so consumers can trace cumulative spend, but v0.1 does not specify caps that the agent must enforce against it.

### 10.2 The loop

```
read commission from stdin
emit run_requested  (source=avp://supervisor, agent-relayed)
emit agent_described
emit agent_started

# Startup resolve (§6)
for each entry in commission.mcp_servers + commission.skills + commission.subagents:
    call avp.resolve(...)
    on success: emit managed_ref_resolved
    on failure: emit managed_ref_resolve_failed; emit agent_stopped("error"); return

# Materialize the resolved environment
for each mcp_server: dial; emit mcp_server_connected
for each skill:      load content; emit skill_loaded (if eager)

loop:
    state.total_turns += 1
    emit model_turn_started(step)
    response = call_model()
    emit model_turn_ended(step, tokens, cost, ...)

    state.total_cost_usd += response.cost_usd
    state.total_tokens   += response.tokens_input + response.tokens_output
    emit cost_recorded(state)

    for tool_call in response.tool_calls:
        emit tool_invoked(call_id, tool, input)
        if tool is an MCP-server tool:
            output = mcp_dispatch(server_id, tool, input)
        elif tool is a managed subagent:
            emit subagent_invoked
            response = call avp.spawn_subagent(...)
            emit subagent_returned (or subagent_failed)
        else:
            output = execute_tool_locally(input)
        emit tool_returned(call_id, output)

    if model converged:
        emit agent_stopped("converged"); return
```

### 10.3 Cost / token accounting rules (normative)

- `cost_usd` on `model_turn_ended` is the BILLABLE cost (post-cache-discount).
- `tokens_input` on `model_turn_ended` is the total input tokens INCLUDING cache-read tokens.
- `tokens_cache_read` and `tokens_cache_write` are informational; they MUST NOT alter `state.total_tokens` independently.
- `state.total_cost_usd` and `state.total_tokens` are monotonically non-decreasing.
- **Translator agents over cumulative-usage SDKs.** Some SDKs (notably the Claude Agent SDK) report usage as a running session total per message rather than as a per-call delta. Translators MUST derive deltas (subtract previous cumulative) to populate per-turn `tokens_*` and `cost_usd` correctly. When the SDK's cumulative drops without warning (`cum < prev`), the translator MUST emit `error_occurred` with `code: "accounting_reset"` rather than silently clamping; consumers cannot distinguish a swallowed delta from a legitimate quiet turn otherwise. SDKs that signal context compaction or sub-agent dispatch via lifecycle events SHOULD be hooked so the translator resets its baselines deliberately, not via the error path.

---

## 11. Two classes of trajectory facts

The trajectory holds two semantically distinct kinds of facts. Implementations and supervisor frameworks SHOULD surface them separately to consumers:

| Class | Event types | Semantics |
|---|---|---|
| **What the agent did** | `model_turn_*`, `tool_invoked`, `tool_returned`, `tool_failed`, `text_emitted`, `subagent_*`, `managed_ref_resolved`, `managed_ref_resolve_failed` | Mechanical actions the agent took |
| **What the run cost** | `cost_recorded`, `model_turn_ended.usage` | Resource accounting |

Interpretive narrative (the supervisor saying "this is a SuspiciousWriteDetected") is a post-hoc concern — annotation of saved trajectories, not a runtime event class. v0.1 deliberately leaves this out of the wire.

---

## 12. Event reference

All non-RPC-request event types are past-tense facts. Event `type` values are reverse-DNS, namespaced under `avp.*`.

| Type | Source(s) | One-line semantics |
|---|---|---|
| `avp.run_requested` | `avp://supervisor` | First event. Agent-relayed; supervisor-attributed. Anchors the run with `avp.commission` (full Commission snapshot) + `avp.supervisor.name`. See §3.1. |
| `avp.agent_described` | `avp://agent` | Second event. The agent's self-published manifest (`avp.manifest`) — same payload `<agent> describe` prints. See §3.1. |
| `avp.agent_started` | `avp://agent` | Third event. Merged view: what the model will actually see, after Commission × resolution × SDK enrichment. |
| `avp.agent_stopped` | `avp://agent` | Run has ended; last event of the trajectory. |
| `avp.managed_ref_resolved` | `avp://agent` | One per Commission-declared managed ref the agent successfully resolved at startup. See §6. |
| `avp.managed_ref_resolve_failed` | `avp://agent` | Resolver returned an error or could not be reached for one of the Commission's managed refs. Agent stops fail-fast. See §6. |
| `avp.model_turn_started` | `avp://agent` | About to call the model. |
| `avp.model_turn_ended` | `avp://agent` | Model response received. Carries OTel `gen_ai.usage.*`. |
| `avp.tool_invoked` | `avp://agent` | Model invoked a tool. |
| `avp.tool_returned` | `avp://agent` | Tool produced a result (or was rejected). |
| `avp.tool_failed` | `avp://agent` | Tool raised an execution error. |
| `avp.subagent_invoked` | `avp://agent` | Parent agent delegated to a declared subagent (see §9.5). Frame span opens. Carries `avp.subagent.run_id` for managed subagents. |
| `avp.subagent_returned` | `avp://agent` | Subagent returned to its parent. Frame span closes; pairs with `subagent_invoked` by `span_id`. |
| `avp.subagent_failed` | `avp://agent` | Subagent invocation errored; the model receives an `Error: …` tool_result. |
| `avp.text_emitted` | `avp://agent` | Assistant text content. |
| `avp.reasoning_emitted` | `avp://agent` | Reasoning / thinking block (extended thinking, o-series reasoning). Distinct from text so consumers can filter chain-of-thought. |
| `avp.refusal_recorded` | `avp://agent` | Model declined the turn. Run terminates with `avp.agent_stopped.avp.reason="refused"`. |
| `avp.cost_recorded` | `avp://agent` | Cumulative `RunStateSnapshot` snapshot. May carry `avp.cost.source="reported"` on the reconciliation event when the API/SDK hands back an authoritative cost total. |
| `avp.skill_loaded` | `avp://agent` | SKILL.md loaded into context. |
| `avp.error_occurred` | `avp://agent` | Non-tool error. |
| `avp.mcp_server_connected` | `avp://agent` | Connection established to an MCP server (resolved from a `Commission.mcp_servers[].ref`). |
| `avp.mcp_server_disconnected` | `avp://agent` | Connection to an MCP server closed. |

Field-level definitions are in [`avp.schema.json`](./avp.schema.json) and [`event.schema.json`](./event.schema.json) (auto-generated from the Pydantic models in `python/avp/src/avp/types.py`).

### 12.1 `agent_stopped` convenience aliases

`agent_stopped.data` carries `avp.total_tokens`, `avp.total_cost_usd`, `avp.total_turns`, and `avp.duration_ms` at the top level **as convenience aliases**. When non-null they MUST equal the matching field inside `avp.state` (a [`RunStateSnapshot`](./avp.schema.json#/$defs/RunStateSnapshot)). New consumers SHOULD read `avp.state.*` — the same shape ships on every `cost_recorded` event, so analytics code that targets `avp.state` works uniformly across the run timeline rather than special-casing the terminator. The top-level fields are scheduled for removal in v0.2.

---

## 13. Custom event types and vendor extensions

Any `type` value not in the `avp.*` namespace is a custom event. Implementations MAY emit custom events. Consumers MUST:

- Validate them against the CloudEvents 1.0 envelope shape — `specversion`, `id`, `source`, `type`, `time`, `data` MUST be present.
- Pass them through without error if they do not recognize the `type`.

Implementers SHOULD use reverse-DNS `type` values (e.g. `com.example.deploy_completed`) to avoid future conflicts. The `avp.*` namespace is reserved.

For **non-spec fields within a known event type**: place them inside `data` under a vendor-namespaced key (e.g., `vendor.priority`, `acme.region`). The reference parser allows extra keys to round-trip through `data` verbatim, so vendor extensions don't require a separate envelope.

---

## 14. Conformance

### 14.1 Agent

An agent is conforming if and only if all of the following hold:

1. It reads exactly one valid `Commission` (per `commission.schema.json`) before emitting any events.
2. The trajectory MUST open with the prelude defined in §3.1: `avp.run_requested` (source=`avp://supervisor`), then `avp.agent_described` (source=`avp://agent`), then `avp.agent_started` (source=`avp://agent`), in that exact order. `avp.run_requested.data["avp.commission"]` MUST carry a faithful snapshot of the Commission the supervisor handed in (including managed refs verbatim). `avp.agent_described.data["avp.manifest"]` MUST equal the manifest payload the agent publishes via its pre-flight `describe` surface for the same agent build. `avp.agent_started` MUST include `prompt` when available. The `data.tools` field MUST list the EFFECTIVE tool surface — agent built-in tools plus any MCP-server tools surfaced after `mcp_server_connected`.
3. Every event it emits MUST conform to the CloudEvents 1.0 envelope shape (`specversion`, `id`, `source`, `type`, `time`, `data`). All v0.1 events EXCEPT `avp.run_requested` MUST set `source: "avp://agent"`. `avp.run_requested` is the only event with `source: "avp://supervisor"` — agent-relayed; the agent stamps the source URI from `Commission.supervisor`.
4. For every model inference, it MUST emit `avp.model_turn_started` immediately before the request and `avp.model_turn_ended` immediately after the response.
5. For every tool call, it MUST emit `avp.tool_invoked` before invocation and either `avp.tool_returned` (success or rejection) or `avp.tool_failed` (execution error) afterward.
6. It MUST emit `avp.cost_recorded` at least once per turn. The `data["avp.state"]` field MUST validate against `RunStateSnapshot`.
7. The last event it emits MUST be `avp.agent_stopped` (source=`avp://agent`). After emitting `agent_stopped`, the agent MUST NOT emit additional events.
8. All emitted events MUST validate against `event.schema.json`.

If the Commission carries any managed assets (`mcp_servers`, `skills`, or `subagents` non-empty), the agent additionally MUST:

R1. Read `AVP_RESOLVER_URL` from its environment. If absent or empty, emit `avp.error_occurred(code: "resolver_not_configured")` + `avp.agent_stopped(reason: "error")` before any model turn.
R2. Call `avp.resolve` (§6) once per `Commission.{mcp_servers,skills,subagents}[]` entry, between `agent_started` and the first `model_turn_started`.
R3. Emit `avp.managed_ref_resolved` after each successful resolution. Emit `avp.managed_ref_resolve_failed` and `avp.agent_stopped(reason: "error")` on any resolver error before any model turn.
R4. For supervisor-managed subagent invocations, call `avp.spawn_subagent` (§6.3), set `subagent_invoked.data["avp.subagent.run_id"]` to the returned child `run_id`, and roll the child's `usage` into the parent's `RunStateSnapshot` as if it were a local subagent.

If `Commission.mcp_servers` is non-empty, the agent additionally MUST:

M1. Emit `avp.mcp_server_connected` for each Commission-declared MCP server after resolving its ref and dialing the resolved endpoint, before the first turn. The connected event SHOULD carry the live tool catalog (`data.avp.mcp.tools[]`) returned by MCP's `tools/list`.
M2. Emit `avp.mcp_server_disconnected` for each connected MCP server before `avp.agent_stopped`.
M3. Dispatch `tools/call` for any model-invoked tool whose name is hosted by an MCP server through that server, tagging `tool_invoked.data["avp.tool.dispatch_target"] = "mcp_server"` and `avp.mcp_server_id` matching the Commission entry's `id`.

If asset-id collisions exist between agent-internal contributions and Commission-declared entries (or between distinct Commission entries), the agent MUST emit `avp.error_occurred(code: "commission_collision")` and stop before any model turn.

If `Commission.enabled_builtin_tools`, `enabled_builtin_subagents`, or `enabled_builtin_skills` is non-null, the agent additionally MUST (§9.2):

A1. Validate every name in each allowlist against the corresponding `manifest.built_in_*` list. Names that don't match emit `avp.error_occurred(code: "commission_collision")` and `avp.agent_stopped(reason: "error")` before any model turn.
A2. Filter the model-facing surface in `agent_started.data.tools[]` / `data.subagents[]` / `data.skills[]` so disabled built-ins do not appear.
A3. Reject runtime invocations of disabled built-ins by emitting `avp.tool_failed` after `avp.tool_invoked` (or `avp.subagent_failed` after `avp.subagent_invoked`) and not executing the built-in.

### 14.2 Supervisor

A supervisor is conforming if and only if all of the following hold:

1. The `Commission` it sends validates against `commission.schema.json`.
2. After sending the `Commission`, the supervisor sends nothing else over the Commission/event transport. v0.1 has no supervisor → agent push channel.
3. If the `Commission` carries any `mcp_servers`, `skills`, or `subagents`, the supervisor MUST stand up a resolver service the agent can reach (and configure the agent's environment with `AVP_RESOLVER_URL` accordingly). The resolver MUST implement the `avp.resolve` method per §6.2; `avp.spawn_subagent` per §6.3 is required iff the Commission carries `subagents`.

---

## 15. Deployment scope

AVP defines the **wire format**, not the deployment topology. The following are explicitly **out of scope**, and implementations choose:

- **Workspace provisioning.** What directory the agent runs in, how files (reference data, source trees) get there, and how it's cleaned up after — git checkout, container volume mount, tmpdir, NFS share, etc.
- **Secret injection.** How API keys and credentials reach the agent process and the resolver service (env vars, secrets manager, mounted files).
- **MCP server hosting.** Where supervisor-declared MCP servers run, how they're discovered, how they're scaled. The supervisor's resolver knows where each ref points; AVP records the dispatch.
- **Resolver hosting.** Where `AVP_RESOLVER_URL` points, how it authenticates, how it scales. Same trust boundary as the agent process — the supervisor configures both.
- **Agent placement.** Local subprocess, Docker container, remote VM, serverless function, browser sandbox.
- **OS-level sandboxing.** seccomp, AppArmor, cgroups, network policies, filesystem capabilities.
- **Authentication of the supervisor↔agent channel** beyond what stdio / HTTP transports inherit from their environment.

The agent's **workspace** is conventionally the agent's current working directory (CWD). Tool inputs containing relative paths resolve there. The supervisor's deployment layer — whatever it is — is responsible for ensuring referenced files exist in that workspace before the run starts.

### 15.1 Pattern: pre-turn world refresh

A common temptation is "I want to update the agent's view of the world between turns" — re-read a config file, re-fetch a dashboard, inject the current build status. This is sometimes called *re-observation*. **AVP does not provide a hook for this**, by design — mid-run reach-in by the supervisor breaks the bounded-context guarantee that makes trajectories meaningful.

The supported pattern is to expose the world refresh as an **MCP-server tool** (§7, §9). The agent calls it; the supervisor's MCP server computes the current value; the agent records the MCP dispatch on the wire as `tool_invoked` / `tool_returned`. The agent decides when to refresh and which information to pull, the trajectory shows exactly what context informed each turn, and there's no asymmetry between driver-pattern and translator-pattern agents (both can call MCP tools cleanly).

This section names the lines so readers don't trip on them. A complete production deployment will involve more than this spec covers; that's by design.

---

## 16. Versioning

- `Commission.schema_version` MUST equal `"0.1"`.
- `agent_started.data["avp.schema_version"]` MUST equal `"0.1"`.
- Future minor versions MAY add new event types, fields, or enum values. They MUST NOT remove or repurpose existing ones.
- Future major versions MAY introduce breaking changes. Vendor-namespaced keys (`vendor.*`, `com.example.*`) inside `data` round-trip verbatim today (per §13), insulating extensions from spec drift.

An agent that receives a `Commission` with an unsupported `schema_version` MUST emit `avp.error_occurred` with `data["avp.error.code"]: "unknown"` and a descriptive message, then emit `avp.agent_stopped` with `data["avp.reason"]: "error"`.
