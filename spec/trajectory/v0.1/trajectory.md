# AVP Trajectory Spec, v0.1

**Status:** Stable
**Stability:** Wire shape, event catalog, and conformance criteria are committed; additive changes may ship as v0.y, but breaking changes require a new minor or major version.
**Schema:** [`trajectory.schema.json`](./trajectory.schema.json)
**$id:** `https://raw.githubusercontent.com/portofcontext/agent-voyager-project/main/spec/trajectory/v0.1/trajectory.schema.json`

## 1. Scope

The Trajectory Spec defines the **stream of events** an agent emits as it runs. It is independently implementable: an existing agent loop with its own run-config object can emit conforming events without adopting [Commission](../../commission/v0.1-beta/commission.md), [Agent Descriptor](../../agent-descriptor/v0.1/agent-descriptor.md), or the [Resolver API](../../resolver/v0.1-beta/resolver.md). When those specs ARE adopted, the prelude carries a Commission snapshot and an Agent Descriptor payload, and managed-asset events record Resolver round-trips.

The trajectory records **what the agent did** (mechanical actions: model turns, tool calls, subagent dispatch, ref resolution, skill loads, refusals, errors) and **what the run cost** (`cost_recorded`, `model_turn_ended.usage`). Interpretive narrative ("SuspiciousWriteDetected") is post-hoc annotation, not a runtime event class, and is out of scope.

## 2. The trajectory

The agent's stdout is the **canonical trajectory**. Every event is a CloudEvents 1.0 envelope. The `source` attribute identifies the producer:

- **`source: "avp://agent"`** for the overwhelming majority of events: the agent emitting facts about what it did.
- **`source: "avp://supervisor"`** appears only on the trajectory's opening `avp.run_requested` event (agent-relayed from `Commission.supervisor`; see §2.1). Supervisors do not directly emit events; there is no supervisor → agent push channel.

Every event's `data` payload carries an OpenTelemetry **span triple**: `trace_id` (16 random bytes, 32 lowercase hex chars), `span_id` (8 random bytes, 16 hex chars), and `parent_span_id` (or 16 zeros for the root). The agent span is the run; turn / tool / managed-ref-resolution spans nest inside it. Consumers reconstruct the trajectory as a span tree.

### 2.1 Run prelude

Every conforming trajectory opens with three events, in this exact order:

```
1. avp.run_requested      source=avp://supervisor   (agent-relayed)
2. avp.agent_described    source=avp://agent
3. avp.agent_started      source=avp://agent
```

- **`avp.run_requested`** anchors the run. The agent emits it from `Commission.supervisor` with `source: avp://supervisor` (agent-relayed; the agent stamps the source URI). `data["avp.commission"]` carries the full Commission snapshot the supervisor handed in (refs included verbatim), so an auditor reading the trajectory can re-derive the run's input surface without an external registry. `data["avp.supervisor.name"]` and optional `data["avp.supervisor.version"]` complete the attribution.
- **`avp.agent_described`** carries the agent's self-published Descriptor at `data["avp.descriptor"]`. The payload MUST equal what `<agent> describe` prints to stdout for the same agent build, making the audit trail and pre-flight introspection two views of the same fact.
- **`avp.agent_started`** is the merged view, listing what the model will actually see for this run: the agent's internal contribution combined with the supervisor's managed assets after resolution.

`run_requested` and `agent_described` are root-level in the span tree (`parent_span_id = ZERO`). They do NOT pair; `agent_started` owns the agent span that all subsequent run events nest under.

An agent that cannot identify itself MUST NOT skip the prelude. It emits `agent_described` with the smallest valid Descriptor it can publish. A supervisor that omits `Commission.supervisor` MUST still see `run_requested` emitted, with `avp.supervisor.name="unknown"`.

### 2.2 Managed-ref resolution events

Between `agent_started` and the first `model_turn_started`, the agent MUST resolve every managed asset declared in the Commission. Each successful resolution emits one `avp.managed_ref_resolved` event; any failure emits one `avp.managed_ref_resolve_failed` event followed by `agent_stopped(reason: "error")`. These events do not re-record the opaque ref material; `run_requested.data["avp.commission"]` already carries it.

## 3. The agent loop (normative)

A conforming agent MUST behave as if executing the following algorithm. The agent MAY reorder operations that are not externally observable, provided the emitted event sequence is indistinguishable.

### 3.1 What counts as a turn

A **turn** is exactly one `model_turn_started` / `model_turn_ended` pair where the model produced new output (text, tool calls, or both). Continuations and SDK-internal restatements that do not represent a fresh model call MUST NOT be counted as turns. Translator-pattern agents wrapping SDKs that emit "assistant message" objects for non-model-call events MUST count an event as a turn only when the SDK-reported usage carries non-zero new output tokens, or (if the SDK doesn't report per-call usage) when the message includes content the model itself produced.

The agent maintains a `RunStateSnapshot` (see schema `#/$defs/RunStateSnapshot`) tracking `total_turns`, `total_cost_usd`, `total_tokens`, etc. The snapshot travels on `cost_recorded` and `agent_stopped`; v0.1 does not specify caps the agent must enforce.

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

### 3.3 Cost / token accounting rules

- `cost_usd` on `model_turn_ended` is the BILLABLE cost (post-cache-discount).
- `tokens_input` on `model_turn_ended` is the total input tokens INCLUDING cache-read tokens.
- `tokens_cache_read` and `tokens_cache_write` are informational; they MUST NOT alter `state.total_tokens` independently.
- `state.total_cost_usd` and `state.total_tokens` are monotonically non-decreasing.
- **Cumulative-usage SDKs.** Some SDKs (notably the Claude Agent SDK) report usage as a running session total per message rather than as a per-call delta. Translators MUST derive deltas (subtract previous cumulative) to populate per-turn `tokens_*` and `cost_usd`. When cumulative drops without warning (`cum < prev`), the translator MUST emit `error_occurred` with `code: "accounting_reset"` rather than silently clamping. SDKs that signal context compaction or sub-agent dispatch via lifecycle events SHOULD be hooked so the translator resets baselines deliberately.

## 4. Tool dispatch

Two dispatch paths for any tool the model can call:

1. **Agent built-in.** Compiled into the agent package; declared on the Descriptor under `built_in_tools`. Surfaced on `agent_started.data.tools[]` with `avp.tool.dispatch_target = "local"`. Run directly.
2. **MCP server.** Declared by the supervisor in `Commission.mcp_servers[]` as `{id, ref}`. The agent resolves the ref, dials the endpoint, runs MCP's `tools/list`, and dispatches via MCP's `tools/call`. Surfaced on `mcp_server_connected.data["avp.mcp.tools"]` and on `agent_started.data.tools[]` with `avp.tool.dispatch_target = "mcp_server"` and `avp.mcp_server_id` matching the Commission entry's `id`.

Wire flow per call: `tool_invoked` → dispatch → `tool_returned` (or `tool_failed`). There is no AVP-flavored RPC for tool dispatch; supervisors expose Python/shell/HTTP tools by wrapping them in an MCP server.

### 4.1 Merge semantics: agent-internal ∪ Commission-managed

The agent's loop dispatches against a single bag of tools at startup:

1. Start with the agent's internal tools (Descriptor's `built_in_tools`).
2. For each `Commission.mcp_servers[]` ref, resolve, connect, and add the server's `tools/list` output.
3. If any `id` collision exists between an agent-internal MCP server and a Commission-declared one, emit `error_occurred` with `data["avp.error.code"]: "commission_collision"` and stop.

Tool-name collisions across distinct MCP servers are an agent-runtime concern outside AVP's wire. The agent's MCP client surfaces names to the model however it normally does (most clients namespace by server id); AVP records the name the agent dispatched on in `tool_invoked.data["gen_ai.tool.name"]`.

## 5. Subagents

`Commission.subagents[]` declares delegate agents the parent may invoke by name, as `{id, ref}` pairs. The supervisor stands up the subagent as a managed asset; the parent only sees an opaque ref.

1. At startup, the parent calls `avp.resolve` for each `subagents[]` entry to obtain model-facing metadata (`name`, `description`, `inputSchema`). The resolved metadata appears on `agent_started.data.subagents[]`.
2. Model invokes a tool whose name matches a resolved subagent. Agent emits `avp.subagent_invoked` (NOT `avp.tool_invoked`). The event's `data.span_id` is the **frame span**. Agent calls `avp.spawn_subagent` with the saved ref + input.
3. The supervisor handles the child run as its own commissioned trajectory (separate `run_id`, separate `run_requested` → `agent_stopped`). The parent records the child's `run_id` in `subagent_invoked.data["avp.subagent.run_id"]`.
4. When `avp.spawn_subagent` returns, the parent emits `avp.subagent_returned` carrying `data["avp.subagent.result.text"]` and a `RunStateSnapshot` rollup at `data["avp.subagent.usage"]`. The `data.span_id` MUST equal the matching `subagent_invoked.data.span_id`.
5. On error, the parent emits `avp.subagent_failed` with `data["avp.subagent.error"]` instead of `subagent_returned`. The model receives an `Error: …` tool_result for symmetry with tool dispatch.
6. The subagent's spend MUST be rolled into the parent run's cumulative `RunStateSnapshot`. Per-subagent attribution is preserved on `subagent_returned.data["avp.subagent.usage"]` and the full child trajectory.

Consumers join parent and child trajectories via `subagent_invoked.data["avp.subagent.run_id"]` matching the child run's `run_id` (carried on every child event's `subject`).

Resolved subagent names MUST NOT collide with agent built-in tool names or with tools returned by a Commission-managed MCP server. The agent MUST detect this at startup, emit `error_occurred` with `data["avp.error.code"]: "commission_collision"`, and stop with `reason: "error"`.

## 6. Skills

`Commission.skills[]` declares [Agent Skills](https://agentskills.io/specification) the agent loads into the model's context for the run. The agent calls `avp.resolve` at startup to obtain the SKILL.md content; agentskills.io's content model then applies. AVP itself does not specify URI schemes for skill sources.

`avp.skill_loaded` means **the SKILL.md body content has been added to the model's active context window**, NOT a registration acknowledgment. (The registration view is `agent_started.data.skills[]`; resolution is `managed_ref_resolved`.) Two emission patterns differentiated by `descriptor.capabilities`:

- **`skills:eager`**: agent injects all resolved bodies at startup. Emit `skill_loaded` once per skill, `step=0`, after `agent_started` and before turn 1.
- **`skills:progressive`**: model decides per-turn. Emit `skill_loaded` when the body actually enters context, with `step=N`. MAY fire multiple times for the same skill (e.g., after compaction).

Agents whose SDK does NOT expose progressive-disclosure load events SHOULD NOT emit `skill_loaded` at all; `agent_started.data.skills[]` still records the registration.

If a skill ref cannot be resolved, the agent MUST emit `managed_ref_resolve_failed` and `agent_stopped(reason: "error")` BEFORE any model turn runs.

## 7. Event reference

Event `type` values are reverse-DNS, past-tense facts, namespaced under `avp.*`.

| Type | Source | One-line semantics |
|---|---|---|
| `avp.run_requested` | `avp://supervisor` | First event. Agent-relayed. Carries `avp.commission` (full snapshot) + `avp.supervisor.name`. |
| `avp.agent_described` | `avp://agent` | Second event. Self-published Descriptor (`avp.descriptor`). |
| `avp.agent_started` | `avp://agent` | Third event. Merged view: what the model will actually see. |
| `avp.agent_stopped` | `avp://agent` | Run has ended; last event of the trajectory. |
| `avp.managed_ref_resolved` | `avp://agent` | One per Commission-declared managed ref successfully resolved at startup. |
| `avp.managed_ref_resolve_failed` | `avp://agent` | Resolver errored or unreachable. Agent stops fail-fast. |
| `avp.model_turn_started` | `avp://agent` | About to call the model. |
| `avp.model_turn_ended` | `avp://agent` | Model response received. Carries OTel `gen_ai.usage.*`. |
| `avp.tool_invoked` | `avp://agent` | Model invoked a tool. |
| `avp.tool_returned` | `avp://agent` | Tool produced a result (or was rejected). |
| `avp.tool_failed` | `avp://agent` | Tool raised an execution error. |
| `avp.subagent_invoked` | `avp://agent` | Parent delegated to a declared subagent. Frame span opens. |
| `avp.subagent_returned` | `avp://agent` | Subagent returned. Frame span closes; pairs with `subagent_invoked` by `span_id`. |
| `avp.subagent_failed` | `avp://agent` | Subagent invocation errored; the model receives an `Error: …` tool_result. |
| `avp.text_emitted` | `avp://agent` | Assistant text content. |
| `avp.reasoning_emitted` | `avp://agent` | Reasoning / thinking block. Distinct from text so consumers can filter chain-of-thought. |
| `avp.refusal_recorded` | `avp://agent` | Model declined the turn. Run terminates with `reason="refused"`. |
| `avp.cost_recorded` | `avp://agent` | Cumulative `RunStateSnapshot`. May carry `avp.cost.source="reported"` on the reconciliation event when the API/SDK hands back an authoritative cost total. |
| `avp.skill_loaded` | `avp://agent` | SKILL.md body added to model context. |
| `avp.error_occurred` | `avp://agent` | Non-tool error. |
| `avp.mcp_server_connected` | `avp://agent` | Connection established to an MCP server. |
| `avp.mcp_server_disconnected` | `avp://agent` | Connection closed. |

Field-level definitions live in [`trajectory.schema.json`](./trajectory.schema.json) (auto-generated from `python/avp/src/avp/types.py`).

### 7.1 `agent_stopped` convenience aliases

`agent_stopped.data` carries `avp.total_tokens`, `avp.total_cost_usd`, `avp.total_turns`, and `avp.duration_ms` at the top level **as convenience aliases**. When non-null they MUST equal the matching field inside `avp.state` (a `RunStateSnapshot`). New consumers SHOULD read `avp.state.*`: the same shape ships on every `cost_recorded` event, so analytics code that targets `avp.state` works uniformly. The top-level fields are scheduled for removal in a future major.

## 8. Conformance

An agent is conforming if and only if:

1. Every event validates against the CloudEvents 1.0 envelope. All events EXCEPT `avp.run_requested` MUST set `source: "avp://agent"`. `avp.run_requested` is the only event with `source: "avp://supervisor"` (agent-relayed).
2. The trajectory opens with the prelude defined in §2.1, in that exact order. `run_requested.data["avp.commission"]` MUST carry a faithful Commission snapshot (refs verbatim). `agent_described.data["avp.descriptor"]` MUST equal the Descriptor the agent publishes via its pre-flight `describe` surface. `agent_started.data.tools` MUST list the EFFECTIVE tool surface (agent built-ins plus MCP-server tools surfaced after `mcp_server_connected`).
3. For every model inference: `model_turn_started` immediately before, `model_turn_ended` immediately after.
4. For every tool call: `tool_invoked` before invocation, then `tool_returned` (success or rejection) or `tool_failed` (execution error).
5. `cost_recorded` at least once per turn. `data["avp.state"]` MUST validate against `RunStateSnapshot`.
6. The last event MUST be `agent_stopped` (source=`avp://agent`). After emitting it, the agent MUST NOT emit additional events.
7. All emitted events MUST validate against `trajectory.schema.json`.

If `Commission.mcp_servers` is non-empty, the agent additionally MUST:

M1. Emit `mcp_server_connected` for each Commission-declared server after resolving its ref and dialing, before the first turn. The event SHOULD carry the live tool catalog (`data["avp.mcp.tools"]`).
M2. Emit `mcp_server_disconnected` for each connected server before `agent_stopped`.
M3. Tag `tool_invoked.data["avp.tool.dispatch_target"] = "mcp_server"` and set `avp.mcp_server_id` for any tool dispatched through an MCP server.
