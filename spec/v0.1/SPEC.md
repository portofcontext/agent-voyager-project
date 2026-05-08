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
- **MCP 2025-11-25** for supervisor-side tool dispatch. Supervisors that want to expose tools to the model declare an MCP server in `Commission.mcp_servers[]`; the agent connects, lists tools, and dispatches calls via MCP. There is no AVP-flavored RPC.
- **Agent Skills** (agentskills.io) for `SKILL.md` files referenced by `Commission.skills[]`.
- **JSON Schema Draft 2020-12** for this specification's machine-readable form.

AVP-specific concepts — the **no-mid-run-reach-in topology** and the **trajectory-as-source-of-truth contract** — live under the `avp.*` attribute namespace.

See [`FOUNDATIONS.md`](../../FOUNDATIONS.md) for the full mapping rationale.

---

## 1. The seam

AVP defines exactly one boundary, between two roles, with **two unidirectional flows** crossing it:

- **Supervisor** — declares the agent's complete environment in a Commission sent at startup. MCP servers (the supervisor-side tool dispatch path). Skills. Subagents. The prompt. Once the Commission is sent, the supervisor observes the trajectory; it does not reach in.
- **Agent** — runs the agent inside the supervisor's environment. Emits a stream of facts (events) that the supervisor observes.

```
                                  agent's environment
                          (mcp_servers, skills, subagents, prompt)
                                              │
                                              ▼
   supervisor ──── Commission (one-time, setup) ──▶ agent
                                              │
                                              ▼
                                        runs the agent
                                              │
                                              ▼
   supervisor ◀────────── events (continuous, run-end) ────── agent
```

This is the v0.1 architectural choice: **control flows down at setup; observation flows up during the run.** No mid-run bidirectional negotiation. The agent's bounded context is intact because its environment was fully declared up front.

Tools the model invokes that aren't built into the agent are dispatched via **MCP** (declared in `Commission.mcp_servers[]`). MCP is its own protocol; AVP just observes — emit `mcp_server_connected` with the live tool catalog on connect, tag each `tool_invoked` / `tool_returned` pair with `avp.tool.dispatch_target = "mcp_server"`, and the rest is MCP's wire. There is no AVP-flavored RPC channel between supervisor and agent. See §6.

---

## 2. Message classes

| Class | Direction | Cardinality | Schema entry point |
|---|---|---|---|
| `Commission` | supervisor → agent | exactly one, at startup | [`commission.schema.json`](./commission.schema.json) |
| `Event` | agent → supervisor | streamed throughout the run | [`event.schema.json`](./event.schema.json) |

v0.1 has no supervisor → agent channel beyond the one-shot Commission. Supervisor-side tool dispatch goes through MCP (its own protocol, declared in `Commission.mcp_servers[]`); the supervisor never needs to push messages back to the agent.

---

## 3. The trajectory

The agent's stdout is the **canonical trajectory**. Every event is a CloudEvents 1.0 envelope (per §0). The `source` attribute is a URI that identifies the producer:

- **`source: "avp://agent"`** is the overwhelming majority of events — the agent emitting facts about what it did.
- **`source: "avp://supervisor"`** appears only on the trajectory's opening `avp.run_requested` event (agent-relayed from `Commission.supervisor`; see §3.1). v0.1 has no supervisor → agent channel — supervisors do not directly emit events.

Every event's `data` payload carries an OpenTelemetry **span triple** — `trace_id` (16 random bytes, 32 lowercase hex chars), `span_id` (8 random bytes, 16 hex chars), and `parent_span_id` (or 16 zeros for the root). The agent span is the run; turn / tool spans nest inside it. Consumers reconstruct the trajectory as a span tree.

### 3.1 Run prelude

Every conforming trajectory opens with three events, in this exact order:

```
1. avp.run_requested      source=avp://supervisor   (agent-relayed)
2. avp.agent_described   source=avp://agent
3. avp.agent_started      source=avp://agent
```

These are distinct facts the wire records before the agent runs:

- **`avp.run_requested`** anchors the run. The agent emits it from `Commission.supervisor` with `source: avp://supervisor` — agent-relayed; the agent stamps the source URI to attribute the run to the originating supervisor build. `data.avp.config` carries the full Commission snapshot the supervisor handed in, so an auditor reading the trajectory can re-derive the run's input surface without an external Commission registry. `data.avp.supervisor.name` and the optional `data.avp.supervisor.version` complete the attribution.

- **`avp.agent_described`** is the agent's "whoami" — its self-published manifest of everything triggerable without supervisor configuration: SDK preset tools, runtime-bundled subagents, runtime-bundled skills, plus the agent's name, version, and supported AVP spec version. The payload (`data.avp.agent`) MUST equal what `<agent> describe` prints to stdout for the same agent build. This makes the audit trail and pre-flight introspection two views of the same fact.

- **`avp.agent_started`** is unchanged in role: the merged-view event, listing what the model will actually see for this specific run (Commission-declared tools/skills/subagents combined with SDK enrichment captured post-`client.connect()`).

`run_requested` and `agent_described` are root-level in the span tree (`parent_span_id = ZERO`). They do NOT pair (each owns its own span); `agent_started` owns the agent span that all subsequent run events nest under.

A agent that cannot identify itself (no manifest available) MUST NOT skip the prelude — instead, emit `agent_described` with the smallest valid manifest it can publish (its own package name, version, and `avp_spec_version`). A supervisor that omits `Commission.supervisor` MUST still see `run_requested` emitted, with `avp.supervisor.name="unknown"`.

---

## 4. Conformance — overview

A **agent** is conforming if it reads exactly one valid `Commission` at startup, runs the agent inside the declared environment per §9, and emits the events required by §10–§11. See §13.1 for the full checklist.

A **supervisor** is conforming if every `Commission` it sends validates against `commission.schema.json`. v0.1 has no supervisor → agent channel — there are no other messages a supervisor sends. See §13.2.

---

## 5. Transports

A conforming implementation MUST support at least one transport. Both transports use the same JSON Schemas; only the framing differs.

### 5.1 stdio (local)

- The supervisor launches the agent as a subprocess.
- The supervisor MUST write a single `Commission` JSON document to the agent's stdin, terminated by `\n`.
- The agent MUST read exactly one `Commission` from stdin before emitting any events.
- After reading `Commission`, stdin is unused — v0.1 has no supervisor → agent channel. Supervisors that want to expose tools to the model do it via `Commission.mcp_servers[]` (an MCP server, stdio or HTTP, in-process or external).
- The agent MUST emit `Event` documents to stdout as NDJSON, one JSON object per line, no pretty-printing, terminated by `\n`. The agent MUST flush stdout after each line.

### 5.2 HTTP (remote)

- The supervisor POSTs a single `Commission` to start a run; the agent streams events back via Server-Sent Events.
- No back-channel. Tool dispatch in HTTP transport works exactly as in stdio: through MCP, declared in `Commission.mcp_servers[]`.

---

## 6. Tool dispatch via MCP

v0.1 has one mechanism for supervisor-side tool dispatch: **MCP**
([Model Context Protocol](https://modelcontextprotocol.io/), 2025-11-25).
The supervisor stands up an MCP server (stdio or HTTP, in-process or
external) and declares it in `Commission.mcp_servers[]`. The agent connects,
runs MCP's `initialize` + `tools/list`, and dispatches `tools/call` against
the server when the model invokes one of those tools.

This means there is no AVP-flavored RPC channel between supervisor and
agent. Everything tool-related rides on the existing MCP wire — the same
protocol your editor, IDE plugin, or other agent runtime is already
speaking. AVP's contribution at the tool-dispatch layer is purely
observational: emit `avp.mcp_server_connected` with the live tool catalog
on connect, emit `avp.mcp_server_disconnected` on close, and tag each
`tool_invoked` / `tool_returned` pair with `avp.tool.dispatch_target =
"mcp_server"` so consumers can correlate.

Tools the agent ships in-process (e.g. avp-anthropic's
`bash`/`read_file`/`write_file`) are agent-package built-ins. They appear
on the manifest (`agent_described.data.avp.agent.built_in_tools`) and on
`agent_started.data.tools` with `avp.tool.dispatch_target = "local"`. The
agent runs them directly; no MCP layer involved.

The result: two well-defined dispatch paths for any tool the model can
call — `local` (compiled into the agent) or `mcp_server` (declared in
Commission). Nothing else.

---

## 7. Verifiers (deferred)

v0.1 does not specify verifiers. The deterministic-checks-at-trigger-points
concept was carried in early drafts and is removed here so v0.1 stays narrowly
focused on observation and tool dispatch. A future revision may reintroduce
verifiers (or a slimmer "pre-tool gate" surface) once the wire-level shape has
settled. Until then, supervisors that want gating wire it externally — by
running the agent inside a constrained workspace, by exposing only safe RPC
tools, or by reviewing the trajectory after the fact.

---

## 8. Tools

v0.1 has two paths for any tool the model can call:

1. **Agent built-in.** Compiled into the agent package. Examples: avp-anthropic's `bash`/`read_file`/`write_file`, avp-claude-agent's `Read`/`Edit`/`Bash`/etc. Surfaced in the agent's manifest (`agent_described.data.avp.agent.built_in_tools`) and in `agent_started.data.tools[]` with `avp.tool.dispatch_target = "local"`. The agent runs them directly.
2. **MCP server.** Declared by the supervisor in `Commission.mcp_servers[]`. The agent connects, runs MCP's `tools/list`, and dispatches calls via MCP's `tools/call`. Surfaced on `mcp_server_connected.data.avp.mcp.tools[]` (live tool catalog) and on `agent_started.data.tools[]` with `avp.tool.dispatch_target = "mcp_server"` and `avp.mcp_server_id` matching the Commission entry.

Wire flow:

1. Model calls a tool. Agent emits `avp.tool_invoked`.
2. Agent dispatches: locally for built-ins, via MCP for MCP-server tools.
3. Agent emits `avp.tool_returned` (or `avp.tool_failed`).

There is no AVP-flavored RPC channel. v0.1 does not define `Commission.tools`; supervisors that want to expose Python (or shell, or HTTP-backed) tools wrap them in an MCP server.

**`avp.tool.dispatch_target`.** Every `tool_invoked` event MAY carry `avp.tool.dispatch_target` discriminating the implementation that handled the call:

| Value | Meaning |
|---|---|
| `mcp_server` | Tool was dispatched by an MCP server. The event also carries `avp.mcp_server_id` matching a `Commission.mcp_servers[].id`. |
| `local` | Tool ran in-process. Also used for inline server-side tools the API ran during a single `messages.create()` (e.g. Anthropic's hosted `web_search`, `code_execution`); those events carry `avp.tool.subtype` naming the hosted-tool kind. |

Supervisors building dashboards / audits filter on `dispatch_target` to count tool calls by implementation route, and on `avp.mcp_server_id` / `avp.tool.subtype` to break down further.

### 8.1 Restricting the exposed tool set: `Commission.allowed_tools`

`Commission.allowed_tools` is an **optional allowlist** of tool names the agent exposes to the model. It is the supervisor's lever for narrowing the agent's tool surface without enumerating the agent's internals.

Semantics:

- **Absent.** The agent exposes all of its built-ins plus every MCP-server tool. This is the default, backwards-compatible behavior.
- **Present.** The agent MUST expose ONLY tools whose names are in this list. Agent built-ins, MCP-server tools, and `Commission.subagents[]` entries are all filtered through it.
- **Unrecognized names.** Names in `allowed_tools` that match neither a agent built-in nor an MCP-server tool nor a `Commission.subagents[]` entry are agent-specific. The agent MAY validate them at startup; failing that, the runtime check rejects any actual call to such a name as `tool_failed` (see below).
- **Runtime rejection.** If the model nevertheless calls a tool whose name is not in `allowed_tools`, the agent MUST emit `tool_failed` with an error message identifying the allowlist as the cause, and MUST NOT execute the tool. (`tool_invoked` is still emitted first to keep the trajectory faithful — the agent attempted the call.)

Supervisors MAY maintain category-based profiles (e.g., "DDD-strict", "Compliance") at the framework layer that resolve to a specific `allowed_tools` per agent; AVP itself takes no opinion on profiles.

---

## 8.5 Subagents

`Commission.subagents[]` declares **delegate agents** the parent agent may invoke by name. A Subagent is a top-level Commission primitive alongside `mcp_servers` and `skills` — the supervisor declares the full set up front (no mid-run reach-in); the parent agent picks one to delegate to at runtime. The shape mirrors `Commission` itself: each Subagent carries its own `system_prompt`, `model`, `mcp_servers`, `skills`, `output_schema` — the environment slice the subagent runs inside.

Field-level definitions live in [`commission.schema.json#/$defs/Subagent`](./commission.schema.json) (auto-generated). v0.1 specifies the wire and lifecycle; richer dispatch (tools-inside-subagents, recursion, verifier cascade) is specified but not required to be exercised by the prototype agents.

**Wire flow.**

1. Model invokes a tool whose name matches a `Commission.subagents[].name`. Agent emits `avp.subagent_invoked` (NOT `avp.tool_invoked`). The event's `data.span_id` is the **frame span** for this invocation.
2. Agent runs the subagent within the declared environment slice. Any nested events the subagent emits (model turns, tool calls, text) MUST set `data.parent_span_id` to the frame span (or descend from it transitively). The trajectory reconstructs as one tree.
3. Agent emits `avp.subagent_returned` carrying `data.avp.subagent.result.text` plus a `RunStateSnapshot` rollup at `data.avp.subagent.usage`. The `data.span_id` MUST equal the matching `subagent_invoked.data.span_id` so consumers pair them.
4. If invocation fails (no driver wired, exception, or driver reported error), agent emits `avp.subagent_failed` with `data.avp.subagent.error` instead of `subagent_returned`. The model receives an `Error: …` tool_result for symmetry with §8 step 4.
5. The subagent's spend (cost, tokens) MUST be rolled into the parent run's cumulative `RunStateSnapshot`. Per-subagent attribution is preserved on `subagent_returned.data.avp.subagent.usage`.

**Two observability modes.** Agents MAY expose subagent internals at different fidelity:

- **Transparent.** The agent owns the sub-loop (driver pattern) and emits `model_turn_*` / `tool_*` / `text_emitted` for the subagent, parented under the frame span. Consumers see the full nested span tree.
- **Opaque.** The agent delegates to an SDK that doesn't surface subagent internals (translator pattern). Only `subagent_invoked` and `subagent_returned` are emitted; the wire shape is "thin" but well-formed. Consumers MUST NOT assume the absence of nested events implies the subagent ran trivially — only that this agent cannot observe the internals.

Both modes produce the same outer wire shape; the second is a strict subset of the first.

**Subagent ↔ tool collision.** Subagent names MUST NOT collide with agent built-in tool names. A collision is a configuration conflict — the agent MUST detect this at startup, emit `error_occurred`, and stop with `reason: "error"` before any model turn runs.

**`allowed_tools` applies to subagents.** When `Commission.allowed_tools` is set, every name in `Commission.subagents[]` MUST also appear there. The model-facing surface is one allowlist over agent built-ins, MCP-server tools, and subagents alike.

**`agent_started.data.subagents`.** When `Commission.subagents` is non-empty, the agent MUST surface the model-facing subagent declaration on `agent_started.data.subagents[]` (parallel to `data.tools[]` and `data.skills[]`). Each entry carries `name`, `description`, and optional `inputSchema` (MCP-shaped). Consumers can read this without parsing the Commission a second time.

---

## 9. The agent loop (normative)

A conforming agent MUST behave as if executing the following algorithm. (The agent MAY reorder operations that are not externally observable, provided the emitted event sequence is indistinguishable.)

### 9.1 Run state and the definition of a turn

A **turn** in AVP is exactly one `model_turn_started` / `model_turn_ended`
pair where the model produced new output (either text or tool calls or
both). Continuations and SDK-internal restatements that do not represent a
fresh model call MUST NOT be counted as turns.

This matters most for translator-pattern agents wrapping SDKs that emit
"assistant message" objects for things that aren't fresh model calls (e.g.,
follow-up wrappers around tool results). Translator agents MUST count an
event as a turn only when the SDK-reported usage carries non-zero new
output tokens (delta-output > 0), or — if the SDK doesn't report per-call
usage — when the message includes content the model itself produced.

The agent maintains a `RunStateSnapshot` (see [`avp.schema.json#/$defs/RunStateSnapshot`](./avp.schema.json)) tracking `total_turns`, `total_cost_usd`, `total_tokens`, etc. The snapshot is observability — it travels on `cost_recorded` and `agent_stopped` so consumers can trace cumulative spend, but v0.1 does not specify caps that the agent must enforce against it.

### 9.2 The loop

```
read config from stdin
emit run_requested  (source=avp://supervisor, agent-relayed)
emit agent_described
emit agent_started
emit skill_loaded for each loaded skill

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
        else:
            output = execute_tool_locally(input)
        emit tool_returned(call_id, output)

    if model converged:
        emit agent_stopped("converged"); return
```

### 9.3 Cost / token accounting rules (normative)

- `cost_usd` on `model_turn_ended` is the BILLABLE cost (post-cache-discount).
- `tokens_input` on `model_turn_ended` is the total input tokens INCLUDING cache-read tokens.
- `tokens_cache_read` and `tokens_cache_write` are informational; they MUST NOT alter `state.total_tokens` independently.
- `state.total_cost_usd` and `state.total_tokens` are monotonically non-decreasing.
- **Translator agents over cumulative-usage SDKs.** Some SDKs (notably the Claude Agent SDK) report usage as a running session total per message rather than as a per-call delta. Translators MUST derive deltas (subtract previous cumulative) to populate per-turn `tokens_*` and `cost_usd` correctly. When the SDK's cumulative drops without warning (`cum < prev`), the translator MUST emit `error_occurred` with `code: "accounting_reset"` rather than silently clamping; consumers cannot distinguish a swallowed delta from a legitimate quiet turn otherwise. SDKs that signal context compaction or sub-agent dispatch via lifecycle events SHOULD be hooked so the translator resets its baselines deliberately, not via the error path.

---

## 10. Two classes of trajectory facts

The trajectory holds two semantically distinct kinds of facts. Implementations and supervisor frameworks SHOULD surface them separately to consumers:

| Class | Event types | Semantics |
|---|---|---|
| **What the agent did** | `model_turn_*`, `tool_invoked`, `tool_returned`, `tool_failed`, `text_emitted` | Mechanical actions the agent took |
| **What the run cost** | `cost_recorded`, `model_turn_ended.usage` | Resource accounting |

Interpretive narrative (the supervisor saying "this is a SuspiciousWriteDetected") is a post-hoc concern — annotation of saved trajectories, not a runtime event class. v0.1 deliberately leaves this out of the wire.

---

## 11. Event reference

All non-RPC-request event types are past-tense facts. `*_request` events keep imperative form because they ARE pending RPCs. Event `type` values are reverse-DNS, namespaced under `avp.*`.

| Type | Source(s) | One-line semantics |
|---|---|---|
| `avp.run_requested` | `avp://supervisor` | First event. Agent-relayed; supervisor-attributed. Anchors the run with `avp.config` (full Commission snapshot) + `avp.supervisor.name`. See §3.1. |
| `avp.agent_described` | `avp://agent` | Second event. The agent's self-published manifest (`avp.agent`) — same payload `<agent> describe` prints. See §3.1. |
| `avp.agent_started` | `avp://agent` | Third event. Merged view: what the model will actually see, after Commission × SDK enrichment. |
| `avp.agent_stopped` | `avp://agent` | Run has ended; last event of the trajectory. |
| `avp.model_turn_started` | `avp://agent` | About to call the model. |
| `avp.model_turn_ended` | `avp://agent` | Model response received. Carries OTel `gen_ai.usage.*`. |
| `avp.tool_invoked` | `avp://agent` | Model invoked a tool. |
| `avp.tool_returned` | `avp://agent` | Tool produced a result (or was rejected). |
| `avp.tool_failed` | `avp://agent` | Tool raised an execution error. |
| `avp.subagent_invoked` | `avp://agent` | Parent agent delegated to a declared subagent (see §8.5). Frame span opens. |
| `avp.subagent_returned` | `avp://agent` | Subagent returned to its parent. Frame span closes; pairs with `subagent_invoked` by `span_id`. |
| `avp.subagent_failed` | `avp://agent` | Subagent invocation errored; the model receives an `Error: …` tool_result. |
| `avp.text_emitted` | `avp://agent` | Assistant text content. |
| `avp.reasoning_emitted` | `avp://agent` | Reasoning / thinking block (extended thinking, o-series reasoning). Distinct from text so consumers can filter chain-of-thought. |
| `avp.refusal_recorded` | `avp://agent` | Model declined the turn. Run terminates with `avp.agent_stopped.avp.reason="refused"`. |
| `avp.cost_recorded` | `avp://agent` | Cumulative `RunStateSnapshot` snapshot. May carry `avp.cost.source="reported"` on the reconciliation event when the API/SDK hands back an authoritative cost total. |
| `avp.skill_loaded` | `avp://agent` | SKILL.md loaded into context. |
| `avp.skill_executed` | `avp://agent` | Skill activated. |
| `avp.error_occurred` | `avp://agent` | Non-tool error. |
| `avp.mcp_server_connected` | `avp://agent` | Connection established to a Commission-declared MCP server. |
| `avp.mcp_server_disconnected` | `avp://agent` | Connection to an MCP server closed. |

Field-level definitions are in [`avp.schema.json`](./avp.schema.json) and [`event.schema.json`](./event.schema.json) (auto-generated from the Pydantic models in `python/avp/src/avp/types.py`).

### 11.1 `agent_stopped` convenience aliases

`agent_stopped.data` carries `avp.total_tokens`, `avp.total_cost_usd`, `avp.total_turns`, and `avp.duration_ms` at the top level **as convenience aliases**. When non-null they MUST equal the matching field inside `avp.state` (a [`RunStateSnapshot`](./avp.schema.json#/$defs/RunStateSnapshot)). New consumers SHOULD read `avp.state.*` — the same shape ships on every `cost_recorded` event, so analytics code that targets `avp.state` works uniformly across the run timeline rather than special-casing the terminator. The top-level fields are scheduled for removal in v0.2.

---

## 12. Custom event types and vendor extensions

Any `type` value not in the `avp.*` namespace is a custom event. Implementations MAY emit custom events. Consumers MUST:

- Validate them against the CloudEvents 1.0 envelope shape — `specversion`, `id`, `source`, `type`, `time`, `data` MUST be present.
- Pass them through without error if they do not recognize the `type`.

Implementers SHOULD use reverse-DNS `type` values (e.g. `com.example.verifier_result`) to avoid future conflicts. The `avp.*` namespace is reserved.

For **non-spec fields within a known event type**: place them inside `data` under a vendor-namespaced key (e.g., `vendor.priority`, `acme.region`). The reference parser allows extra keys to round-trip through `data` verbatim, so vendor extensions don't require a separate envelope.

---

## 13. Conformance

### 13.1 Agent

A agent is conforming if and only if all of the following hold:

1. It reads exactly one valid `Commission` (per `commission.schema.json`) before emitting any events.
2. The trajectory MUST open with the prelude defined in §3.1: `avp.run_requested` (source=`avp://supervisor`), then `avp.agent_described` (source=`avp://agent`), then `avp.agent_started` (source=`avp://agent`), in that exact order. `avp.run_requested.data.avp.config` MUST carry a faithful snapshot of the Commission the supervisor handed in. `avp.agent_described.data.avp.agent` MUST equal the manifest payload the agent publishes via its pre-flight `describe` surface for the same agent build. `avp.agent_started` MUST include `prompt` when available. The `data.tools` field MUST list the EFFECTIVE tool surface — the agent's built-in tools, filtered by `Commission.allowed_tools` if set, plus any MCP-server tools surfaced post-`mcp_server_connected`. Each tool entry MUST include `name`.
3. Every event it emits MUST conform to the CloudEvents 1.0 envelope shape (`specversion`, `id`, `source`, `type`, `time`, `data`). All v0.1 events EXCEPT `avp.run_requested` MUST set `source: "avp://agent"`. `avp.run_requested` is the only event with `source: "avp://supervisor"` — agent-relayed; the agent stamps the source URI from `Commission.supervisor`.
4. For every model inference, it MUST emit `avp.model_turn_started` immediately before the request and `avp.model_turn_ended` immediately after the response.
5. For every tool call, it MUST emit `avp.tool_invoked` before invocation and either `avp.tool_returned` (success or rejection) or `avp.tool_failed` (execution error) afterward.
6. It MUST emit `avp.cost_recorded` at least once per turn. The `data["avp.state"]` field MUST validate against `RunStateSnapshot`.
7. The last event it emits MUST be `avp.agent_stopped` (source=`avp://agent`). After emitting `agent_stopped`, the agent MUST NOT emit additional events.
8. All emitted events MUST validate against `event.schema.json`.

If `Commission.mcp_servers` is non-empty, the agent additionally MUST:

M1. Emit `avp.mcp_server_connected` for each declared MCP server before the first turn. The connected event SHOULD carry the live tool catalog (`data.avp.mcp.tools[]`) returned by MCP's `tools/list`.
M2. Emit `avp.mcp_server_disconnected` for each connected MCP server before `avp.agent_stopped`.
M3. Dispatch `tools/call` for any model-invoked tool whose name is hosted by an MCP server through that server, tagging `tool_invoked.data["avp.tool.dispatch_target"] = "mcp_server"` and `avp.mcp_server_id` matching the Commission entry.

If `Commission.allowed_tools` is set, the agent additionally MUST:

A1. Verify that every `Commission.subagents[]` name appears in `Commission.allowed_tools`. If any does not, emit `avp.error_occurred` and `avp.agent_stopped` with `data["avp.reason"]: "error"` before running any model turn (§8.1).
A2. Reject any tool call whose `tool` name is not in `Commission.allowed_tools` by emitting `avp.tool_failed` (after `avp.tool_invoked`) and not executing the tool.

### 13.2 Supervisor

A supervisor is conforming if and only if all of the following hold:

1. The `Commission` it sends validates against `commission.schema.json`.
2. After sending the `Commission`, the supervisor sends nothing else over stdio (or the equivalent transport channel). v0.1 has no agent → supervisor RPC channel.

---

## 14. Deployment scope

AVP defines the **wire format**, not the deployment topology. The following are explicitly **out of scope**, and implementations choose:

- **Workspace provisioning.** What directory the agent runs in, how files (reference data, source trees) get there, and how it's cleaned up after — git checkout, container volume mount, tmpdir, NFS share, etc.
- **Secret injection.** How API keys and credentials reach the agent process (env vars, secrets manager, mounted files).
- **MCP server hosting.** Where supervisor-declared MCP servers run, how they're discovered, how they're scaled. Supervisors that wrap their own tooling as an MCP server own the deployment story for it.
- **Agent placement.** Local subprocess, Docker container, remote VM, serverless function, browser sandbox.
- **OS-level sandboxing.** seccomp, AppArmor, cgroups, network policies, filesystem capabilities.
- **Authentication of the supervisor↔agent channel** beyond what stdio / HTTP transports inherit from their environment.

The agent's **workspace** is conventionally the agent's current working directory (CWD). Tool inputs containing relative paths resolve there. The supervisor's deployment layer — whatever it is — is responsible for ensuring referenced files exist in that workspace before the run starts.

### 14.1 Pattern: pre-turn world refresh

A common temptation is "I want to update the agent's view of the world between turns" — re-read a config file, re-fetch a dashboard, inject the current build status. This is sometimes called *re-observation*. **AVP does not provide a hook for this**, by design — mid-run reach-in by the supervisor breaks the bounded-context guarantee that makes trajectories meaningful.

The supported pattern is to expose the world refresh as an **MCP-server tool** (§6, §8). The agent calls it; the supervisor's MCP server computes the current value; the agent records the MCP dispatch on the wire as `tool_invoked` / `tool_returned`. The agent decides when to refresh and which information to pull, the trajectory shows exactly what context informed each turn, and there's no asymmetry between driver-pattern and translator-pattern agents (both can call MCP tools cleanly).

This section names the lines so readers don't trip on them. A complete production deployment will involve more than this spec covers; that's by design.

---

## 15. Versioning

- `Commission.schema_version` MUST equal `"0.1"`.
- `agent_started.data["avp.schema_version"]` MUST equal `"0.1"`.
- Future minor versions MAY add new event types, fields, or enum values. They MUST NOT remove or repurpose existing ones.
- Future major versions MAY introduce breaking changes. Vendor-namespaced keys (`vendor.*`, `com.example.*`) inside `data` round-trip verbatim today (per §12), insulating extensions from spec drift.

A agent that receives a `Commission` with an unsupported `schema_version` MUST emit `avp.error_occurred` with `data["avp.error.code"]: "unknown"` and a descriptive message, then emit `avp.agent_stopped` with `data["avp.reason"]: "error"`.
