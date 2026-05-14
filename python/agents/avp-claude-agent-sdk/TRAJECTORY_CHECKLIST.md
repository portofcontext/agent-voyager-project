# Trajectory implementation checklist — `avp-claude-agent-sdk`

Goal: calling `setup_avp()` instruments `claude_agent_sdk.query` in place.
All subsequent calls to `claude_agent_sdk.query` emit a conforming AVP
trajectory. The wrapper yields the same `Message` objects as the upstream.

Cross-references:
- Spec: [`spec/v0.1/trajectory.md`](../../../spec/v0.1/trajectory.md)
- AVP event types: [`python/avp/src/avp/trajectory.py`](../../avp/src/avp/trajectory.py)
- Pricing: [`python/avp/src/avp/pricing.py`](../../avp/src/avp/pricing.py)
- Upstream message shapes: `claude_agent_sdk.types`

## Plumbing

- [x] `setup_avp(sink=stdio_sink)` patches `claude_agent_sdk.query`
  idempotently and stores the sink. Also scans `sys.modules` to update
  modules that did `from claude_agent_sdk import query` before setup.
- [x] `_ensure_patched()` applies patches without touching the sink;
  used by `run_avp_agent` so it doesn't stomp a user-configured sink.
- [x] Per-call `RunState` (context-var scoped) holds `trace_id`,
  `run_id`, `agent_span_id`, `current_turn_span_id`, `step`,
  `tool_result_arrived`, `tool_spans`. Context-var isolation means
  concurrent calls don't cross-fire.
- [x] `_wrap_query` creates `RunState` on the fly (with configured sink)
  when none is set; defers to an existing one when `run_avp_agent` set it.
- [x] `handle_message(state, message)` in `_emit.py` is the single
  dispatch entry point, reusable for `ClaudeSDKClient` patch (Stage 3).
  Uses class-name dispatch (`type().__name__`) not `isinstance`.

## Run prelude (spec §2.1) — emit before consuming any SDK message

- [x] `avp.run_requested` — no Commission on the `setup_avp` path; omit
  `avp.commission` and `avp.supervisor.*`. Span triple at `ZERO`.
- [x] `avp.agent_described` — `AgentDescriptor` with
  `name="avp-claude-agent-sdk"`, `version` from package metadata,
  `avp_spec_version="0.1"`. `parent_span_id = ZERO`.
- [x] `avp.agent_started` — opens the agent span; `agent_span_id` stored
  on `RunState`. Populated: `gen_ai.provider.name`, `gen_ai.request.model`,
  `prompt`, `system_prompt`, `tools[]`, `mcp_servers[]`, `skills[]`,
  `subagents[]`.

## Per-turn loop (spec §3.1–3.3)

- [x] `avp.model_turn_started(step=N)` on each `AssistantMessage` that
  opens a new turn. `parent_span_id = agent_span_id`. `step` owned by
  `RunState`. 1-indexed.
- [x] **Merge gate** — consecutive `AssistantMessage`s without an
  intervening `UserMessage(ToolResultBlock)` are the same LLM call
  (e.g. thinking block + text block). Only the first opens a turn;
  subsequent ones are merged silently. Mirrors Braintrust's
  `next_llm_start` check. `tool_result_arrived` on `RunState` is the flag.
- [ ] Cumulative usage tracking. Add `prev_cum` to `RunState`:
  `{input, output, cache_read, cache_creation, cost_usd}`. After each
  `AssistantMessage.usage`, compute per-turn deltas. Silent rebase when
  `cum < prev` (compaction / sub-agent dispatch resets — spec §3.3).
  Gate `model_turn_started` on `delta_output > 0` (spec §3.1 MUST).
- [ ] `avp.model_turn_ended` at end of each turn. Required (spec §8 #5):
  - `gen_ai.usage.input_tokens` = delta input (incl. cache reads)
  - `gen_ai.usage.output_tokens` = delta output
  - `gen_ai.usage.cache_read.input_tokens`,
    `gen_ai.usage.cache_creation.input_tokens` = deltas
  - `gen_ai.response.model` = `AssistantMessage.model`
  - `gen_ai.response.finish_reasons = [AssistantMessage.stop_reason]`
  - `avp.cost_usd` = per-turn delta from `avp.pricing.compute_cost()`
  - `avp.cost.source` = `"computed"` / `"unknown"`
  - `duration_ms` = wall time from turn start

### Pricing

- [ ] `from avp.pricing import compute_cost, load_default_prices`
- [ ] Load price table once per run; store reference on `RunState`.

## Content-block translation (per `AssistantMessage.content[]`)

- [ ] `TextBlock` → `avp.text_emitted(step=N, avp.text=block.text)`.
  `parent_span_id = current_turn_span_id`.
- [ ] `ThinkingBlock` → `avp.reasoning_emitted(step=N,
  avp.reasoning.text=block.thinking,
  avp.reasoning.signature=block.signature)`.
- [ ] `ToolUseBlock` → `avp.tool_invoked`. Save `block.id → span_id`
  in `RunState.tool_spans` to pair with the result.
- [ ] `ToolResultBlock` (in `UserMessage.content`) → `avp.tool_returned`
  or `avp.tool_failed` (`is_error=True`). Look up `tool_use_id` in
  `RunState.tool_spans` for `parent_span_id`.
- [ ] `ServerToolUseBlock` / `ServerToolResultBlock` → same mapping;
  tag `avp.tool.dispatch_target="local"`.

## SystemMessage subtypes

- [ ] `TaskStartedMessage` / `TaskNotificationMessage` → `avp.subagent_invoked`
  / `avp.subagent_returned`. Populate `avp.subagent.usage` from `TaskUsage`.
  Use `_msg_field(message, field)` helper (see Braintrust reference) for
  SDK version compatibility (`>=0.1.11` top-level attrs vs `0.1.10` data dict).
- [ ] `TaskProgressMessage` — drop.
- [ ] Unknown subtypes — drop (honest-silent beats fabricated events).

## Terminal events (spec §8 #3, #6)

- [x] `ResultMessage` → `avp.agent_stopped`:
  - `avp.reason = "converged"` (normal) / `"error"` (`is_error=True`)
  - `avp.output` = `ResultMessage.result` when present
- [ ] `ResultMessage.stop_reason == "refusal"` → `avp.reason = "refused"`.
- [ ] Wrapper exceptions (`CLIConnectionError`, `ProcessError`, etc.) →
  `avp.error_occurred(code="agent_crash")` then `avp.agent_stopped("error")`
  before re-raising.
- [ ] `CancelledError` → `avp.agent_stopped("interrupted")`. Suppress
  (SDK sometimes raises it as internal subprocess cleanup, not a genuine
  cancellation — lift comment from Braintrust's `_stream_messages_with_tracing`).
- [ ] Guarantee `agent_stopped` is last: try/except/finally around the
  stream; `finally` emits if not already emitted. Track with
  `state.stopped: bool` flag.

## Conformance floor (spec §8)

- [x] Trajectory opens with `run_requested → agent_described → agent_started`.
- [x] CloudEvents envelope on every event; `source = "avp://agent"`.
- [x] Span triple on every event; prelude at ZERO; turns under `agent_span_id`.
- [x] `ResultMessage` → `agent_stopped` with correct reason.
- [ ] Every model inference brackets with `model_turn_started` /
  `model_turn_ended` (`started` ✅; `ended` ❌).
- [ ] Every tool call brackets with `tool_invoked` / `tool_returned` or
  `tool_failed`.
- [ ] `model_turn_ended` carries `avp.cost_usd` and `gen_ai.usage.*_tokens`.
- [ ] Last event is always `agent_stopped`; exceptions handled.
- [ ] All emitted events validate against `trajectory.schema.json`.

## Decisions (resolved)

1. **Sink** — `setup_avp(sink=stdio_sink)` stores sink in `_patches._configured_sink`;
   `run_avp_agent` sets a `RunState` with its own sink before calling into
   the patched query, so it takes precedence without overwriting the global.
2. **State** — `RunState` dataclass on a `ContextVar`; no module globals;
   concurrent calls isolated per asyncio task.
3. **Merge gate** — `tool_result_arrived` flag on `RunState`; mirrors
   Braintrust's `next_llm_start`. Consecutive `AssistantMessage`s without
   a `UserMessage(ToolResultBlock)` = same LLM call, not a new turn.
4. **Per-turn cost** — `compute_cost()` from `avp.pricing`; stamp
   `avp.cost.source = "computed"` / `"unknown"`. `model_turn_ended` carries
   `avp.cost_usd`; consumers reduce the stream (spec §7.1).
5. **No Commission on `run_requested`** — `setup_avp` / `query` path omits
   `avp.commission` and `avp.supervisor.*`. `run_avp_agent` handles the
   Commission path.
6. **Task tool** → `subagent_invoked` / `subagent_returned` with
   `avp.subagent.usage` (in-process fallback, spec §5 #6).
7. **`agent_stopped` payload** — only `avp.reason` + optional `avp.output`;
   no cumulative totals (spec §7.1).
8. **Class-name dispatch** — `type(message).__name__` not `isinstance`;
   decoupled from SDK imports and resilient to class hierarchy changes.
