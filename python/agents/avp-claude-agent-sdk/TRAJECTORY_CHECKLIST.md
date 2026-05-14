# Trajectory implementation checklist — `avp-claude-agent-sdk`

Goal: swapping `from claude_agent_sdk import query` for
`from avp_claude_agent_sdk import query` (or calling `apply_patches()`)
produces a fully AVP-conforming trajectory. The wrapper yields the same
`Message` objects as the upstream `query()`.

Cross-references:
- Spec: [`spec/v0.1/trajectory.md`](../../../spec/v0.1/trajectory.md)
- AVP event types: [`python/avp/src/avp/trajectory.py`](../../avp/src/avp/trajectory.py)
- Pricing: [`python/avp/src/avp/pricing.py`](../../avp/src/avp/pricing.py)
- Upstream message shapes: `claude_agent_sdk.types`

## Plumbing

- [x] `sink: EventSink | None = None` kwarg on `query()`; defaults to
  `avp.agent.stdio_sink`.
- [x] Per-call `RunState` (context-var scoped) holds `trace_id`,
  `run_id`, `agent_span_id`, `current_turn_span_id`, `tool_spans`.
  Context-var isolation means concurrent `query()` calls don't
  cross-fire.
- [x] `apply_patches()` / `restore_patches()` in `_patches.py`:
  idempotent monkeypatch of `claude_agent_sdk.query`; creates `RunState`
  on the fly when none is set by `run_avp_agent`.

## Run prelude (spec §2.1) — emit before consuming any SDK message

- [x] `avp.run_requested` — no Commission on the `query()` path; omit
  `avp.commission` and `avp.supervisor.*` entirely. Span triple with
  `parent_span_id = ZERO`.
- [x] `avp.agent_described` — `AgentDescriptor` with
  `name="avp-claude-agent-sdk"`, `version` from package metadata,
  `avp_spec_version="0.1"`. `parent_span_id = ZERO`.
- [x] `avp.agent_started` — opens the agent span. `agent_span_id`
  stored on `RunState` for parenting subsequent events. Populated:
  `gen_ai.provider.name`, `gen_ai.request.model`, `prompt`,
  `system_prompt`, `tools[]`, `mcp_servers[]`, `skills[]`, `subagents[]`.

## Per-turn loop (spec §3.1–3.3)

- [x] `avp.model_turn_started(step=N)` on each `AssistantMessage`.
  `parent_span_id = agent_span_id`. `step` is 1-indexed.
  `current_turn_span_id` stored on `RunState`.
- [ ] Cumulative usage tracking. Add `prev_cum` to `RunState`:
  `{input, output, cache_read, cache_creation, cost_usd}`. After each
  `AssistantMessage.usage`, compute per-turn deltas. Silent rebase when
  `cum < prev` (compaction / sub-agent dispatch resets — spec §3.3).
- [ ] `avp.model_turn_ended` at end of each `AssistantMessage`. Required
  fields (spec §8 #5):
  - `gen_ai.usage.input_tokens` = delta input (incl. cache reads)
  - `gen_ai.usage.output_tokens` = delta output
  - `gen_ai.usage.cache_read.input_tokens`,
    `gen_ai.usage.cache_creation.input_tokens` = deltas (optional but
    strongly recommended)
  - `gen_ai.response.model` = `AssistantMessage.model`
  - `gen_ai.response.finish_reasons = [AssistantMessage.stop_reason]`
    when present
  - `avp.cost_usd` = per-turn delta from `avp.pricing.compute_cost()`
  - `avp.cost.source` = `"computed"` if model in price table, else
    `"unknown"`
  - `duration_ms` = wall time from turn start

### Pricing

- [ ] `from avp.pricing import compute_cost, load_default_prices`
- [ ] Load price table once at top of the `query()` call; store on
  `RunState` (or pass through to the emitter). `compute_cost()` takes
  `ModelPrice` + token counts → `float`.

## Content-block translation (per `AssistantMessage.content[]`)

- [ ] `TextBlock` → `avp.text_emitted(step=N, avp.text=block.text)`.
  `parent_span_id = current_turn_span_id`.
- [ ] `ThinkingBlock` → `avp.reasoning_emitted(step=N,
  avp.reasoning.text=block.thinking,
  avp.reasoning.signature=block.signature)`.
- [ ] `ToolUseBlock` → `avp.tool_invoked` with
  `gen_ai.tool.call.id=block.id`, `gen_ai.tool.name=block.name`,
  `gen_ai.tool.call.arguments=block.input`. Save `block.id → span_id`
  in `RunState.tool_spans` to pair with the result.
  `avp.tool.dispatch_target="local"` (built-in) or `"mcp_server"`.
- [ ] `ToolResultBlock` (in subsequent `UserMessage.content`) →
  `avp.tool_returned` or `avp.tool_failed` (if `is_error=True`). Look
  up `block.tool_use_id` in `RunState.tool_spans` to set
  `parent_span_id`.
- [ ] `ServerToolUseBlock` / `ServerToolResultBlock` → same mapping as
  above; tag `avp.tool.dispatch_target="local"` (API-executed, not MCP).

## SystemMessage subtypes

- [ ] `TaskStartedMessage` / `TaskNotificationMessage` — map to
  `avp.subagent_invoked` / `avp.subagent_returned` keyed on `task_id`.
  Populate `avp.subagent.usage` from `TaskUsage` (in-process fallback
  per spec §5 #6 — SDK black-boxes the child loop).
  `avp.subagent.run_id` stays `None`.
- [ ] `TaskProgressMessage` — drop (informational).
- [ ] Unknown subtypes → drop (honest-silent beats fabricated events).

## Terminal events (spec §8 #3, #6)

- [ ] `ResultMessage` → emit `avp.agent_stopped`:
  - `avp.reason = "converged"` (normal) / `"error"` (is_error=True) /
    `"refused"` (refusal)
  - `avp.output` = `ResultMessage.result` when present
- [ ] Wrapper exceptions (`CLIConnectionError`, `ProcessError`, etc.) →
  emit `avp.error_occurred(code="agent_crash", message=str(e))` then
  `avp.agent_stopped(reason="error")` before re-raising.
- [ ] `CancelledError` → `avp.agent_stopped(reason="cancelled")`.
  Suppress the error (the SDK sometimes raises it as an internal
  cleanup signal — see reference implementation comment).
- [ ] Guarantee: `agent_stopped` is ALWAYS the last event; use
  try/finally around the stream.

## Conformance floor (spec §8)

- [x] Trajectory opens with `run_requested → agent_described →
  agent_started`.
- [x] CloudEvents envelope on every event; `source = "avp://agent"`.
- [x] Span triple on every event; prelude events at ZERO; turn events
  parented under `agent_span_id`.
- [ ] Every model inference brackets with `model_turn_started` /
  `model_turn_ended` (started done; ended missing).
- [ ] Every tool call brackets with `tool_invoked` and one of
  `tool_returned` / `tool_failed`.
- [ ] `model_turn_ended` carries `avp.cost_usd` and
  `gen_ai.usage.*_tokens` (per-turn deltas, non-negative).
- [ ] Last event is `agent_stopped`; nothing after.
- [ ] All emitted events validate against `trajectory.schema.json`.

## Decisions (resolved)

1. **Sink** — `sink: EventSink | None = None` kwarg on `query()`;
   `stdio_sink` default; stored on `RunState` for stateless emitters.
2. **State** — `RunState` dataclass on a `ContextVar`; no module
   globals; concurrent calls isolated per asyncio task.
3. **Per-turn cost** — `compute_cost()` from `avp.pricing`; stamp
   `avp.cost.source = "computed"` / `"unknown"`. No separate
   `cost_recorded` event — `model_turn_ended` carries `avp.cost_usd`
   per spec §8 #5; consumers reduce the stream.
4. **No Commission on `run_requested`** — `query()` is the
   library-invocation path; omit `avp.commission` and
   `avp.supervisor.*`. A separate Commission-aware entry point
   (`run_avp_agent`) handles the supervised path.
5. **Task tool** — modeled as `avp.subagent_invoked` /
   `subagent_returned` with `avp.subagent.usage` (in-process fallback
   per spec §5 #6); `avp.subagent.run_id = None`.
6. **`agent_stopped` payload** — only `avp.reason` and optional
   `avp.output`; no cumulative state snapshot on the wire (spec §7.1).
