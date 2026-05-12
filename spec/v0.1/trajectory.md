# AVP Trajectory Spec, v0.1

**Status:** Draft
**Stability:** beta. Wire shape, event catalog, and conformance criteria are stable; minor additive changes possible.
**Umbrella version:** v0.1 (see [`README.md`](./README.md))
**Schema:** [`trajectory.schema.json`](./trajectory.schema.json)
**$id base:** `https://avp.dev/schema/v0.1/`

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

---

## 1. Scope

The Trajectory Spec defines the **stream of events** an agent emits as it runs. It is independently implementable: an existing agent loop with its own run-config object can emit conforming AVP events without adopting [Commission](./commission.md), [Agent Descriptor](./agent-descriptor.md), or the [Resolver API](./resolver.md). When the other sub-specs ARE adopted, this document describes how they compose into the event stream (the run prelude carries a Commission snapshot and an Agent Descriptor payload; managed-asset events record Resolver round-trips).

The trajectory holds two semantically distinct kinds of facts:

| Class | Event types | Semantics |
|---|---|---|
| **What the agent did** | `model_turn_*`, `tool_invoked`, `tool_returned`, `tool_failed`, `text_emitted`, `reasoning_emitted`, `subagent_*`, `managed_ref_resolved`, `managed_ref_resolve_failed`, `mcp_server_connected`, `mcp_server_disconnected`, `skill_loaded`, `refusal_recorded`, `error_occurred` | Mechanical actions the agent took |
| **What the run cost** | `cost_recorded`, `model_turn_ended.usage` | Resource accounting |

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

The agent's stdout is the **canonical trajectory**. Every event is a CloudEvents 1.0 envelope. The `source` attribute is a URI that identifies the producer:

- **`source: "avp://agent"`** is the overwhelming majority of events: the agent emitting facts about what it did.
- **`source: "avp://supervisor"`** appears only on the trajectory's opening `avp.run_requested` event (agent-relayed from `Commission.supervisor`; see §2.1). v0.1 has no supervisor → agent push channel; supervisors do not directly emit events.

Every event's `data` payload carries an OpenTelemetry **span triple**: `trace_id` (16 random bytes, 32 lowercase hex chars), `span_id` (8 random bytes, 16 hex chars), and `parent_span_id` (or 16 zeros for the root). The agent span is the run; turn / tool / managed-ref-resolution spans nest inside it. Consumers reconstruct the trajectory as a span tree.

### 2.1 Run prelude

Every conforming trajectory opens with three events, in this exact order:

```
1. avp.run_requested      source=avp://supervisor   (agent-relayed)
2. avp.agent_described    source=avp://agent
3. avp.agent_started      source=avp://agent
```

These are distinct facts the wire records before the agent runs:

- **`avp.run_requested`** anchors the run. The agent emits it from `Commission.supervisor` with `source: avp://supervisor` (agent-relayed; the agent stamps the source URI to attribute the run to the originating supervisor build). `data["avp.commission"]` carries the full Commission snapshot the supervisor handed in (refs included verbatim, since they are opaque to the agent), so an auditor reading the trajectory can re-derive the run's input surface without an external Commission registry. `data["avp.supervisor.name"]` and the optional `data["avp.supervisor.version"]` complete the attribution. See [`commission.md`](./commission.md) for the snapshot's shape.

- **`avp.agent_described`** is the agent's self-published [Agent Descriptor](./agent-descriptor.md) of everything triggerable without supervisor configuration: SDK preset tools, runtime-bundled subagents, runtime-bundled skills, plus the agent's name, version, and supported AVP spec version. The payload (`data["avp.descriptor"]`) MUST equal what `<agent> describe` prints to stdout for the same agent build. This makes the audit trail and pre-flight introspection two views of the same fact. v0.1-conforming agents implicitly speak the Resolver API; capability is implied by `avp_spec_version: "0.1"` rather than carried as a separate flag.

- **`avp.agent_started`** is the merged-view event, listing what the model will actually see for this specific run: the agent's internal contribution combined with the supervisor's managed assets after they have been resolved (per [`resolver.md`](./resolver.md)).

`run_requested` and `agent_described` are root-level in the span tree (`parent_span_id = ZERO`). They do NOT pair (each owns its own span); `agent_started` owns the agent span that all subsequent run events nest under.

An agent that cannot identify itself (no Descriptor available) MUST NOT skip the prelude. Instead, emit `agent_described` with the smallest valid Descriptor it can publish (its own package name, version, and `avp_spec_version`). A supervisor that omits `Commission.supervisor` MUST still see `run_requested` emitted, with `avp.supervisor.name="unknown"`.

### 2.2 Managed-ref resolution events

Between `agent_started` and the first `model_turn_started`, the agent MUST resolve every managed asset declared in the Commission (per [`resolver.md`](./resolver.md)). Each successful resolution emits one `avp.managed_ref_resolved` event; any failure emits one `avp.managed_ref_resolve_failed` event followed by `agent_stopped(reason: "error")`. These events do not re-record the opaque ref material; `run_requested.data["avp.commission"]` already carries it. The resolution events record only that the round-trip happened.

---

## 3. The agent loop (normative)

A conforming agent MUST behave as if executing the following algorithm. (The agent MAY reorder operations that are not externally observable, provided the emitted event sequence is indistinguishable.)

### 3.1 Run state and the definition of a turn

A **turn** in AVP is exactly one `model_turn_started` / `model_turn_ended` pair where the model produced new output (either text or tool calls or both). Continuations and SDK-internal restatements that do not represent a fresh model call MUST NOT be counted as turns.

This matters most for translator-pattern agents wrapping SDKs that emit "assistant message" objects for things that aren't fresh model calls (e.g., follow-up wrappers around tool results). Translator agents MUST count an event as a turn only when the SDK-reported usage carries non-zero new output tokens (delta-output > 0), or (if the SDK doesn't report per-call usage) when the message includes content the model itself produced.

The agent maintains a `RunStateSnapshot` (see [`trajectory.schema.json`](./trajectory.schema.json) `#/$defs/RunStateSnapshot`) tracking `total_turns`, `total_cost_usd`, `total_tokens`, etc. The snapshot is observability: it travels on `cost_recorded` and `agent_stopped` so consumers can trace cumulative spend, but v0.1 does not specify caps that the agent must enforce against it.

### 3.2 The loop

```
read commission from stdin
emit run_requested  (source=avp://supervisor, agent-relayed)
emit agent_described
emit agent_started

# Startup resolve (Resolver API)
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

### 3.3 Cost / token accounting rules (normative)

- `cost_usd` on `model_turn_ended` is the BILLABLE cost (post-cache-discount).
- `tokens_input` on `model_turn_ended` is the total input tokens INCLUDING cache-read tokens.
- `tokens_cache_read` and `tokens_cache_write` are informational; they MUST NOT alter `state.total_tokens` independently.
- `state.total_cost_usd` and `state.total_tokens` are monotonically non-decreasing.
- **Translator agents over cumulative-usage SDKs.** Some SDKs (notably the Claude Agent SDK) report usage as a running session total per message rather than as a per-call delta. Translators MUST derive deltas (subtract previous cumulative) to populate per-turn `tokens_*` and `cost_usd` correctly. When the SDK's cumulative drops without warning (`cum < prev`), the translator MUST emit `error_occurred` with `code: "accounting_reset"` rather than silently clamping; consumers cannot distinguish a swallowed delta from a legitimate quiet turn otherwise. SDKs that signal context compaction or sub-agent dispatch via lifecycle events SHOULD be hooked so the translator resets its baselines deliberately, not via the error path.

---

## 4. Tool dispatch

v0.1 has two paths for any tool the model can call:

1. **Agent built-in.** Compiled into the agent package; declared on the agent's [Agent Descriptor](./agent-descriptor.md) under `built_in_tools`. Surfaced on `agent_started.data.tools[]` with `avp.tool.dispatch_target = "local"`. The agent runs them directly.
2. **MCP server.** Declared by the supervisor in `Commission.mcp_servers[]` as `{id, ref}`. The agent resolves the ref (Resolver API), dials the resolved endpoint, runs MCP's `tools/list`, and dispatches calls via MCP's `tools/call`. Surfaced on `mcp_server_connected.data["avp.mcp.tools"]` (live tool catalog) and on `agent_started.data.tools[]` with `avp.tool.dispatch_target = "mcp_server"` and `avp.mcp_server_id` matching the Commission entry's `id`.

Wire flow:

1. Model calls a tool. Agent emits `avp.tool_invoked`.
2. Agent dispatches: locally for built-ins, via MCP for MCP-server tools.
3. Agent emits `avp.tool_returned` (or `avp.tool_failed`).

There is no AVP-flavored RPC channel for tool dispatch. Supervisors that want to expose Python (or shell, or HTTP-backed) tools wrap them in an MCP server, declare the server's ref in `Commission.mcp_servers[]`, and have their resolver return the connection material when asked.

**`avp.tool.dispatch_target`.** Every `tool_invoked` event MAY carry `avp.tool.dispatch_target` discriminating the implementation that handled the call:

| Value | Meaning |
|---|---|
| `local` | Tool ran in the agent's own process: code compiled into the agent package. |
| `mcp_server` | Tool was dispatched by an MCP server. The event also carries `avp.mcp_server_id` matching a `Commission.mcp_servers[].id`. |

### 4.1 Merge semantics: agent-internal ∪ Commission-managed

The agent's loop dispatches against a single bag of tools, regardless of whether each entry was baked into the agent or resolved from a Commission ref. The agent's runtime layer constructs the bag at startup:

1. Start with the agent's internal tools (the Descriptor's `built_in_tools`).
2. For each `Commission.mcp_servers[]` ref, resolve, connect, and add the server's `tools/list` output.
3. If any `id` collision exists between an agent-internal MCP server and a Commission-declared one, emit `error_occurred` with `data["avp.error.code"]: "commission_collision"` and stop. Configuration errors fail-fast.

Tool-name collisions across distinct MCP servers (e.g. agent-internal `github_v1` and Commission-managed `github_v2` both exposing `list_prs`) are an agent-runtime concern outside AVP's wire. The agent's MCP client surfaces names to the model however it normally does (most clients namespace by server id, e.g. `github_v1__list_prs`); AVP records the name the agent dispatched on in `tool_invoked.data["gen_ai.tool.name"]`.

---

## 5. Subagents

`Commission.subagents[]` declares **delegate agents** the parent agent may invoke by name, as `{id, ref}` pairs. The supervisor stands up the subagent as a managed asset; the parent agent only sees an opaque ref.

**Wire flow.**

1. At startup, the parent agent calls `avp.resolve` (Resolver API) for each `subagents[]` entry to obtain model-facing metadata (`name`, `description`, `inputSchema`). The resolved metadata appears on `agent_started.data.subagents[]`.
2. Model invokes a tool whose name matches a resolved subagent. Agent emits `avp.subagent_invoked` (NOT `avp.tool_invoked`). The event's `data.span_id` is the **frame span** for this invocation. Agent calls `avp.spawn_subagent` (Resolver API) with the saved ref + input.
3. The supervisor handles the child run as its own commissioned trajectory (separate `run_id`, separate `run_requested` → `agent_stopped`). The parent records the child's `run_id` in `subagent_invoked.data["avp.subagent.run_id"]`.
4. When `avp.spawn_subagent` returns, the parent agent emits `avp.subagent_returned` carrying `data["avp.subagent.result.text"]` plus a `RunStateSnapshot` rollup at `data["avp.subagent.usage"]` from the resolver's response. The `data.span_id` MUST equal the matching `subagent_invoked.data.span_id` so consumers pair them.
5. If `avp.spawn_subagent` errors, the parent agent emits `avp.subagent_failed` with `data["avp.subagent.error"]` instead of `subagent_returned`. The model receives an `Error: …` tool_result for symmetry with tool dispatch.
6. The subagent's spend (cost, tokens) MUST be rolled into the parent run's cumulative `RunStateSnapshot`. Per-subagent attribution is preserved on `subagent_returned.data["avp.subagent.usage"]` and the full child trajectory.

**Trajectory correlation.** Consumers join the parent and child trajectories via `subagent_invoked.data["avp.subagent.run_id"]` matching the child run's `run_id` (carried on every child event's `subject` per CloudEvents). The child trajectory is independently complete; consumers can render it standalone or nested under the parent.

**Subagent ↔ tool collision.** Resolved subagent names MUST NOT collide with agent built-in tool names or with any tool returned by a Commission-managed MCP server. A collision is a configuration conflict: the agent MUST detect this at startup, emit `error_occurred` with `data["avp.error.code"]: "commission_collision"`, and stop with `reason: "error"` before any model turn runs.

**`agent_started.data.subagents`.** The agent MUST surface the resolved subagent declarations on `agent_started.data.subagents[]` (parallel to `data.tools[]` and `data.skills[]`). Each entry carries `name`, `description`, and optional `inputSchema` (MCP-shaped) returned by `avp.resolve`. Consumers can read this without re-resolving.

---

## 6. Skills

`Commission.skills[]` declares [Agent Skills](https://agentskills.io/specification) the agent loads into the model's context for the run, as `{id, ref}` pairs. The agent calls `avp.resolve` at startup to obtain the SKILL.md content (or a location to fetch); agentskills.io's content model then applies. AVP itself does not specify URI schemes for skill sources.

### 6.1 Loading semantics

The `avp.skill_loaded` event means **the SKILL.md body content has been added to the model's active context window**, NOT a registration acknowledgment. (The registration view is `agent_started.data.skills[]`; the resolution view is `managed_ref_resolved` for each entry.)

Two emission patterns differentiated by an agent's `descriptor.capabilities`:

- **`skills:eager`**: agent injects all resolved SKILL.md bodies at startup (typically as a system_prompt suffix). Emit `skill_loaded` once per skill, `step=0`, after `agent_started` and before turn 1.

- **`skills:progressive`**: model decides per-turn which skill bodies to pull into context. Emit `skill_loaded` when the body actually enters context, with `step=N` matching the turn it loaded in. MAY fire multiple times for the same skill (e.g., re-load after compaction).

Agents whose SDK does NOT expose progressive-disclosure load events SHOULD NOT emit `skill_loaded` at all; `agent_started.data.skills[]` still records the registration. Honest-silent beats fabricated events.

### 6.2 Resolution failures

If a skill ref cannot be resolved (resolver unreachable, skill content malformed, ref not understood by the resolver), the agent MUST emit `managed_ref_resolve_failed` and `agent_stopped` with `reason: "error"` BEFORE any model turn runs.

---

## 7. Event reference

All non-RPC-request event types are past-tense facts. Event `type` values are reverse-DNS, namespaced under `avp.*`.

| Type | Source(s) | One-line semantics |
|---|---|---|
| `avp.run_requested` | `avp://supervisor` | First event. Agent-relayed; supervisor-attributed. Anchors the run with `avp.commission` (full Commission snapshot) + `avp.supervisor.name`. See §2.1. |
| `avp.agent_described` | `avp://agent` | Second event. The agent's self-published Descriptor (`avp.descriptor`); same payload `<agent> describe` prints. See §2.1. |
| `avp.agent_started` | `avp://agent` | Third event. Merged view: what the model will actually see, after Commission × resolution × SDK enrichment. |
| `avp.agent_stopped` | `avp://agent` | Run has ended; last event of the trajectory. |
| `avp.managed_ref_resolved` | `avp://agent` | One per Commission-declared managed ref the agent successfully resolved at startup. |
| `avp.managed_ref_resolve_failed` | `avp://agent` | Resolver returned an error or could not be reached for one of the Commission's managed refs. Agent stops fail-fast. |
| `avp.model_turn_started` | `avp://agent` | About to call the model. |
| `avp.model_turn_ended` | `avp://agent` | Model response received. Carries OTel `gen_ai.usage.*`. |
| `avp.tool_invoked` | `avp://agent` | Model invoked a tool. |
| `avp.tool_returned` | `avp://agent` | Tool produced a result (or was rejected). |
| `avp.tool_failed` | `avp://agent` | Tool raised an execution error. |
| `avp.subagent_invoked` | `avp://agent` | Parent agent delegated to a declared subagent. Frame span opens. Carries `avp.subagent.run_id` for managed subagents. |
| `avp.subagent_returned` | `avp://agent` | Subagent returned to its parent. Frame span closes; pairs with `subagent_invoked` by `span_id`. |
| `avp.subagent_failed` | `avp://agent` | Subagent invocation errored; the model receives an `Error: …` tool_result. |
| `avp.text_emitted` | `avp://agent` | Assistant text content. |
| `avp.reasoning_emitted` | `avp://agent` | Reasoning / thinking block (extended thinking, o-series reasoning). Distinct from text so consumers can filter chain-of-thought. |
| `avp.refusal_recorded` | `avp://agent` | Model declined the turn. Run terminates with `avp.agent_stopped.avp.reason="refused"`. |
| `avp.cost_recorded` | `avp://agent` | Cumulative `RunStateSnapshot` snapshot. May carry `avp.cost.source="reported"` on the reconciliation event when the API/SDK hands back an authoritative cost total. |
| `avp.skill_loaded` | `avp://agent` | SKILL.md loaded into context. |
| `avp.error_occurred` | `avp://agent` | Non-tool error. Documented `data["avp.error.code"]` values include `commission_collision` (configuration), and `execution_backend_failure` (the runner determined its host execution environment can no longer continue; signals the supervisor that the run is a rescue candidate — see §7.3). |
| `avp.mcp_server_connected` | `avp://agent` | Connection established to an MCP server (resolved from a `Commission.mcp_servers[].ref`). |
| `avp.mcp_server_disconnected` | `avp://agent` | Connection to an MCP server closed. |
| `avp.run_rescued` | `avp://supervisor` | Supervisor-sourced peer event (additive to §2.1; not part of the prelude). Inserted between a failed runner's last event and the new runner's first event when the supervisor swaps execution backends mid-run. Same `run_id`; the trajectory continues. See §7.3. |

Field-level definitions are in [`trajectory.schema.json`](./trajectory.schema.json) (auto-generated from the Pydantic models in `python/avp/src/avp/types.py`).

### 7.1 `agent_stopped` convenience aliases

`agent_stopped.data` carries `avp.total_tokens`, `avp.total_cost_usd`, `avp.total_turns`, and `avp.duration_ms` at the top level **as convenience aliases**. When non-null they MUST equal the matching field inside `avp.state` (a `RunStateSnapshot`). New consumers SHOULD read `avp.state.*`: the same shape ships on every `cost_recorded` event, so analytics code that targets `avp.state` works uniformly across the run timeline rather than special-casing the terminator. The top-level fields are scheduled for removal in v0.2.

### 7.2 Per-event runner attribution (optional)

A trajectory MAY span multiple execution backends (see §7.3, agent rescue). To let consumers attribute any single event to the runner that produced it without scanning for the nearest bracket, every agent-sourced event MAY carry `data["avp.runner"]`:

```json
"data": {
  "avp.runner": {
    "backend": "local-ollama",
    "model":   "llama3.2:3b"
  }
}
```

Field semantics:

- `backend` — stable identifier of the execution backend (matches the supervisor's `ExecutionBackend::identity`, e.g. `"modal-sandbox"`, `"local-ollama"`).
- `model` — the underlying model id used for inference on this turn (the literal string passed to the model provider). MAY differ between events in the same trajectory if a rescue swapped to a backend that uses a different model.

The field is **optional** for backward compatibility. Runners SHOULD populate it when they know they may participate in a rescued trajectory. Consumers MUST tolerate its absence and MUST NOT rely on a single trajectory-wide value.

A run that traverses multiple backends will produce a trajectory whose `avp.runner` value changes across the boundary. The change MUST be flanked by an `avp.run_rescued` bracket (§7.3); the bracket is the authoritative boundary marker, `avp.runner` is the per-event tag.

### 7.3 Agent rescue (supervisor-orchestrated)

A supervisor MAY swap a run's execution backend mid-trajectory ("agent rescue") — for example, when a local-LLM runner crashes and the supervisor continues the same `run_id` on a CASDK runner. v0.1 specifies two surfaces for this:

**Runner-side signal.** A runner that determines its host execution environment can no longer continue (and therefore cannot legitimately emit `agent_stopped`) SHOULD emit:

```
avp.error_occurred
  data["avp.error.code"]    = "execution_backend_failure"
  data["avp.error.message"] = <free-form runner-supplied description>
```

immediately before terminating. This is a signal to the supervisor that the run is a candidate for rescue, distinct from agent-side errors that warrant a normal `agent_stopped(reason: "error")`. A runner MAY choose to emit `agent_stopped` instead; the rescue signal is best-effort.

**Supervisor-side bracket.** When the supervisor decides to swap backends, it appends a single `avp.run_rescued` event to the trajectory before re-dispatching:

```json
{
  "specversion": "1.0",
  "type":   "avp.run_rescued",
  "source": "avp://supervisor",
  "data": {
    "from":   {"backend": "local-ollama",  "attempt": 1, "model": "llama3.2:3b"},
    "to":     {"backend": "modal-sandbox", "attempt": 2, "model": "claude-sonnet-4-5"},
    "reason": "execution_backend_failure: ollama: connection refused",
    "last_completed_seq": 17
  }
}
```

- `source: "avp://supervisor"` (the second supervisor-sourced event type alongside `run_requested`).
- The bracket does **not** restart the span tree. The new runner inherits the agent span opened by the original `agent_started`.
- The new runner SHOULD read the prior events as read-only context (deterministic replay of completed turns is the v0.1 contract; see §1.1 for the deferred warm-rescue / `Commission.resume` extensions).
- Cost / token totals accumulate across the swap — one `run_id`, one `RunStateSnapshot` lineage.

The final terminator (`agent_stopped`) MUST come from whichever runner finishes the run, with `source: "avp://agent"`. v0.1 has no separate `agent_stopped(reason: "rescued")` — rescue is a mid-run event, not a termination.

A rescued trajectory therefore looks like:

```
avp.run_requested      (avp://supervisor)
avp.agent_described    (avp://agent, runner A)
avp.agent_started      (avp://agent, runner A)
…                      (runner A events, data.avp.runner = {backend: A, model: ...})
avp.error_occurred     (avp://agent, runner A, avp.error.code = "execution_backend_failure")
avp.run_rescued        (avp://supervisor)
…                      (runner B events, data.avp.runner = {backend: B, model: ...})
avp.agent_stopped      (avp://agent, runner B)
```

---

## 8. Conformance

An agent is conforming to the Trajectory Spec if and only if all of the following hold:

1. Every event it emits MUST conform to the CloudEvents 1.0 envelope shape (`specversion`, `id`, `source`, `type`, `time`, `data`). All v0.1 events EXCEPT `avp.run_requested` MUST set `source: "avp://agent"`. `avp.run_requested` is the only event with `source: "avp://supervisor"` (agent-relayed; the agent stamps the source URI from `Commission.supervisor` when [Commission](./commission.md) is in use).
2. The trajectory MUST open with the prelude defined in §2.1: `avp.run_requested`, then `avp.agent_described`, then `avp.agent_started`, in that exact order. `avp.run_requested.data["avp.commission"]` MUST carry a faithful snapshot of the Commission the supervisor handed in (including managed refs verbatim). `avp.agent_described.data["avp.descriptor"]` MUST equal the [Agent Descriptor](./agent-descriptor.md) payload the agent publishes via its pre-flight `describe` surface for the same agent build. `avp.agent_started` MUST include `prompt` when available. The `data.tools` field MUST list the EFFECTIVE tool surface: agent built-in tools plus any MCP-server tools surfaced after `mcp_server_connected`.
3. For every model inference, it MUST emit `avp.model_turn_started` immediately before the request and `avp.model_turn_ended` immediately after the response.
4. For every tool call, it MUST emit `avp.tool_invoked` before invocation and either `avp.tool_returned` (success or rejection) or `avp.tool_failed` (execution error) afterward.
5. It MUST emit `avp.cost_recorded` at least once per turn. The `data["avp.state"]` field MUST validate against `RunStateSnapshot`.
6. The last event it emits MUST be `avp.agent_stopped` (source=`avp://agent`). After emitting `agent_stopped`, the agent MUST NOT emit additional events.
7. All emitted events MUST validate against `trajectory.schema.json`.

If `Commission.mcp_servers` is non-empty (cross-spec composition with [Commission](./commission.md)), the agent additionally MUST:

M1. Emit `avp.mcp_server_connected` for each Commission-declared MCP server after resolving its ref and dialing the resolved endpoint, before the first turn. The connected event SHOULD carry the live tool catalog (`data["avp.mcp.tools"]`) returned by MCP's `tools/list`.
M2. Emit `avp.mcp_server_disconnected` for each connected MCP server before `avp.agent_stopped`.
M3. Dispatch `tools/call` for any model-invoked tool whose name is hosted by an MCP server through that server, tagging `tool_invoked.data["avp.tool.dispatch_target"] = "mcp_server"` and `avp.mcp_server_id` matching the Commission entry's `id`.
