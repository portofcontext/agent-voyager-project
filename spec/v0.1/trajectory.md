# AVP Trajectory Spec, v0.1

**Status:** Draft
**Stability:** beta. Wire shape, event catalog, and conformance criteria are stable; minor additive changes possible.
**Umbrella version:** v0.1 (see [`README.md`](./README.md))
**Schema:** [`trajectory.schema.json`](./trajectory.schema.json)
**$id base:** `https://avp.dev/schema/v0.1/`

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

---

## 1. Scope

The Trajectory Spec defines the **stream of events** an agent emits as it runs. It is independently implementable: an existing agent loop with its own run-config object can emit conforming AVP events without adopting [Commission](./commission.md), [Agent Descriptor](./agent-descriptor.md), or the [Resolver API](./resolver.md). When the other specs ARE adopted, this document describes how they compose into the event stream (the run prelude carries a Commission snapshot and an Agent Descriptor payload; managed-asset events record Resolver round-trips).

The trajectory holds two semantically distinct kinds of facts:

| Class | Event types | Semantics |
|---|---|---|
| **What the agent did** | `assistant_message` (carries `avp.content`, the model's content-block array for the turn), `tool_invoked`, `tool_returned`, `subagent_*`, `managed_ref_resolved`, `managed_ref_resolve_failed`, `mcp_server_connected`, `mcp_server_disconnected`, `error_occurred` | Mechanical actions the agent took |
| **What the run cost** | `assistant_message.gen_ai.usage.*`, `assistant_message.avp.cost_usd` | Resource accounting (per-turn deltas; consumer reduces). |
| **What the model output** | `assistant_message.avp.content: list[AVPContentBlock]` | Provider-agnostic content blocks (`text`, `thinking`, `tool_use`, `image`, `document`, `audio`, `video`, `refusal`, `server_tool_use`, `server_tool_result`). Reconstructing a provider message array is a direct read of this field per turn, paired with the `avp.tool_result` blocks on intervening `tool_returned` events to form the user-role tool-result messages. Block taxonomy: [`avp.content`](../../python/avp/src/avp/content.py). |

Interpretive narrative (the supervisor saying "this is a SuspiciousWriteDetected") is a post-hoc concern: annotation of saved trajectories, not a runtime event class. v0.1 deliberately leaves this out of the wire.

### 1.1 Non-goals

The Trajectory Spec explicitly does **not** define:

- **The Commission shape.** What a supervisor sends *to* the agent at startup → see [`commission.md`](./commission.md).
- **The Agent Descriptor shape.** What an agent advertises about itself → see [`agent-descriptor.md`](./agent-descriptor.md).
- **The wire protocol for dereferencing refs.** How `managed_ref_resolved` events come into being → see [`resolver.md`](./resolver.md).
- **Multi-run orchestration.** Cross-run correlation, scheduling, persistence, replay: supervisor-framework concerns above the wire.
- **Post-hoc training-data formats.** Trajectory is a live event stream; for SFT/RL logging see ATIF (`FOUNDATIONS.md` § *Adjacent prior art*).
- **Interpretive annotation.** Categorical judgments ("SuspiciousWriteDetected", "PolicyViolation") are post-hoc annotation, not runtime events.
- **Verifiers / pre-tool gates.** Deferred from v0.1; see umbrella README §5.

---

## 2. The trajectory

The agent's stdout is the **canonical trajectory**. Every event is a CloudEvents 1.0 envelope with `source: "avp://agent"`: the agent is the sole producer on the wire. Supervisor attribution, when applicable, lives in `run_requested.data["avp.commission"]` and `data["avp.supervisor.*"]` (see §2.1); v0.1 has no supervisor → agent push channel and supervisors do not directly emit events.

Every event's `data` payload carries an OpenTelemetry **span triple**: `trace_id` (16 random bytes, 32 lowercase hex chars), `span_id` (8 random bytes, 16 hex chars), and `parent_span_id` (or 16 zeros for the root). The agent span is the run; turn / tool / managed-ref-resolution spans nest inside it. Consumers reconstruct the trajectory as a span tree.

Every event's `data` payload MAY also carry **`avp.meta`**: an optional object (`dict[str, any]`) for agent- or caller-supplied annotations. Its contents are opaque to AVP; conformance validators MUST NOT assert on its values. Omit the key entirely when empty.

All `data` fields beyond the span triple (`trace_id`, `span_id`, `parent_span_id`) MUST be namespaced under a dotted prefix (e.g. `avp.*`, `gen_ai.*`, or a vendor-chosen namespace like `acme.*`). Un-namespaced keys are reserved for the span triple only.

### 2.1 Run prelude

A conforming trajectory opens with the **prelude**: a fixed-pair head, then optional resolver / connect / load events for managed and dialed assets, then a closing `agent_started` snapshot of the merged runtime state.

```
1. avp.run_requested
2. avp.agent_described
3. [avp.managed_ref_resolved]*    one per Commission-declared ref
4. [avp.mcp_server_connected]*    one per dialed server (descriptor's + Commission's)
5. avp.agent_started              merged-state snapshot
```

These are distinct facts the wire records before the agent's first model turn:

- **`avp.run_requested`** anchors the run. When relaying a Commission, the event carries the full Commission snapshot under `data["avp.commission"]` (refs verbatim, opaque to the agent) plus `data["avp.supervisor.name"]` (+ optional `version`) for attribution — making the trajectory self-contained for audit. Without a Commission (e.g. an agent invoked as a library by an application that does not adopt the Commission spec), those fields are absent; the event still anchors the run via `subject = run_id` and the span triple, and the agent's baked-in invocation surface is advertised on `agent_described.data["avp.descriptor"]` instead. See [`commission.md`](./commission.md) and [`agent-descriptor.md`](./agent-descriptor.md).

- **`avp.agent_described`** is the agent's self-published [Agent Descriptor](./agent-descriptor.md) of everything triggerable without supervisor configuration: SDK preset tools, runtime-bundled subagents, runtime-bundled skills, MCP servers it dials internally, plus the agent's name, version, and supported AVP spec version. The payload (`data["avp.descriptor"]`) MUST equal what `<agent> describe` prints to stdout for the same agent build. This makes the audit trail and pre-flight introspection two views of the same fact. v0.1-conforming agents implicitly speak the Resolver API; capability is implied by `avp_spec_version: "0.1"` rather than carried as a separate flag.

- **`avp.managed_ref_resolved`** fires once per Commission-declared managed ref (`Commission.mcp_servers[]`, `Commission.skills[]`, `Commission.subagents[]`), recording that the resolver round-trip happened. Descriptor entries are agent-internal — no ref, no round-trip, no event. See [`resolver.md`](./resolver.md).

- **`avp.mcp_server_connected`** fires once per MCP server the agent dials at startup (both descriptor's and Commission-managed). Carries the live tool catalog from MCP's `tools/list` under `data["avp.mcp.tools"]`. See §4.

- **`avp.agent_started`** is the **merged-state snapshot**: what the run will actually use, after the descriptor's catalog is filtered by Commission's `enabled_builtin_*` allowlists and combined with Commission's managed refs. `data` carries the settled `avp.prompt` / `avp.system_prompt` / `model` and the merged lists `avp.tools[]` (descriptor's local tools, post-allowlist), `avp.mcp_servers[]` (descriptor's filtered ∪ Commission's, identity only), `avp.skills[]`, `avp.subagents[]`. Per-server tool catalogs from MCP servers stay on the corresponding `mcp_server_connected` events; `agent_started.data["avp.mcp_servers"]` carries server identity only. Consumers join the two by id for the full per-server view.

**Span tree.** `run_requested` and `agent_described` are root-level (`parent_span_id = ZERO`). Each `managed_ref_resolved` and `mcp_server_connected` event in the prelude is also root-level — they record startup operations that happen before the agent's run span begins. `agent_started` opens the agent run span, which all subsequent run events nest under.

An agent that cannot identify itself (no Descriptor available) MUST NOT skip the prelude. Instead, emit `agent_described` with the smallest valid Descriptor it can publish (its own package name, version, and `avp_spec_version`). A Commission whose `supervisor` is omitted MUST still produce a `run_requested` with `data["avp.commission"]` present and `data["avp.supervisor.*"]` absent (absence, not `"unknown"`, is the canonical signal).

### 2.2 Resolution failures

If a managed-ref resolution fails (resolver unreachable, ref not understood by the resolver, content malformed), the agent MUST emit `avp.managed_ref_resolve_failed` for the failing entry and then `avp.agent_stopped(reason: "error")`. No further prelude events fire and no model turn runs. Resolution events do not re-record the opaque ref material; `run_requested.data["avp.commission"]` already carries it. Both success (`managed_ref_resolved`) and failure (`managed_ref_resolve_failed`) events record only that the round-trip happened (and how).

---

## 3. The agent loop (normative)

A conforming agent MUST behave as if executing the following algorithm. (The agent MAY reorder operations that are not externally observable, provided the emitted event sequence is indistinguishable.)

### 3.1 Run state and the definition of a turn

A **turn** in AVP is exactly one `assistant_message` event where the model produced new output (either text or tool calls or both). Continuations and SDK-internal restatements that do not represent a fresh model call MUST NOT be counted as turns.

This matters most for translator-pattern agents wrapping SDKs that emit "assistant message" objects for things that aren't fresh model calls (e.g., follow-up wrappers around tool results). Translator agents MUST count an event as a turn only when the SDK-reported usage carries non-zero new output tokens (delta-output > 0), or (if the SDK doesn't report per-call usage) when the message includes content the model itself produced.

The agent does NOT maintain a cumulative run-state on the wire. Each `assistant_message` carries per-turn deltas (`gen_ai.usage.*_tokens`, `avp.cost_usd`); consumers reduce the stream to compute totals. v0.1 does not specify caps the agent must enforce.

### 3.2 The loop

```
read commission from stdin (or in-process equivalent; may be absent)
emit run_requested
emit agent_described

# Startup resolve (Resolver API) — only Commission-declared refs.
# Descriptor entries are agent-internal and skip this step.
for each entry in commission.mcp_servers + commission.skills + commission.subagents:
    call avp.resolve(...)
    on success: emit managed_ref_resolved
    on failure: emit managed_ref_resolve_failed; emit agent_stopped("error"); return

# Materialize the resolved environment.
# MCP servers from both descriptor and Commission are dialed here.
for each mcp_server (descriptor's + Commission's): dial; emit mcp_server_connected
emit agent_started   # merged-state snapshot of everything above

loop:
    response = call_model()
    emit assistant_message(step, content=response.content_blocks, tokens_delta, cost_delta, ...)

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

### 3.3 Cost / token accounting rules (normative)

- `avp.cost_usd` on `assistant_message` is the per-turn billable cost (post-cache-discount). Cumulative totals are not on the wire; consumers reduce the stream.
- `gen_ai.usage.input_tokens` on `assistant_message` is the total input tokens INCLUDING cache-read tokens.
- `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.cache_creation.input_tokens` are informational and already accounted for inside `input_tokens`; consumers MUST NOT double-count them when summing.
- Per-turn deltas (`avp.cost_usd`, `gen_ai.usage.*_tokens`) are non-negative.
- Translator agents wrapping cumulative-usage SDKs (notably the Claude Agent SDK, which reports running session totals per message) derive per-turn deltas by subtracting the previous cumulative. Reset handling (e.g. cumulative drops after compaction or sub-agent dispatch) is an implementation detail of the translator; no specific error code is mandated.

---

## 4. Tool dispatch

v0.1 has two paths for any tool the model can call:

1. **Local.** Compiled into the agent package; declared on the agent's [Agent Descriptor](./agent-descriptor.md) under `tools`. The agent runs them directly. Surfaced on `agent_started.data["avp.tools"]` (post-`enabled_builtin_tools` filter).
2. **MCP server.** A server the agent dials at startup — either declared on the descriptor (`descriptor.mcp_servers[]`) or by the supervisor (`Commission.mcp_servers[]` as opaque `{id, ref}` pairs). The agent resolves Commission refs via the Resolver API, dials each server, runs MCP's `tools/list`, and dispatches calls via MCP's `tools/call`. Per-server tool catalogs surface on `mcp_server_connected.data["avp.mcp.tools"]`; the server's identity (`{id, description?}`) appears on `agent_started.data["avp.mcp_servers"]`. MCP-surfaced tools are **not** duplicated on `agent_started.data["avp.tools"]`.

Wire flow:

1. Model calls a tool. Agent emits `avp.tool_invoked`.
2. Agent dispatches: locally for tools listed in `descriptor.tools`; via MCP for tools surfaced by a connected MCP server.
3. Agent emits `avp.tool_returned` (`avp.tool_result.isError` discriminates success, rejection, and execution errors).

**Tool result shape.** The `avp.tool_result` field on `tool_returned` is an AVP [`ToolResultBlock`](../../python/avp/src/avp/content.py): `tool_use_id`, `content` (a string or a list of nested `text` / `image` / `document` blocks for providers that permit them), `structured_content` (an optional programmatic payload alongside the human-readable content, mirroring MCP's `structuredContent` / Gemini `function_response.response` / Bedrock `toolResult.content.json`), and `is_error`. `is_error` discriminates all outcomes: `false` (or absent) for success, `true` for rejections (tool declined by the agent) or execution errors, with the reason in `content[0].text`. During reconstruction this block becomes one entry of the next user-role message's content array.

There is no AVP-flavored RPC channel for tool dispatch. Supervisors that want to expose Python (or shell, or HTTP-backed) tools wrap them in an MCP server, declare the server's ref in `Commission.mcp_servers[]`, and have their resolver return the connection material when asked.

**`avp.tool.dispatch_target`.** Every `tool_invoked` event MAY carry `avp.tool.dispatch_target` discriminating the implementation that handled the call:

| Value | Meaning |
|---|---|
| `local` | Tool ran in the agent's own process: code compiled into the agent package (`descriptor.tools`). |
| `mcp_server` | Tool was dispatched by an MCP server. The event also carries `avp.mcp_server_id` matching an entry in `agent_started.data["avp.mcp_servers"]` (from either `descriptor.mcp_servers` or `Commission.mcp_servers`). |

### 4.1 Merge semantics: descriptor ∪ Commission

The agent's loop dispatches against a single bag of tools, regardless of whether each entry came from the descriptor or from a Commission-managed MCP server. The agent's runtime layer constructs the bag at startup:

1. Start with the agent's local tools (`descriptor.tools`, filtered by `Commission.enabled_builtin_tools`).
2. For each MCP server in `descriptor.mcp_servers` (filtered by `Commission.enabled_builtin_mcp_servers`) and `Commission.mcp_servers`, dial (resolve via Resolver API first for Commission refs), connect, and add the server's `tools/list` output to the dispatch table.
3. If any `id` collision exists between a descriptor-declared MCP server and a Commission-declared one, emit `error_occurred` with `data["avp.error.code"]: "commission_collision"` and stop. Configuration errors fail-fast.

Tool-name collisions across distinct MCP servers (e.g. agent-internal `github_v1` and Commission-managed `github_v2` both exposing `list_prs`) are an agent-runtime concern outside AVP's wire. The agent's MCP client surfaces names to the model however it normally does (most clients namespace by server id, e.g. `github_v1__list_prs`); AVP records the name the agent dispatched on in `tool_invoked.data["gen_ai.tool.name"]`.

---

## 5. Subagents

`Commission.subagents[]` declares **delegate agents** the parent agent may invoke by name, as `{id, ref}` pairs. The supervisor stands up the subagent as a managed asset; the parent agent only sees an opaque ref.

**Wire flow.**

1. At startup, the parent agent calls `avp.resolve` (Resolver API) for each `subagents[]` entry to obtain model-facing metadata (`name`, `description`, `inputSchema`). The resolved metadata appears on `agent_started.data["avp.subagents"]`.
2. Model invokes a tool whose name matches a resolved subagent. Agent emits `avp.subagent_invoked` (NOT `avp.tool_invoked`). The event's `data.span_id` is the **frame span** for this invocation. Agent calls `avp.spawn_subagent` (Resolver API) with the saved ref + input.
3. The supervisor handles the child run as its own commissioned trajectory (separate `run_id`, separate `run_requested` → `agent_stopped`). The parent records the child's `run_id` in `subagent_invoked.data["avp.subagent.run_id"]`.
4. When `avp.spawn_subagent` returns, the parent agent emits `avp.subagent_returned` carrying `data["avp.subagent.result.text"]`. The `data.span_id` MUST equal the matching `subagent_invoked.data.span_id` so consumers pair them. For **managed** subagents (separate `run_id`, separate trajectory the supervisor reads), `data["avp.subagent.usage"]` MUST be omitted; the supervisor reads the child's trajectory directly and reduces its deltas.
5. If `avp.spawn_subagent` errors, the parent agent emits `avp.subagent_failed` with `data["avp.subagent.error"]` instead of `subagent_returned`. The model receives an `Error: …` tool_result for symmetry with tool dispatch.
6. **In-process subagent fallback.** When the parent agent's SDK black-boxes a child loop and never exposes the child's per-turn events (e.g. Claude Agent SDK's Task tool, which yields only `TaskNotificationMessage` with `TaskUsage` totals), the parent MAY populate `subagent_returned.data["avp.subagent.usage"]` with a narrow `SubagentUsage` carrier (`cost_usd`, `tokens_input`, `tokens_output`, `turns`) so the supervisor at least sees the child's spend. Agents that CAN emit the child's per-turn events into the parent's trajectory (with `parent_span_id` = the invocation's `span_id`) MUST do so and MUST omit `avp.subagent.usage`; the supervisor reconstructs from raw events.

**Trajectory correlation.** Consumers join the parent and child trajectories via `subagent_invoked.data["avp.subagent.run_id"]` matching the child run's `run_id` (carried on every child event's `subject` per CloudEvents). The child trajectory is independently complete; consumers can render it standalone or nested under the parent.

**Subagent ↔ tool collision.** Resolved subagent names MUST NOT collide with agent built-in tool names or with any tool returned by a Commission-managed MCP server. A collision is a configuration conflict: the agent MUST detect this at startup, emit `error_occurred` with `data["avp.error.code"]: "commission_collision"`, and stop with `reason: "error"` before any model turn runs.

**`agent_started.data["avp.subagents"]`.** The agent MUST surface the resolved subagent declarations on `agent_started.data["avp.subagents"]` (parallel to `data["avp.tools"]` and `data["avp.skills"]`). Each entry carries `name`, `description`, and optional `inputSchema` (MCP-shaped) returned by `avp.resolve`. Consumers can read this without re-resolving.

---

## 6. Skills

`Commission.skills[]` declares [Agent Skills](https://agentskills.io/specification) the agent loads into the model's context for the run, as `{id, ref}` pairs. The agent calls `avp.resolve` at startup to obtain the SKILL.md content (or a location to fetch); agentskills.io's content model then applies. AVP itself does not specify URI schemes for skill sources.

The registration view is `agent_started.data["avp.skills"]`; the resolution view is `managed_ref_resolved` for each Commission-declared entry. No discrete per-skill load event exists on the wire: how and when a SKILL.md body enters the model's context window is an implementation detail of the agent.

### 6.1 Resolution failures

If a skill ref cannot be resolved (resolver unreachable, skill content malformed, ref not understood by the resolver), the agent MUST emit `managed_ref_resolve_failed` and `agent_stopped` with `reason: "error"` BEFORE any model turn runs.

---

## 7. Event reference

All non-RPC-request event types are past-tense facts. Event `type` values are reverse-DNS, namespaced under `avp.*`.

| Type | Source(s) | One-line semantics |
|---|---|---|
| `avp.run_requested` | `avp://agent` | First event. Anchors the run. With a Commission: carries `avp.commission` (full snapshot) + optional `avp.supervisor.*` for attribution. Without one: those fields absent. See §2.1. |
| `avp.agent_described` | `avp://agent` | Second event. The agent's self-published Descriptor (`avp.descriptor`); same payload `<agent> describe` prints. See §2.1. |
| `avp.agent_started` | `avp://agent` | Closes the prelude. Merged-state snapshot: settled `avp.prompt` / `avp.system_prompt` / `model` plus merged `avp.tools[]` (local) / `avp.mcp_servers[]` (identity) / `avp.skills[]` / `avp.subagents[]`. Per-server tool catalogs stay on the corresponding `mcp_server_connected` events. See §2.1. |
| `avp.agent_stopped` | `avp://agent` | Run has ended; last event of the trajectory. |
| `avp.managed_ref_resolved` | `avp://agent` | One per Commission-declared managed ref the agent successfully resolved at startup. Descriptor entries are agent-internal and do NOT produce this event. |
| `avp.managed_ref_resolve_failed` | `avp://agent` | Resolver returned an error or could not be reached for one of the Commission's managed refs. Agent stops fail-fast. |
| `avp.assistant_message` | `avp://agent` | Model produced output. Carries `avp.content` (the full content-block array for the turn: `text`, `thinking`, `tool_use`, `refusal`, multimodal blocks, server-tool blocks), per-inference token deltas, and cost. Refusal: refusal text appears as a `refusal` (or `text`) block in `avp.content`; the upstream finish-reason surfaces on `gen_ai.response.finish_reasons`; the provider's safety category (when given) surfaces on `avp.refusal.category`. |
| `avp.tool_invoked` | `avp://agent` | Model invoked a tool. |
| `avp.tool_returned` | `avp://agent` | Tool produced a result. `avp.tool_result.is_error` discriminates success, rejection, and execution error. |
| `avp.subagent_invoked` | `avp://agent` | Parent agent delegated to a declared subagent. Frame span opens. Carries `avp.subagent.run_id` for managed subagents. |
| `avp.subagent_returned` | `avp://agent` | Subagent returned to its parent. Frame span closes; pairs with `subagent_invoked` by `span_id`. |
| `avp.subagent_failed` | `avp://agent` | Subagent invocation errored; the model receives an `Error: …` tool_result. |
| `avp.error_occurred` | `avp://agent` | Non-tool error. |
| `avp.mcp_server_connected` | `avp://agent` | Connection established to an MCP server — either declared on the descriptor or resolved from `Commission.mcp_servers[].ref`. Carries the live tool catalog under `data["avp.mcp.tools"]`. |
| `avp.mcp_server_disconnected` | `avp://agent` | Connection to an MCP server closed. |

Field-level definitions are in [`trajectory.schema.json`](./trajectory.schema.json) (auto-generated from the Pydantic models in `python/avp/src/avp/trajectory.py`).

### 7.1 Cumulative state is the consumer's responsibility

The agent does NOT publish cumulative totals on the wire. Per-turn deltas live on each `assistant_message` (`avp.cost_usd`, `gen_ai.usage.*_tokens`); tool invocation counts come from `tool_invoked` events; run duration is `agent_stopped.time` minus `agent_started.time`. Consumers (supervisors, audit pipelines, dashboards) reduce the event stream to compute totals. The reasons for this split are (1) one source of truth on the wire, (2) no agent-side accumulator to drift, and (3) translator-pattern agents already derive per-turn deltas from cumulative-usage SDKs; making them then re-accumulate to broadcast cumulative state is busywork without value.

The wire invariant is "run total = sum of per-turn `assistant_message.avp.cost_usd`." Per-turn `avp.cost_usd` is the translator's best observation at turn end; reconciliation against external billing systems is a consumer concern.

---

## 8. Conformance

An agent is conforming to the Trajectory Spec if and only if all of the following hold:

1. Every event it emits MUST conform to the CloudEvents 1.0 envelope shape (`specversion`, `id`, `source`, `type`, `time`, `data`) and MUST set `source: "avp://agent"`. The agent is the sole producer on the wire; supervisor attribution lives in `run_requested.data["avp.commission"]` and `data["avp.supervisor.*"]` when a Commission is in use, per [Commission](./commission.md).
2. The trajectory MUST open with the prelude defined in §2.1, in this order: `avp.run_requested`, `avp.agent_described`, then any `avp.managed_ref_resolved` (one per Commission-declared ref), any `avp.mcp_server_connected` (one per dialed server, descriptor's + Commission's), and finally `avp.agent_started`. When relaying a Commission, `avp.run_requested.data["avp.commission"]` MUST carry a faithful snapshot of it (managed refs verbatim); otherwise `data["avp.commission"]` and `data["avp.supervisor.*"]` MUST be absent. `avp.agent_described.data["avp.descriptor"]` MUST equal the [Agent Descriptor](./agent-descriptor.md) payload the agent publishes via its pre-flight `describe` surface for the same agent build. `avp.agent_started` is the merged-state snapshot: `data["avp.tools"]` MUST list the agent's local tool catalog (`descriptor.tools` filtered by `Commission.enabled_builtin_tools`); `data["avp.mcp_servers"]` MUST list the merged MCP server identities (descriptor's filtered ∪ Commission's resolved); `data["avp.skills"]` and `data["avp.subagents"]` MUST list the merged skill / subagent decls. MCP-surfaced tool catalogs MUST NOT be duplicated on `data["avp.tools"]`; they live on each `mcp_server_connected.data["avp.mcp.tools"]`. `avp.prompt` MUST be included on `agent_started` when available.
3. For every model inference, it MUST emit `avp.assistant_message` after the model returns output. `data["avp.content"]` MUST carry a faithful `list[AVPContentBlock]` of the blocks the model produced this turn (text, thinking, tool_use, refusal, multimodal, server-tool); reconstructing a provider message array from the trajectory MUST be a direct read of this field per turn, paired with the `avp.tool_result` blocks on intervening `tool_returned` events.
4. For every tool call, it MUST emit `avp.tool_invoked` before invocation and then `avp.tool_returned` (with `avp.tool_result.is_error` set appropriately for success, rejection, or execution error) afterward.
5. Each `avp.assistant_message` MUST carry the per-turn billable cost (`avp.cost_usd`) and per-turn token deltas (`gen_ai.usage.*_tokens`). The agent MUST NOT publish cumulative totals on the wire.
6. The last event it emits MUST be `avp.agent_stopped` (source=`avp://agent`). After emitting `agent_stopped`, the agent MUST NOT emit additional events.
7. All emitted events MUST validate against `trajectory.schema.json`.

If `Commission.mcp_servers` is non-empty (cross-spec composition with [Commission](./commission.md)), the agent additionally MUST:

M1. Emit `avp.mcp_server_connected` for each Commission-declared MCP server after resolving its ref and dialing the resolved endpoint, before the first turn. The connected event SHOULD carry the live tool catalog (`data["avp.mcp.tools"]`) returned by MCP's `tools/list`.
M2. Emit `avp.mcp_server_disconnected` for each connected MCP server before `avp.agent_stopped`.
M3. Dispatch `tools/call` for any model-invoked tool whose name is hosted by an MCP server through that server, tagging `tool_invoked.data["avp.tool.dispatch_target"] = "mcp_server"` and `avp.mcp_server_id` matching the Commission entry's `id`.
