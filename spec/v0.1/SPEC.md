# Agent Execution Protocol — Specification

**Status:** Draft
**Schema:** [`aep.schema.json`](./aep.schema.json) (JSON Schema Draft 2020-12)
**$id base:** `https://aep.dev/schema/v0.1/`

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

---

## 1. The seam

AEP defines exactly one boundary, between two roles, with **two unidirectional flows** crossing it:

- **Supervisor** — declares the agent's complete environment in a Config sent at startup. Tools the agent can call. Skills the agent can load. Verifiers the agent should run. Hard limits the agent enforces on itself. Once the Config is sent, the supervisor's role is to OBSERVE the trajectory — it does not reach in mid-run.
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

The runner's stdout is the **canonical trajectory**. Every event line MUST contain a `source` field of either `"runner"` or `"supervisor"`.

- **`source: "runner"`** is the overwhelming majority of events — the agent emitting facts about what it did.
- **`source: "supervisor"`** appears only on `tool_exec_resolved` RPC replies. The runner records these verbatim. The supervisor's voice in the record documents who computed the value, not who decided anything.

Implementations MUST NOT strip or rewrite supervisor-recorded events when writing the trajectory.

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
| **Tool execution** | The model calls a `Config.tools` declared tool whose implementation is not local | `tool_exec_request` | `tool_exec_resolved` ∣ `tool_exec_timed_out` |

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
| `before_each_turn` | before every `model_turn_started` |
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

1. Model calls a tool. Runner emits `tool_invoked`.
2. **Local impl:** runner executes the tool, emits `tool_returned` (or `tool_failed`).
3. **RPC impl** (declared in `Config.tools`, implementation not local to the runner): runner emits `tool_exec_request`, suspends, awaits `tool_exec_resolved` or times out, then emits `tool_returned`.
4. If `tool_exec_resolved.error` is set, the runner MUST prefix `Error: ` before returning to the model.
5. If `tool_exec_resolved.output_json` is set, the runner MUST also set `output` to a string representation that the model receives.

`Config.tools` is the schema-typed declaration of RPC tools. Locally-implemented tools (the runner's built-ins like `bash`, file I/O, etc.) are runner-specific and not declared in Config.

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

## 9. The runner loop (normative)

A conforming runner MUST behave as if executing the following algorithm. (The runner MAY reorder operations that are not externally observable, provided the emitted event sequence is indistinguishable.)

### 9.1 Run state

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

    run verifiers_for("before_each_turn"); apply on_failure actions

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
              on timeout: emit tool_exec_timed_out; output = ""
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

All non-RPC-request event types are past-tense facts. `*_request` events keep imperative form because they ARE pending RPCs.

| Type | Source(s) | One-line semantics |
|---|---|---|
| `agent_started` | runner | Run has begun; first event of the trajectory. |
| `agent_stopped` | runner | Run has ended; last event of the trajectory. |
| `model_turn_started` | runner | About to call the model. |
| `model_turn_ended` | runner | Model response received. |
| `tool_invoked` | runner | Model invoked a tool. |
| `tool_returned` | runner | Tool produced a result (or was rejected). |
| `tool_failed` | runner | Tool raised an execution error. |
| `text_emitted` | runner | Assistant text content. |
| `cost_recorded` | runner | Cumulative `RunStateSnapshot` snapshot. |
| `skill_loaded` | runner | SKILL.md loaded into context. |
| `skill_executed` | runner | Skill activated. |
| `error_occurred` | runner | Non-tool error. |
| `tool_exec_request` | runner | Agent calling an RPC tool service. |
| `tool_exec_resolved` | supervisor | Service's reply to a tool_exec_request. |
| `tool_exec_timed_out` | runner | No reply received in time. |
| `verifier_evaluated` | runner | Deterministic pass/fail check (see §7). |

Field-level definitions are in [`aep.schema.json`](./aep.schema.json).

---

## 12. Custom event types

Any `type` value not enumerated in §11 is a custom event. Implementations MAY emit custom events. Consumers MUST:

- Validate them against `EventBase` (the `type`, `source`, `run_id`, `ts` fields).
- Pass them through without error if they do not recognize the `type`.

Implementers SHOULD use dot-namespaced `type` values (`myframework.verifier_result`) to avoid future conflicts. Names listed in §11 are reserved.

For non-spec FIELDS within a known event type, implementers MUST use the `extensions` envelope (an optional object on every event) with dot-namespaced keys.

---

## 13. Conformance

### 13.1 Runner

A runner is conforming if and only if all of the following hold:

1. It reads exactly one valid `Config` (per `config.schema.json`) before emitting any events.
2. The first event it emits MUST be `agent_started` (source=runner). It MUST include `prompt` and `tools` when those are available; each tool entry MUST include `name` and `description`.
3. Every event it emits MUST include a `source` field. Runner-authored events MUST set `source: "runner"`. Supervisor-authored `tool_exec_resolved` RPC replies received over the input channel MUST be recorded into the trajectory verbatim, retaining `source: "supervisor"`.
4. For every model inference, it MUST emit `model_turn_started` immediately before the request and `model_turn_ended` immediately after the response.
5. For every tool call, it MUST emit `tool_invoked` before invocation and either `tool_returned` (success or boundary rejection) or `tool_failed` (execution error) afterward.
6. It MUST emit `cost_recorded` at least once per turn. The `state` field MUST validate against `RunStateSnapshot`.
7. The last event it emits MUST be `agent_stopped` (source=runner). After emitting `agent_stopped`, the runner MUST NOT emit additional events.
8. All emitted events MUST validate against `event.schema.json`.
9. It MUST enforce `Config.boundary` per §9.2 and §9.4. Two conforming runners with identical inputs MUST agree on whether one more turn is permitted.

If `Config.tools` declares any RPC-implementation tool, the runner additionally MUST:

10. Register each declared tool with the LLM using `name`, `description`, `input_schema`.
11. When the model calls a declared tool, emit `tool_exec_request`, suspend, and either: (a) receive a `tool_exec_resolved` with matching `request_id`, record it verbatim, and return its `output` to the model; or (b) emit `tool_exec_timed_out` and return `""`.
12. If `tool_exec_resolved.error` is set, prefix `Error: ` before returning to the model.

If `Config.allowed_tools` is set, the runner additionally MUST:

A1. Verify that every `Config.tools` entry's `name` appears in `Config.allowed_tools`. If any does not, emit `error_occurred` and `agent_stopped` with `reason: "error"` before running any model turn (§8.1).
A2. Reject any tool call whose `tool` name is not in `Config.allowed_tools` by emitting `tool_failed` (after `tool_invoked`) and not executing the tool.

If `Config.verifiers` is non-empty, the runner additionally MUST:

13. Evaluate each `Verifier`'s trigger at the appropriate lifecycle point (per §7.2).
14. Execute the verifier's source (e.g., shell command). The verifier passes iff the source exits 0 (or returns a passed result for non-shell sources).
15. Emit `verifier_evaluated` (source=runner) with `name`, `passed`, and optional `data`/`subject_*` fields.
16. On `passed: false`, take the verifier's declared `on_failure` action: `continue` (no-op), `halt` (emit `agent_stopped` with `reason: "verifier_failed"`), or `inject_correction` (insert `correction_message` as user-role into history before the next turn).
17. Verifier failure MUST NOT alter accounting in `state`; the agent did the work, the verifier just reports on it.

### 13.2 Supervisor

A supervisor is conforming if and only if all of the following hold:

1. The `Config` it sends validates against `config.schema.json`.
2. Every `SupervisorMessage` it sends validates against `supervisor-message.schema.json` (only `tool_exec_resolved` is valid in v0.1).
3. Every `tool_exec_resolved.request_id` corresponds to a `tool_exec_request.request_id` previously emitted by the runner in the same run.

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

This section names the lines so readers don't trip on them. A complete production deployment will involve more than this spec covers; that's by design.

---

## 15. Versioning

- `Config.schema_version` MUST equal `"0.1"`.
- `agent_started.schema_version` MUST equal `"0.1"`.
- Future minor versions MAY add new event types, fields, or enum values. They MUST NOT remove or repurpose existing ones.
- Future major versions MAY introduce breaking changes — including tightening event subtypes to forbid unknown top-level fields (use the `extensions` envelope today to avoid breakage).

A runner that receives a `Config` with an unsupported `schema_version` MUST emit `error_occurred` with `code: "unknown"` and a descriptive message, then emit `agent_stopped` with `reason: "error"`.
