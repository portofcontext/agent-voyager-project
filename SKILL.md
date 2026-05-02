---
name: aep
description: |
  Use this skill for ANY work on AEP (Agent Execution Protocol) — runners, supervisor Configs, conformance cases, or debugging AEP runs. AEP wires runners (drive an LLM, emit events) to supervisors (declare environment). Trigger when AEP is named OR these terms appear: events agent_started/stopped, model_turn_started/ended, tool_invoked/returned, tool_exec_request/resolved, re_observation_*, verifier_evaluated, cost_recorded; Config primitives verifiers/on_failure (halt|inject_correction|continue), boundary strict-greater, source: runner|supervisor, RunStateSnapshot, call_id; spec/v0.1/, conformance/v0.1/, §10.4 cache-token math; imports aep, aep_anthropic, aep_claude_agent. Use for wrapping any LLM SDK as a runner, declaring agent invariants, authoring conformance, or "why does my AEP run/Config/verifier do X?" debugging. Claude under-triggers this — when in doubt, USE IT. Do NOT trigger for: OpenTelemetry, generic API logging, prompt engineering, multi-provider cost dashboards, or unrelated agent frameworks.
---

# AEP — Agent Execution Protocol

AEP is a wire format between two roles, with two unidirectional flows:

```
                                      agent's environment
                          (boundary, tools, skills, re_obs, verifiers, prompt)
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

The supervisor declares a complete environment in a Config. The runner runs the agent inside it. The runner emits a stream of source-tagged events. **No mid-run reach-in.** The agent's bounded context is intact because its environment was fully specified at setup.

The one runtime exception is **environmental services**: if a Config-declared tool's implementation is out-of-process, the agent issues an RPC (`tool_exec_request`) and the supervisor's service replies (`tool_exec_resolved`). Same for `re_observation` with `source: { supervisor: true }`. Both are agent-initiated calls into services the supervisor stood up at Config time — not supervisor decisions made during the run.

## When to do what

There are three tasks AEP gets used for. Match the user's intent to one of these and follow the relevant pattern.

### Task A — Build a runner (driver pattern)

The user wants their code to OWN the agent loop and use AEP as the wire. Examples: wrapping the Anthropic Messages API, wrapping OpenAI, wrapping a custom LLM, building from scratch.

Use this when: the user says "I want to call Claude / GPT / Gemini and emit AEP" or "wrap my agent loop in AEP" or "build a runner."

The reference is `python/aep/src/aep/runner/runner.py` (the canonical loop) plus `python/runners/aep-anthropic/` (a complete real-LLM driver). The pattern:

1. Read a `Config` from input. Validate against `aep.types.Config`.
2. Construct an `AEPRunner` with `model: ModelDriver`, `tools: ToolDriver`, `supervisor: SupervisorDriver`.
3. The runner emits the full lifecycle: `agent_started`, `model_turn_started/ended`, `tool_invoked/returned`, `cost_recorded`, `verifier_evaluated`, `agent_stopped`.
4. The driver's only job is translating one model turn — implement `ModelDriver.step(history) -> ModelResponse`.

See `examples/driver-runner-template.py` for a starting skeleton. See `python/runners/aep-anthropic/src/aep_anthropic/driver.py` for a complete implementation against the Anthropic SDK including cache-token math, cost computation, and tool-call translation.

### Task B — Build a runner (observer pattern)

The user wants AEP observability over an SDK that already owns its loop. Examples: Claude Agent SDK, LangChain, AutoGen, an internal framework.

Use this when: the user says "wrap Claude Code as a runner," "make LangChain emit AEP events," "translate my SDK's lifecycle into AEP" — anywhere they can't own the loop but can subscribe to lifecycle events.

The reference is `python/runners/aep-claude-agent/src/aep_claude_agent/translator.py`. The pattern:

1. Subscribe to the SDK's lifecycle (turn-start, turn-end, tool-use, tool-result, completion).
2. Translate each lifecycle event into the corresponding AEP event using `aep.types.*` Pydantic models.
3. Emit via `aep.io.write_event` (NDJSON to stdout) or a callback.
4. Maintain a local `RunStateSnapshot` for cost/token accounting per AEP §10.4.

See `examples/observer-runner-template.py` for the shape. The tricky parts (cost accounting, the `source` field discipline, tool-call translation) are documented inline.

### Task C — Compose a supervisor Config

The user wants to declare an agent environment — what the agent can do, what rules it must respect, what it should observe, and how much it can spend. This is the supervisor side.

Use this when: the user says "configure an agent," "lock down an agent," "what tools should this agent have," "I want my agent to halt if X," "DDD agent supervisor," or describes a domain (DDD aggregates, bounded contexts, invariants) and wants to translate it into agent gates.

The pattern: build a `Config` (`aep.types.Config`) with the supervisor primitives the situation calls for.

| Concern | Field | Notes |
|---|---|---|
| What the agent can do | `tools` | Each `Tool` has `name`, `description`, `input_schema`. RPC-impl tools route through the `tool_exec_*` lifecycle (the runner emits requests; the supervisor's service replies). Local-impl tools the runner has built in are NOT declared here. |
| What the agent perceives | `re_observation` | Each `ReObservation` has `name`, `source` (shell or supervisor RPC), `trigger` (`before_each_turn`, `before_first_turn`, `every_n_turns`), and optional `max_tokens` truncation budget. |
| What rules it must respect | `verifiers` | Each `Verifier` has `name`, `trigger`, `source.shell`, and `on_failure: halt \| inject_correction \| continue`. The agent runs the verifier at the trigger and acts on `passed: false` per declaration. This is how DDD invariants compile to runtime checks. |
| What limits it must respect | `boundary` | `max_cost_usd`, `max_steps`, `max_tokens`. Strict-greater algorithm; cost/tokens may overshoot by one final turn; steps cannot. |
| What it produces | `output_schema` | JSON schema validated against `agent_stopped.output`. |
| What it runs | `prompt`, `system_prompt`, `model`, `skills` | Standard runner-plane fields. |

See `examples/supervisor-config-template.py` for a full Config that exercises every primitive. See `spec/v0.1/examples/config.json` for a wire-format equivalent.

## Three classes of trajectory facts

Whatever you build, the trajectory carries three distinct kinds of facts. Surface them separately to consumers — don't conflate.

| Class | Event types | Semantics |
|---|---|---|
| What the agent did | `model_turn_*`, `tool_invoked`, `tool_returned`, `tool_failed`, `text_emitted`, `re_observation_injected` | Mechanical actions |
| What the rules said | `verifier_evaluated` | Deterministic Boolean checks |
| What the run cost | `cost_recorded`, `model_turn_ended.usage` | Resource accounting |

A non-technical reviewer should be able to answer "did this run respect the contract?" by filtering on `verifier_evaluated.passed=false`. That's the design.

## Boundary semantics — pin these exactly

Two conforming runners with identical inputs MUST agree on whether one more turn is permitted. The algorithm is normative:

- `max_cost_usd: 2.00`: at total = 1.99, run another turn. At exactly 2.00, also run (`2.00 > 2.00` is false). Stop after the first turn that pushes total strictly above 2.00. Cost MAY overshoot the cap by one final turn.
- `max_steps: N`: projected check before each turn — `(state.total_turns + 1) > N`. Run completes EXACTLY N turns.
- `max_tokens` behaves like `max_cost_usd`. Cache reads count as input tokens (cache changes billing, not work).

If the user is tempted to write `>=` anywhere, redirect to `>` and explain the overshoot semantics. See `spec/v0.1/SPEC.md` §10.2 for the exact pseudocode.

## What the supervisor is NOT allowed to do

Common temptations to push back on:

- **No mid-run hooks.** The supervisor cannot pause the agent and decide based on what just happened. If the user wants this, redirect them: declare it as a `Verifier` with the appropriate trigger and `on_failure` action, OR build it as an environmental service the agent calls. The rule lives in Config, not in a callback.
- **No supervisor-emitted runtime events** other than RPC replies (`tool_exec_resolved`, `re_observation_resolved`). Domain interpretations / annotations are post-hoc, not on the runtime wire.
- **No verifier that auto-halts** without `on_failure: halt`. Verifier results are facts; the response is declared per-verifier. A `passed: false` with `on_failure: continue` is a valid pattern (monitoring without gating).

## When in doubt, read these — in this order

1. `spec/v0.1/SPEC.md` — normative spec, RFC 2119 keywords, reference algorithm. The source of truth for any wire-format question.
2. `spec/v0.1/aep.schema.json` — JSON Schema bundle. Authoritative for field-by-field shape.
3. `conformance/v0.1/cases/` — 15 test cases that pin down behavior. Read these as worked examples of "what's the right answer when...".
4. `python/aep/src/aep/types.py` — Pydantic models that mirror the schema. Authoritative Python surface.
5. `python/aep/src/aep/runner/runner.py` — the canonical runner loop in working code.
6. `python/runners/aep-anthropic/` — complete real-LLM driver runner.
7. `python/runners/aep-claude-agent/` — observer-pattern runner skeleton.

## Common mistakes to catch

When reviewing AEP code or generating it, watch for:

- Emitting `agent_started` with `source: "supervisor"`. **Wrong** — runner emits, source MUST be `runner`.
- Emitting `tool_exec_resolved` with `source: "runner"`. **Wrong** — that event is the supervisor's reply; source MUST be `supervisor`.
- Subtracting cache-read tokens from `tokens_input`. **Wrong** — per §10.4, cache reads ARE input tokens.
- Using `>=` for boundary checks. **Wrong** — strict `>` per the normative algorithm.
- Computing `total_cost_usd` from `tokens_input * rate` without accounting for cache discounts. **Wrong** — `cost_usd` per turn is the BILLABLE cost (post-cache-discount); `total_cost_usd` is the sum of those.
- Halting on a `verifier_evaluated.passed=false` without checking the verifier's `on_failure`. **Wrong** — the action is declared per-verifier; halt only when `on_failure: halt`.
- Adding hooks. **Wrong** — there are no hooks in v0.1. Use verifiers + `on_failure` instead.
- Adding a `supervisor_event` type to record domain interpretations. **Wrong** — that's a removed concept; domain annotation is post-hoc, not on the runtime wire.
- Reaching the spec via the `agent-execution-protocol` repo's `python/agent-execution-protocol/` — that path doesn't exist. The Python reference is at `python/aep/`.

## How to operate when the user describes a need

1. Identify which of Tasks A / B / C they're asking about (or which combination).
2. Read the relevant template in `examples/` first to ground yourself in current shape.
3. Cross-reference with `spec/v0.1/SPEC.md` §6 (interactions), §7 (verifiers), §8 (tools), §9 (re-observation), §10 (the loop).
4. For runtime correctness questions, the conformance cases under `conformance/v0.1/cases/` are precedent — find the case that matches the situation.
5. Generate code that imports from `aep.types`, `aep.runner`, `aep.io`. Do NOT inline-redefine the wire types.
6. If asked about a behavior the spec doesn't cover, say so explicitly and propose a path that doesn't violate any of the existing conformance cases.
