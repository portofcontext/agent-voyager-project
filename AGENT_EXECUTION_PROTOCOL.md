# Agent Execution Protocol (AEP)

> **Status:** Draft spec (v0.1 model)
> **Normative spec:** [`spec/v0.1/SPEC.md`](./spec/v0.1/SPEC.md)
> **JSON Schemas:** [`spec/v0.1/`](./spec/v0.1/)
> **Conformance suite:** [`conformance/v0.1/`](./conformance/v0.1/)
>
> AEP is an open standard. Any agent runtime can implement AEP compliance without depending on any specific supervisor.

---

## What AEP is

AEP defines exactly one boundary, between two roles, with **two unidirectional flows** crossing it.

- **Supervisor** — declares the agent's complete environment in a Config sent at startup. Boundary, tools, skills, verifiers, prompts. Once the Config is sent, the supervisor's role is to OBSERVE the trajectory.
- **Runner** — runs the agent inside the declared environment. Emits a stream of facts (events) that the supervisor consumes.

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

This is the load-bearing design choice: **control flows down at setup; observation flows up during the run.** No mid-run bidirectional negotiation. The agent's bounded context is intact because its environment was fully declared up front; the agent never gets blocked by a force it didn't know about. That's what makes AEP-driven supervisor frameworks DDD-correct: rules live with the state they govern, declared once, enforced by the agent.

The one apparent exception is **environmental services**: when the agent calls a Config-declared tool whose implementation is out-of-process, the agent issues an RPC and awaits a reply. This is **agent-initiated** — the supervisor pre-deployed the service, but at runtime the supervisor is replying to a request the agent made about its declared environment, not deciding anything.

---

## AEP Config — the environment declaration

```json
{
  "schema_version": "0.1",
  "run_id": "auth-refactor-20260502-abc123",

  "tools": [
    {
      "name": "lookup_user",
      "description": "Look up a user by email.",
      "input_schema": { "type": "object", "required": ["email"], "properties": { "email": { "type": "string" } } },
      "timeout_ms": 15000
    }
  ],
  "allowed_tools": ["lookup_user", "bash"],
  "verifiers": [
    { "name": "tests-pass", "trigger": "after_each_turn", "source": { "shell": "cargo test --quiet" }, "on_failure": "halt" }
  ],
  "boundary":      { "max_cost_usd": 2.0, "max_steps": 30, "max_tokens": 150000 },
  "output_schema": null,

  "prompt":        "Refactor the auth module to use JWT.",
  "system_prompt": "You are a senior Rust developer.",
  "model":         "claude-sonnet-4-6",
  "skills":        [ { "name": "style-guide", "source": "./skills/style-guide" } ],

  "thread_id":     "session-xyz",
  "tags":          ["auth", "refactor"],
  "meta":          { "environment": "dev", "triggered_by": "ci" }
}
```

### Config fields by plane

| Plane | Field | Purpose |
|---|---|---|
| Environment | `tools` | RPC tools the agent can call. Routed through the `tool_exec_*` lifecycle. |
| Environment | `allowed_tools` | Optional allowlist. When present, the runner exposes ONLY these names to the model — both `Config.tools` entries and runner built-ins are filtered through it. When absent, the runner exposes its default set (built-ins + `Config.tools`). |
| Environment | `verifiers` | Deterministic checks the agent runs at declared triggers. Reactions (halt / inject correction / continue) are declared per-verifier. |
| Environment | `boundary` | Hard limits the agent enforces on itself (strict-greater; runs may overshoot cost/tokens by one final turn). |
| Environment | `output_schema` | Structured output contract; validated on `agent_stopped`. |
| Runner | `prompt` / `system_prompt` / `model` / `skills` | What the agent runs and how. |
| Metadata | `thread_id` / `tags` / `meta` | For correlation, filtering, ad-hoc context. |

`schema_version` MUST equal `"0.1"`. `run_id` MUST be unique per run.

---

## Verifiers — the supervisor's primary verb

A verifier is a **deterministic Boolean check**: a test suite, a file existence test, a schema validation, a DDD invariant evaluation. The Config declares verifiers; the agent runs them at declared triggers; the trajectory records `verifier_evaluated` events.

The supervisor declares the rule upfront in Config; the agent enforces it deterministically at runtime. No mid-run reach-in by the supervisor.

```json
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
```

### Triggers

| Trigger | Fires |
|---|---|
| `before_first_turn` | once, after `agent_started` |
| `before_each_turn` | before every `model_turn_started` |
| `after_each_turn` | after every `model_turn_ended` |
| `on_tool:<name>` | after `tool_returned` for the named tool |
| `at_end` | once, before `agent_stopped` |

### `on_failure` actions

| Value | Behavior on `passed: false` |
|---|---|
| `continue` | Just emit the event, proceed normally. Useful for monitoring without gating. |
| `halt` | Emit `agent_stopped` with `reason: "verifier_failed"`. The DDD-invariant pattern. |
| `inject_correction` | Insert `correction_message` as a user-role message before the next turn. The self-correcting agent pattern. |

The supervisor defines what should be true; the agent enforces it deterministically; the trajectory records every check. Three tracks for business users: what the agent did (tool events), what it cost (cost_recorded), and **whether all the rules held** (verifier_evaluated).

---

## Tools

The Config declares `tools[]` exposed to the model. From the agent's perspective every tool is just a tool — the agent does not know whether the implementation is in-process (a callable the runner has registered) or out-of-process (an environmental service called via the RPC lifecycle).

```
LLM calls a tool
  → runner: tool_invoked        { call_id, tool, input }                          [source=runner]
  → if tool's impl is local:
      runner: tool_returned     { call_id, output, [output_json] }                [source=runner]
  → if tool's impl is RPC-backed (a supervisor-stood-up service):
      runner: tool_exec_request   { request_id, call_id, input, timeout_ms }       [source=runner]
         │
         ├──► service: tool_exec_resolved { request_id, output, [output_json], [error] }   [source=supervisor]
         │     runner records verbatim; returns output to LLM (with "Error: " prefix iff error set)
         │
         └──► (timeout) runner: tool_exec_timed_out { request_id, call_id }       [source=runner]
                runner returns "" to LLM
      → runner: tool_returned      { call_id, output }                            [source=runner]
```

The supervisor is not making a runtime decision when its RPC service replies — it's a service answering a request. The agent initiated the call; the supervisor pre-deployed the implementation.

`call_id` identifies the LLM's tool invocation. `request_id` identifies the RPC. Different IDs because they're different concepts; both appear on the relevant events.

---

## Boundary semantics

Strict greater-than. The check fires AFTER each `model_turn_ended` (and after each `tool_returned` for cost/tokens). The step boundary projects the next would-be turn before starting it.

- `max_cost_usd: 2.00`: at `total_cost_usd = 1.99` the next turn proceeds. At exactly `2.00`, also proceeds (`2.00 > 2.00` is false). The run stops AFTER the first turn that brings `total_cost_usd` strictly above `2.00`.
- `max_steps: N`: the projection check is `(state.total_turns + 1) > N`. The run completes EXACTLY N turns.
- Cache reads count as input tokens (cache changes billing, not work).

The full reference algorithm is in [`spec/v0.1/SPEC.md` §9.2–§9.4](./spec/v0.1/SPEC.md#92-boundary-check-normative-algorithm). Two conforming runners with identical inputs MUST agree.

---

## The trajectory

The runner's stdout is the canonical trajectory. Every event has a `source` field.

- **`source: "runner"`** — the agent emitting facts.
- **`source: "supervisor"`** — `tool_exec_resolved` RPC replies the runner records verbatim. Documents who computed the value, not who decided anything.

### Three classes of trajectory facts

| Class | Event types | Semantics |
|---|---|---|
| **What the agent did** | `model_turn_*`, `tool_invoked`, `tool_returned`, `tool_failed`, `text_emitted` | Mechanical actions |
| **What the rules said** | `verifier_evaluated` | Deterministic Boolean checks |
| **What the run cost** | `cost_recorded`, `model_turn_ended.usage` | Resource accounting |

A non-technical reviewer can answer "did this run respect the contract?" by filtering on `verifier_evaluated.passed=false` — without having to read prose annotations or run an LLM judge.

Interpretive narrative ("the supervisor's reading of what happened") is a post-hoc concern handled by trajectory analyzers, not a runtime event class.

---

## Event reference

| Type | Source(s) | Semantics |
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
| `tool_exec_resolved` | supervisor | Service's reply. |
| `tool_exec_timed_out` | runner | No reply received in time. |
| `verifier_evaluated` | runner | Deterministic pass/fail check. |

Field-level definitions are in [`spec/v0.1/aep.schema.json`](./spec/v0.1/aep.schema.json). Conformance criteria are in [`spec/v0.1/SPEC.md` §13](./spec/v0.1/SPEC.md#13-conformance).

---

## Custom events

Any `type` value not listed above is a custom event. Custom events MUST include the `EventBase` fields (`type`, `source`, `run_id`, `ts`). Consumers MUST pass through unrecognized types without error.

Implementers SHOULD use dot-namespaced types (`myframework.verifier_result`). For non-spec FIELDS within a known event type, use the `extensions` envelope.

The names listed above are reserved.

---

## Workspace and deployment

The agent's workspace is conventionally the **runner's current working directory**. Shell verifier paths (e.g., `scripts/scan_secrets.sh`) and any tool inputs containing relative paths resolve there. The supervisor's deployment layer is responsible for ensuring referenced files exist in the workspace before the run starts.

How the workspace gets provisioned (git checkout, container volume mount, tmpdir, NFS share), how secrets reach the process, where RPC tool services run, and how the runner is sandboxed are all **outside AEP's scope** — see [`SPEC.md` §14](./spec/v0.1/SPEC.md#14-deployment-scope). Implementations choose. AEP just defines the wire.

For verifiers whose code shouldn't ship to the workspace, expose them as RPC tools and have the supervisor's service host the logic.

---

## Implementing AEP

The full conformance checklist for runners and supervisors is in [`spec/v0.1/SPEC.md` §13](./spec/v0.1/SPEC.md#13-conformance). The reference algorithm for the runner loop is in §9.

A runner is conforming if it:

1. Reads exactly one valid Config from its input channel before emitting events.
2. Emits `agent_started` first and `agent_stopped` last, both with `source: "runner"`.
3. Emits `model_turn_started` / `model_turn_ended` around every model call.
4. Emits `tool_invoked` / `tool_returned` (or `tool_failed`) around every tool call.
5. Emits `cost_recorded` at least once per turn with a `RunStateSnapshot`.
6. Records supervisor-authored RPC replies into the trajectory verbatim with `source: "supervisor"`.
7. Enforces `Config.boundary` per the normative strict-greater algorithm.
8. Implements the tool-exec lifecycle when `Config.tools` declares RPC-impl tools.
9. Runs declared verifiers at their triggers and applies `on_failure` (halt / inject_correction / continue).

A supervisor is conforming if every Config and SupervisorMessage (RPC reply) it sends validates against the corresponding entry-point schema, and every reply references a `request_id` the runner previously opened.

The conformance suite at [`conformance/v0.1/`](./conformance/v0.1/) ships executable test cases for every load-bearing requirement above. Every AEP-compliant SDK MUST pass every case.
