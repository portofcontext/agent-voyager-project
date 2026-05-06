# Agent Execution Protocol — Specification

**Status:** Draft
**Schema:** [`aep.schema.json`](./aep.schema.json) (JSON Schema Draft 2020-12)
**$id base:** `https://aep.dev/schema/v0.1/`

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

## 0. Built on

AEP specializes — it does not reinvent — the following industry specs:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`, `source`, `type`, `subject`, `time`, `datacontenttype`, `data`).
- **OpenTelemetry GenAI semantic conventions** for token / cost / model / tool attribute names inside `data` (e.g., `gen_ai.usage.input_tokens`, `gen_ai.tool.name`).
- **OpenTelemetry span identification** (`trace_id`, `span_id`, `parent_span_id`) on every event so trajectories reconstruct as a span tree.
- **JSON-RPC 2.0** for the RPC payload inside `tool_exec_request.data.rpc` and `tool_exec_resolved.data.rpc`.
- **MCP 2025-11-25** tool descriptors (`Config.tools[]` uses `inputSchema`, `outputSchema`, `_meta` per the MCP shape).
- **Agent Skills** (agentskills.io) for `SKILL.md` files referenced by `Config.skills[]`.
- **JSON Schema Draft 2020-12** for this specification's machine-readable form.

AEP-specific concepts — **verifiers**, **boundary semantics**, the **no-mid-run-reach-in topology**, and the **trajectory-as-source-of-truth contract** — live under the `aep.*` attribute namespace.

See [`FOUNDATIONS.md`](../../FOUNDATIONS.md) for the full mapping rationale.

---

## 1. The seam

AEP defines exactly one boundary, between two roles, with **two unidirectional flows** crossing it:

- **Supervisor** — declares the agent's complete environment in a Config sent at startup. Tools the agent can call. Skills the agent can load. Verifiers the agent should run. Hard limits the agent enforces on itself. Once the Config is sent, the supervisor observes the trajectory and replies to any agent-initiated RPC requests — it does not reach in unilaterally.
- **Runner** — runs the agent inside the supervisor's environment. Emits a stream of facts (events) that the supervisor observes.

```
                                  agent's environment
                          (boundary, tools, skills, verifiers, prompt)
                                              │
                                              ▼
   supervisor ──── Config (one-time, setup) ──▶ runner
                                              │
                                              ▼
                                        runs the agent
                                              │
                                              ▼
   supervisor ◀────────── events (continuous, run-end) ────── runner
```

This is the v0.1 architectural choice: **control flows down at setup; observation flows up during the run.** No mid-run bidirectional negotiation. The agent's bounded context is intact because its environment was fully declared up front; the agent never gets blocked by a force it didn't know about.

The one apparent exception is **environmental services**: when the agent calls a tool whose implementation is out-of-process, the agent issues an RPC and awaits a reply. This is **agent-initiated** — the supervisor stood up the service at Config time but doesn't decide anything mid-run. See §6.

---

## 2. Message classes

| Class | Direction | Cardinality | Schema entry point |
|---|---|---|---|
| `Config` | supervisor → runner | exactly one, at startup | [`config.schema.json`](./config.schema.json) |
| `Event` | runner → supervisor (and supervisor RPC service → runner for replies, recorded into the same trajectory) | streamed throughout the run | [`event.schema.json`](./event.schema.json) |
| `SupervisorMessage` | supervisor service → runner | streamed, in reply to RPC requests only | [`supervisor-message.schema.json`](./supervisor-message.schema.json) |

`SupervisorMessage` in v0.1 is exactly one event type — `tool_exec_resolved` — the RPC reply the runner records into the trajectory verbatim (`source: "supervisor"`). Nothing else crosses this channel.

---

## 3. The trajectory

The runner's stdout is the **canonical trajectory**. Every event is a CloudEvents 1.0 envelope (per §0). The `source` attribute is a URI that identifies the producer:

- **`source: "aep://runner"`** is the overwhelming majority of events — the agent emitting facts about what it did.
- **`source: "aep://supervisor"`** appears only on `aep.tool_exec_resolved` RPC replies routed through the supervisor channel. The runner records these verbatim.
- **`source: "aep://mcp/<server_id>"`** appears on `aep.tool_exec_resolved` replies that came from a Config-declared MCP server (see `Config.mcp_servers`).

The supervisor's voice in the record documents who computed the value, not who decided anything. Implementations MUST NOT strip or rewrite supervisor-recorded events when writing the trajectory.

Every event's `data` payload carries an OpenTelemetry **span triple** — `trace_id` (16 random bytes, 32 lowercase hex chars), `span_id` (8 random bytes, 16 hex chars), and `parent_span_id` (or 16 zeros for the root). The agent span is the run; turn / tool / RPC spans nest inside it. Consumers reconstruct the trajectory as a span tree.

---

## 4. Conformance — overview

A **runner** is conforming if it reads exactly one valid `Config` at startup, runs the agent inside the declared environment per §9, emits the events required by §10–§11, records supervisor-emitted RPC replies verbatim, and enforces boundary semantics per §9.4. See §13.1 for the full checklist.

A **supervisor** is conforming if every `Config` it sends validates against `config.schema.json` and any `SupervisorMessage` (RPC reply) it sends validates against `supervisor-message.schema.json`. See §13.2.

---

## 5. Transports

A conforming implementation MUST support at least one transport. Both transports use the same JSON Schemas; only the framing differs.

### 5.1 stdio (local)

- The supervisor launches the runner as a subprocess.
- The supervisor MUST write a single `Config` JSON document to the runner's stdin, terminated by `\n`.
- The runner MUST read exactly one `Config` from stdin before emitting any events.
- After reading `Config`, stdin MUST remain open for `SupervisorMessage` lines (NDJSON, one per line) — RPC replies the agent is waiting on.
- The runner MUST emit `Event` documents to stdout as NDJSON, one JSON object per line, no pretty-printing, terminated by `\n`. The runner MUST flush stdout after each line.

### 5.2 HTTP (remote)

- The supervisor POSTs a single `Config` to start a run; the runner streams events back via Server-Sent Events.
- For RPC interactions: when the runner emits `tool_exec_request`, it POSTs the event to a `service_callback_url` declared at Config time; the response body MUST be a `tool_exec_resolved` SupervisorMessage. (See `Config.service_callback_url` if shipped — TBD by transport profile.)

---

## 6. Environmental services (agent-initiated RPC)

An **environmental service** is an out-of-process implementation the supervisor stood up at Config time and the agent calls into during a run. v0.1 has one such service:

| Service kind | Triggered by | Opening event | Closing events |
|---|---|---|---|
| **Tool execution** | The model calls a `Config.tools` declared tool whose implementation is not local | `aep.tool_exec_request` | `aep.tool_exec_resolved` ∣ `aep.tool_exec_timed_out` |

The opening event's `data.rpc` is a [JSON-RPC 2.0](https://www.jsonrpc.org/specification) request: `{jsonrpc: "2.0", id, method, params}`. By MCP convention, `method` is `"tools/call"` and `params` is `{name, arguments}`. The closing event's `data.rpc` is a JSON-RPC 2.0 response: `{jsonrpc: "2.0", id, result}` on success, `{jsonrpc: "2.0", id, error: {code, message, data?}}` on failure.

Lifecycle:

```
       ┌────────────────────────────────────────────────────┐
       │  1. Runner emits an OPENING event (source=runner)  │
       │     • assigns a fresh request_id                   │
       │     • declares timeout_ms                          │
       │     • runner is PAUSED for this RPC                │
       └────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
   ┌──────────────────────┐     ┌──────────────────────────────┐
   │ Service replies      │     │ timeout_ms elapses           │
   │ (source=supervisor)  │     │                              │
   │                      │     │ Runner emits a TIMED-OUT     │
   │ Runner records reply │     │ event (source=runner)        │
   │ verbatim             │     │ and applies the fallback     │
   └──────────────────────┘     └──────────────────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
                       Runner resumes
```

This is RPC. The agent calls; the service replies. The supervisor's process happens to be the service (or stood it up), but at runtime the supervisor is not making decisions — it is responding to a request the agent made about its declared environment.

`request_id` correlates the RPC across opening and closing events. `call_id` (from the underlying tool call) appears alongside `request_id` on `tool_exec_*` events when relevant.

> **Naming asymmetry, deliberately.** Opening events use the imperative noun form (`tool_exec_request`) because they ARE pending RPCs. Closing events use past-tense (`tool_exec_resolved`, `tool_exec_timed_out`) because they are facts about what happened. Reading any single line should make clear whether the runner is waiting on a service.

---

## 7. Verifiers

A **verifier** is a deterministic Boolean check the agent runs at a declared trigger. The Config declares verifiers; the agent runs them; the trajectory records `verifier_evaluated` events with `passed: true|false`.

The supervisor declares the rule upfront in Config; the agent enforces it deterministically at runtime. No mid-run reach-in by the supervisor.

### 7.1 Verifier config

```jsonc
{
  "verifiers": [
    {
      "name": "tests-pass",
      "trigger": "after_each_turn",
      "source": { "shell": "cargo test --quiet" },
      "on_failure": "halt"
    },
    {
      "name": "no-secrets-leaked",
      "trigger": "on_tool:write_file",
      "source": { "shell": "scripts/scan_secrets.sh" },
      "on_failure": "inject_correction",
      "correction_message": "The last write contained a secret. Revert it and try again."
    },
    {
      "name": "ingest-atomicity",
      "trigger": "at_end",
      "source": { "shell": "scripts/check_invariants.sh" },
      "on_failure": "continue"
    }
  ]
}
```

### 7.2 Triggers

| Trigger | Fires |
|---|---|
| `before_first_turn` | once, after `agent_started`, before turn 1 |
| `after_each_turn` | after every `model_turn_ended` |
| `on_tool:<name>` | after `tool_returned` for the named tool |
| `at_end` | once, after the final turn, before `agent_stopped` |

### 7.3 `on_failure` actions

| Value | Behavior on `passed: false` |
|---|---|
| `continue` | Emit `verifier_evaluated`; proceed normally. |
| `halt` | Emit `verifier_evaluated`; emit `agent_stopped` with `reason: "verifier_failed"`. |
| `inject_correction` | Emit `verifier_evaluated`; insert `correction_message` as a user-role message into conversation history before the next turn. |

`correction_message` is REQUIRED when `on_failure` is `inject_correction`.

### 7.4 Wire flow

1. Trigger fires. Runner executes the verifier's source (e.g., shell command).
2. Runner emits `verifier_evaluated` (source=runner) with `name`, `passed`, optional `subject_call_ids` / `subject_request_ids` / `data`.
3. On `passed: false`, runner takes the declared `on_failure` action.

The supervisor is not involved at runtime. The verifier was declared in Config; the agent enforces it.

### 7.5 Path resolution

Shell verifier paths (e.g., `scripts/scan_secrets.sh`) resolve relative to the **runner's current working directory** — by convention, the agent's workspace. A verifier whose source is `cargo test` requires `Cargo.toml` to be in the workspace; one whose source is `scripts/scan_secrets.sh` requires that file to exist there.

How the workspace gets provisioned (git checkout, container volume, tmpdir) is **outside AEP's scope** — see §14. The supervisor's deployment layer is responsible for ensuring referenced files exist before the run starts. For verifiers whose code shouldn't ship to the workspace, expose them as RPC tools (§8) the agent calls and have the supervisor's service host the logic.

---

## 8. Tools

The Config declares `tools[]` the supervisor wants exposed to the model. From the agent's perspective every tool is just a tool — the agent does not know whether the implementation is in-process (a Python callable the runner has registered) or out-of-process (an environmental service called via the RPC lifecycle in §6).

Wire flow:

1. Model calls a tool. Runner emits `aep.tool_invoked`.
2. **Local impl:** runner executes the tool, emits `aep.tool_returned` (or `aep.tool_failed`).
3. **RPC impl** (declared in `Config.tools`, implementation not local to the runner): runner emits `aep.tool_exec_request`, suspends, awaits `aep.tool_exec_resolved` or times out, then emits `aep.tool_returned`.
4. If `tool_exec_resolved.data.rpc.error` is set (JSON-RPC error reply), the runner MUST prefix `Error: ` before returning to the model.
5. If `tool_exec_resolved.data.rpc.result` is a structured value (object/array, not a string), the runner MUST surface it on `tool_returned.data["aep.tool.result.structured"]` and ALSO produce a string serialization on `tool_returned.data["aep.tool.result.text"]` for the model.

`Config.tools` is the schema-typed declaration of RPC tools (MCP-shaped: `name`, `description`, `inputSchema`). Locally-implemented tools (the runner's built-ins like `bash`, file I/O, etc.) are runner-specific and not declared in Config.

### 8.1 Restricting the exposed tool set: `Config.allowed_tools`

`Config.allowed_tools` is an **optional allowlist** of tool names the runner exposes to the model. It is the supervisor's lever for narrowing the agent's tool surface without enumerating the runner's internals.

Semantics:

- **Absent.** The runner exposes all of its built-ins plus every `Config.tools` entry. This is the default, backwards-compatible behavior.
- **Present.** The runner MUST expose ONLY tools whose names are in this list. Both `Config.tools` (RPC) entries and runner built-ins are filtered through it.
- **Cross-field coherence.** Every name in `Config.tools` MUST also appear in `Config.allowed_tools` (when set). A `Config.tools` entry missing from `allowed_tools` is a configuration conflict — the supervisor declared an RPC tool while simultaneously forbidding its exposure. The runner MUST detect this at startup, emit `error_occurred`, and stop with `reason: "error"` before any model turn runs.
- **Unrecognized names.** Names in `allowed_tools` that match neither a `Config.tools` entry nor a runner built-in are runner-specific. The runner MAY validate them at startup; failing that, the runtime check rejects any actual call to such a name as `tool_failed` (see below).
- **Runtime rejection.** If the model nevertheless calls a tool whose name is not in `allowed_tools`, the runner MUST emit `tool_failed` with an error message identifying the allowlist as the cause, and MUST NOT execute the tool. (`tool_invoked` is still emitted first to keep the trajectory faithful — the agent attempted the call.)

Supervisors MAY maintain category-based profiles (e.g., "DDD-strict", "Compliance") at the framework layer that resolve to a specific `allowed_tools` per runner; AEP itself takes no opinion on profiles.

---

## 8.5 Subagents

`Config.subagents[]` declares **delegate agents** the parent agent may invoke by name. A Subagent is a top-level Config primitive alongside `tools` and `skills` — the supervisor declares the full set up front (no mid-run reach-in); the parent agent picks one to delegate to at runtime. The shape mirrors `Config` itself: each Subagent carries its own `system_prompt`, `model`, `tools`, `skills`, `verifiers`, `boundary`, `output_schema` — the environment slice the subagent runs inside.

Field-level definitions live in [`config.schema.json#/$defs/Subagent`](./config.schema.json) (auto-generated). v0.1 specifies the wire and lifecycle; richer dispatch (tools-inside-subagents, recursion, verifier cascade) is specified but not required to be exercised by the prototype runners.

**Wire flow.**

1. Model invokes a tool whose name matches a `Config.subagents[].name`. Runner emits `aep.subagent_invoked` (NOT `aep.tool_invoked`). The event's `data.span_id` is the **frame span** for this invocation.
2. Runner runs the subagent within the declared environment slice. Any nested events the subagent emits (model turns, tool calls, text) MUST set `data.parent_span_id` to the frame span (or descend from it transitively). The trajectory reconstructs as one tree.
3. Runner emits `aep.subagent_returned` carrying `data.aep.subagent.result.text` plus a `RunStateSnapshot` rollup at `data.aep.subagent.usage`. The `data.span_id` MUST equal the matching `subagent_invoked.data.span_id` so consumers pair them.
4. If invocation fails (no driver wired, exception, or driver reported error), runner emits `aep.subagent_failed` with `data.aep.subagent.error` instead of `subagent_returned`. The model receives an `Error: …` tool_result for symmetry with §8 step 4.
5. The subagent's spend (cost, tokens) MUST be rolled into the parent run's cumulative `RunStateSnapshot`. Per-subagent attribution is preserved on `subagent_returned.data.aep.subagent.usage`.

**Two observability modes.** Runners MAY expose subagent internals at different fidelity:

- **Transparent.** The runner owns the sub-loop (driver pattern) and emits `model_turn_*` / `tool_*` / `text_emitted` for the subagent, parented under the frame span. Consumers see the full nested span tree.
- **Opaque.** The runner delegates to an SDK that doesn't surface subagent internals (translator pattern). Only `subagent_invoked` and `subagent_returned` are emitted; the wire shape is "thin" but well-formed. Consumers MUST NOT assume the absence of nested events implies the subagent ran trivially — only that this runner cannot observe the internals.

Both modes produce the same outer wire shape; the second is a strict subset of the first.

**Subagent ↔ tool collision.** Subagent names MUST NOT collide with `Config.tools[].name` or runner built-in tool names. A collision is a configuration conflict — the runner MUST detect this at startup, emit `error_occurred`, and stop with `reason: "error"` before any model turn runs. (Same wire shape as the §8.1 allowed-tools coherence check.)

**`allowed_tools` applies to subagents.** When `Config.allowed_tools` is set, every name in `Config.subagents[]` MUST also appear there, by the same rule that applies to `Config.tools[]`. The model-facing surface is one allowlist over both kinds.

**`agent_started.data.subagents`.** When `Config.subagents` is non-empty, the runner MUST surface the model-facing subagent declaration on `agent_started.data.subagents[]` (parallel to `data.tools[]` and `data.skills[]`). Each entry carries `name`, `description`, and optional `inputSchema` (MCP-shaped). Consumers can read this without parsing the Config a second time.

---

## 9. The runner loop (normative)

A conforming runner MUST behave as if executing the following algorithm. (The runner MAY reorder operations that are not externally observable, provided the emitted event sequence is indistinguishable.)

### 9.1 Run state and the definition of a turn

A **turn** in AEP is exactly one `model_turn_started` / `model_turn_ended`
pair where the model produced new output (either text or tool calls or
both). Continuations and SDK-internal restatements that do not represent a
fresh model call MUST NOT be counted as turns.

This matters most for translator-pattern runners wrapping SDKs that emit
"assistant message" objects for things that aren't fresh model calls (e.g.,
follow-up wrappers around tool results). Translator runners MUST count an
event as a turn only when the SDK-reported usage carries non-zero new
output tokens (delta-output > 0), or — if the SDK doesn't report per-call
usage — when the message includes content the model itself produced.
Wrappers that double-count are non-conformant: §9.2 promises `max_steps: N`
runs EXACTLY N turns, and §9.4 requires two conforming runners to agree on
"is one more turn permitted" for any given Config.

The runner maintains a `RunStateSnapshot` (see [`aep.schema.json#/$defs/RunStateSnapshot`](./aep.schema.json)) tracking `total_turns`, `total_cost_usd`, `total_tokens`, etc.

### 9.2 Boundary check (normative algorithm)

Strict greater-than. Cost and tokens checked AFTER each `model_turn_ended` (and after each `tool_returned` for cost/tokens). The step boundary is checked BEFORE starting a new turn against the projected next-turn count.

```
function check_consumption(state) -> (decision, reason | null):
    if config.boundary.max_cost_usd is set and state.total_cost_usd > config.boundary.max_cost_usd:
        return ("stop", "budget_exhausted")
    if config.boundary.max_tokens is set and state.total_tokens > config.boundary.max_tokens:
        return ("stop", "token_limit")
    return ("continue", null)

function check_step_projection(state) -> (decision, reason | null):
    projected_turns = state.total_turns + 1
    if config.boundary.max_steps is set and projected_turns > config.boundary.max_steps:
        return ("stop", "turn_limit")
    return ("continue", null)
```

`max_steps: N` runs EXACTLY N turns. Cost/tokens MAY overshoot a max by one final turn since cost cannot be projected pre-call.

### 9.3 The loop

```
read config from stdin
emit agent_started
emit skill_loaded for each loaded skill
run verifiers_for("before_first_turn"); apply on_failure actions if any fail

loop:
    (decision, reason) = check_step_projection(state)
    if decision == "stop":
        run verifiers_for("at_end"); apply on_failure actions
        emit agent_stopped(reason); return

    state.total_turns += 1
    emit model_turn_started(step)
    response = call_model()
    emit model_turn_ended(step, tokens, cost, ...)

    state.total_cost_usd += response.cost_usd
    state.total_tokens   += response.tokens_input + response.tokens_output
    emit cost_recorded(state)

    (decision, reason) = check_consumption(state)
    if decision == "stop":
        run verifiers_for("at_end")
        emit agent_stopped(reason); return

    for tool_call in response.tool_calls:
        emit tool_invoked(call_id, tool, input)
        if tool is config-declared (RPC-impl):
            emit tool_exec_request(request_id, ...)
            wait for tool_exec_resolved OR timeout_ms
              on response: record verbatim; output = response.output (with "Error: " prefix iff error set)
              on timeout: emit tool_exec_timed_out; output = "Error: tool execution timed out after Nms"
        else:
            output = execute_tool_locally(input)
        emit tool_returned(call_id, output)

        run verifiers_for("on_tool:" + tool); apply on_failure actions

        (decision, reason) = check_consumption(state)
        if decision == "stop":
            emit agent_stopped(reason); return

    run verifiers_for("after_each_turn"); apply on_failure actions

    if model converged:
        run verifiers_for("at_end")
        emit agent_stopped("converged"); return

apply_on_failure_action(verifier, result):
    if result.passed: return
    if verifier.on_failure == "halt":
        emit agent_stopped("verifier_failed"); return EXIT_FROM_OUTER_LOOP
    if verifier.on_failure == "inject_correction":
        insert verifier.correction_message as user-role into history
    # "continue" → nothing
```

### 9.4 Cost / token accounting rules (normative)

- `cost_usd` on `model_turn_ended` is the BILLABLE cost (post-cache-discount).
- `tokens_input` on `model_turn_ended` is the total input tokens INCLUDING cache-read tokens.
- `tokens_cache_read` and `tokens_cache_write` are informational; they MUST NOT alter `state.total_tokens` independently.
- `state.total_cost_usd` and `state.total_tokens` are monotonically non-decreasing.
- Two conforming runners with identical inputs MUST agree on whether one more turn is permitted under any given boundary.
- **Translator runners over cumulative-usage SDKs.** Some SDKs (notably the Claude Agent SDK) report usage as a running session total per message rather than as a per-call delta. Translators MUST derive deltas (subtract previous cumulative) to populate per-turn `tokens_*` and `cost_usd` correctly. When the SDK's cumulative drops without warning (`cum < prev`), the translator MUST emit `error_occurred` with `code: "accounting_reset"` rather than silently clamping; consumers cannot distinguish a swallowed delta from a legitimate quiet turn otherwise. SDKs that signal context compaction or sub-agent dispatch via lifecycle events SHOULD be hooked so the translator resets its baselines deliberately, not via the error path.

---

## 10. Three classes of trajectory facts

The trajectory holds three semantically distinct kinds of facts. Implementations and supervisor frameworks SHOULD surface them separately to consumers:

| Class | Event types | Semantics |
|---|---|---|
| **What the agent did** | `model_turn_*`, `tool_invoked`, `tool_returned`, `tool_failed`, `text_emitted` | Mechanical actions the agent took |
| **What the rules said** | `verifier_evaluated` | Deterministic Boolean checks — invariants, tests, schema validation |
| **What the run cost** | `cost_recorded`, `model_turn_ended.usage` | Resource accounting |

This separation is what makes trajectories useful to business users: a non-technical reviewer can answer "did this run respect the contract?" by filtering on `verifier_evaluated.passed=false`, without having to read prose annotations or run an LLM judge.

Interpretive narrative (the supervisor saying "this is a SuspiciousWriteDetected") is a post-hoc concern — annotation of saved trajectories, not a runtime event class. v0.1 deliberately leaves this out of the wire.

---

## 11. Event reference

All non-RPC-request event types are past-tense facts. `*_request` events keep imperative form because they ARE pending RPCs. Event `type` values are reverse-DNS, namespaced under `aep.*`.

| Type | Source(s) | One-line semantics |
|---|---|---|
| `aep.agent_started` | `aep://runner` | Run has begun; first event of the trajectory. |
| `aep.agent_stopped` | `aep://runner` | Run has ended; last event of the trajectory. |
| `aep.model_turn_started` | `aep://runner` | About to call the model. |
| `aep.model_turn_ended` | `aep://runner` | Model response received. Carries OTel `gen_ai.usage.*`. |
| `aep.tool_invoked` | `aep://runner` | Model invoked a tool. |
| `aep.tool_returned` | `aep://runner` | Tool produced a result (or was rejected). |
| `aep.tool_failed` | `aep://runner` | Tool raised an execution error. |
| `aep.subagent_invoked` | `aep://runner` | Parent agent delegated to a declared subagent (see §8.5). Frame span opens. |
| `aep.subagent_returned` | `aep://runner` | Subagent returned to its parent. Frame span closes; pairs with `subagent_invoked` by `span_id`. |
| `aep.subagent_failed` | `aep://runner` | Subagent invocation errored; the model receives an `Error: …` tool_result. |
| `aep.text_emitted` | `aep://runner` | Assistant text content. |
| `aep.cost_recorded` | `aep://runner` | Cumulative `RunStateSnapshot` snapshot. |
| `aep.skill_loaded` | `aep://runner` | SKILL.md loaded into context. |
| `aep.skill_executed` | `aep://runner` | Skill activated. |
| `aep.error_occurred` | `aep://runner` | Non-tool error. |
| `aep.tool_exec_request` | `aep://runner` | Agent calling an RPC tool service (carries JSON-RPC request). |
| `aep.tool_exec_resolved` | `aep://supervisor` ∣ `aep://mcp/<server_id>` | Service's reply to a tool_exec_request (carries JSON-RPC response). |
| `aep.tool_exec_timed_out` | `aep://runner` | No reply received in time. |
| `aep.verifier_evaluated` | `aep://runner` | Deterministic pass/fail check (see §7). |
| `aep.mcp_server_connected` | `aep://runner` | Connection established to a Config-declared MCP server. |
| `aep.mcp_server_disconnected` | `aep://runner` | Connection to an MCP server closed. |

Field-level definitions are in [`aep.schema.json`](./aep.schema.json) and [`event.schema.json`](./event.schema.json) (auto-generated from the Pydantic models in `python/aep/src/aep/types.py`).

---

## 12. Custom event types and vendor extensions

Any `type` value not in the `aep.*` namespace is a custom event. Implementations MAY emit custom events. Consumers MUST:

- Validate them against the CloudEvents 1.0 envelope shape — `specversion`, `id`, `source`, `type`, `time`, `data` MUST be present.
- Pass them through without error if they do not recognize the `type`.

Implementers SHOULD use reverse-DNS `type` values (e.g. `com.example.verifier_result`) to avoid future conflicts. The `aep.*` namespace is reserved.

For **non-spec fields within a known event type**: place them inside `data` under a vendor-namespaced key (e.g., `vendor.priority`, `acme.region`). The reference parser allows extra keys to round-trip through `data` verbatim, so vendor extensions don't require a separate envelope.

---

## 13. Conformance

### 13.1 Runner

A runner is conforming if and only if all of the following hold:

1. It reads exactly one valid `Config` (per `config.schema.json`) before emitting any events.
2. The first event it emits MUST be `aep.agent_started` (source=`aep://runner`). It MUST include `prompt` when available. The `data.tools` field MUST list the EFFECTIVE tool surface — the union of `Config.tools` entries and the runner's built-in tools, filtered by `Config.allowed_tools` if set. Consumers rely on this to determine what the model could actually call. Each tool entry MUST include `name`.
3. Every event it emits MUST conform to the CloudEvents 1.0 envelope shape (`specversion`, `id`, `source`, `type`, `time`, `data`). Runner-authored events MUST set `source: "aep://runner"`. `aep.tool_exec_resolved` RPC replies received over the input channel MUST be recorded into the trajectory verbatim, retaining their original `source` (`aep://supervisor` or `aep://mcp/<server_id>`).
4. For every model inference, it MUST emit `aep.model_turn_started` immediately before the request and `aep.model_turn_ended` immediately after the response.
5. For every tool call, it MUST emit `aep.tool_invoked` before invocation and either `aep.tool_returned` (success or boundary rejection) or `aep.tool_failed` (execution error) afterward.
6. It MUST emit `aep.cost_recorded` at least once per turn. The `data["aep.state"]` field MUST validate against `RunStateSnapshot`.
7. The last event it emits MUST be `aep.agent_stopped` (source=`aep://runner`). After emitting `agent_stopped`, the runner MUST NOT emit additional events.
8. All emitted events MUST validate against `event.schema.json`.
9. It MUST enforce `Config.boundary` per §9.2 and §9.4. Two conforming runners with identical inputs MUST agree on whether one more turn is permitted.

If `Config.tools` declares any RPC-implementation tool, the runner additionally MUST:

10. Register each declared tool with the LLM using its `name`, `description`, and `inputSchema` (MCP-shaped, camelCase).
11. When the model calls a declared tool, emit `aep.tool_exec_request` with a fresh `data["aep.request_id"]` and a JSON-RPC 2.0 request payload at `data.rpc`, suspend, and either: (a) receive an `aep.tool_exec_resolved` with matching request id, record it verbatim, and return its result to the model; or (b) emit `aep.tool_exec_timed_out` and return `"Error: tool execution timed out after Nms"` (where N is the declared `timeout_ms`).
12. If `tool_exec_resolved.data.rpc.error` is set, prefix `Error: ` before returning to the model.

If `Config.mcp_servers` is non-empty, the runner additionally MUST:

M1. Emit `aep.mcp_server_connected` for each declared MCP server before the first turn.
M2. Emit `aep.mcp_server_disconnected` for each connected MCP server before `aep.agent_stopped`.
M3. Route `tools/call` JSON-RPC requests for MCP-server-hosted tools through that server; the response's `tool_exec_resolved.source` MUST be `aep://mcp/<server_id>`.

If `Config.allowed_tools` is set, the runner additionally MUST:

A1. Verify that every `Config.tools` entry's `name` appears in `Config.allowed_tools`. If any does not, emit `aep.error_occurred` and `aep.agent_stopped` with `data["aep.reason"]: "error"` before running any model turn (§8.1).
A2. Reject any tool call whose `tool` name is not in `Config.allowed_tools` by emitting `aep.tool_failed` (after `aep.tool_invoked`) and not executing the tool.

If `Config.verifiers` is non-empty, the runner additionally MUST:

13. Evaluate each `Verifier`'s trigger at the appropriate lifecycle point (per §7.2).
14. Execute the verifier's source (e.g., shell command). The verifier passes iff the source exits 0 (or returns a passed result for non-shell sources).
15. Emit `aep.verifier_evaluated` (source=`aep://runner`) with `data["aep.verifier.name"]`, `data["aep.verifier.passed"]`, `data["aep.verifier.duration_ms"]`, and optional `data["aep.verifier.data"]` / `data["aep.verifier.subject_*"]` fields.
16. On `passed: false`, take the verifier's declared `on_failure` action: `continue` (no-op), `halt` (emit `aep.agent_stopped` with `reason: "verifier_failed"`), or `inject_correction` (insert `correction_message` as user-role into history before the next turn).
17. Verifier failure MUST NOT alter accounting in `state`; the agent did the work, the verifier just reports on it.
18. If the runner cannot honor a declared `Config.verifiers` entry under its execution model, it MUST emit `aep.error_occurred` and `aep.agent_stopped` with `reason: "error"` at startup, before any model turn runs. Silent acceptance with runtime degradation (the verifier is in Config but `verifier_evaluated` is never emitted, or `on_failure: halt` is downgraded to `continue` because the runner cannot abort) is a violation. This rule mirrors A1 — declared environment features the runner cannot enforce MUST fail loud at startup.

### 13.2 Supervisor

A supervisor is conforming if and only if all of the following hold:

1. The `Config` it sends validates against `config.schema.json`.
2. Every `SupervisorMessage` it sends validates against `supervisor-message.schema.json` (only `aep.tool_exec_resolved` is valid in v0.1).
3. Every `tool_exec_resolved.data["aep.request_id"]` corresponds to a `tool_exec_request.data["aep.request_id"]` previously emitted by the runner in the same run.
4. The reply's `data.rpc` MUST be a valid JSON-RPC 2.0 response object with exactly one of `result` or `error` set.

Supervisors MUST NOT send unsolicited messages. Runners MAY ignore unsolicited messages.

---

## 14. Deployment scope

AEP defines the **wire format**, not the deployment topology. The following are explicitly **out of scope**, and implementations choose:

- **Workspace provisioning.** What directory the runner runs in, how files (verifier scripts, reference data, source trees) get there, and how it's cleaned up after — git checkout, container volume mount, tmpdir, NFS share, etc.
- **Secret injection.** How API keys and credentials reach the runner process (env vars, secrets manager, mounted files).
- **Service hosting.** Where the supervisor's RPC tool services run, how they're discovered, how they're scaled.
- **Runner placement.** Local subprocess, Docker container, remote VM, serverless function, browser sandbox.
- **OS-level sandboxing.** seccomp, AppArmor, cgroups, network policies, filesystem capabilities.
- **Authentication of the supervisor↔runner channel** beyond what stdio / HTTP transports inherit from their environment.

The agent's **workspace** is conventionally the runner's current working directory (CWD). Shell verifier paths (§7.5) and any tool inputs containing relative paths resolve there. The supervisor's deployment layer — whatever it is — is responsible for ensuring referenced scripts and files exist in that workspace before the run starts.

### 14.1 Pattern: pre-turn world refresh

A common temptation is "I want to update the agent's view of the world between turns" — re-read a config file, re-fetch a dashboard, inject the current build status. This is sometimes called *re-observation*. **AEP does not provide a hook for this**, by design — mid-run reach-in by the supervisor breaks the bounded-context guarantee that makes trajectories meaningful.

The supported pattern is to expose the world refresh as an **RPC tool** (§8). The agent calls it; the supervisor's service computes the current value; the runner records `tool_exec_request` / `tool_exec_resolved` into the trajectory. The agent decides when to refresh and which information to pull, the trajectory shows exactly what context informed each turn, and there's no asymmetry between driver-pattern and translator-pattern runners (both can call RPC tools cleanly).

This section names the lines so readers don't trip on them. A complete production deployment will involve more than this spec covers; that's by design.

---

## 15. Versioning

- `Config.schema_version` MUST equal `"0.1"`.
- `agent_started.data["aep.schema_version"]` MUST equal `"0.1"`.
- Future minor versions MAY add new event types, fields, or enum values. They MUST NOT remove or repurpose existing ones.
- Future major versions MAY introduce breaking changes. Vendor-namespaced keys (`vendor.*`, `com.example.*`) inside `data` round-trip verbatim today (per §12), insulating extensions from spec drift.

A runner that receives a `Config` with an unsupported `schema_version` MUST emit `aep.error_occurred` with `data["aep.error.code"]: "unknown"` and a descriptive message, then emit `aep.agent_stopped` with `data["aep.reason"]: "error"`.
