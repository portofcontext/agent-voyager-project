# Trajectory implementation checklist — `avp-claude-agent-sdk`

Goal: `AVPClaudeSDKClient` (subclass of `ClaudeSDKClient`) is the primary
surface. `connect()` emits the prelude (with the real tool list from
`get_mcp_status()`), `receive_response()` tees the message stream
through AVP emission, `disconnect()` emits `agent_stopped`. The wrapper
yields the same `Message` objects as the upstream. `query()` is not
overridden -- in `ClaudeSDKClient` it is fire-and-forget (returns
`None`, sends the prompt); the iterator lives on `receive_response()`.
`setup_avp()` (Stage 3) swaps `claude_agent_sdk.ClaudeSDKClient` for
`AVPClaudeSDKClient` so callers get instrumentation by import-time
monkeypatch; the `query()` free function is out of scope (no pre-run
lifecycle, no conformant `agent_started`).

Cross-references:
- Spec: [`spec/v0.1/trajectory.md`](../../../spec/v0.1/trajectory.md)
- AVP event types: [`python/avp/src/avp/trajectory.py`](../../avp/src/avp/trajectory.py)
- AVP content blocks: [`python/avp/src/avp/content.py`](../../avp/src/avp/content.py)
- Pricing: [`python/avp/src/avp/pricing.py`](../../avp/src/avp/pricing.py)
- Upstream message shapes: `claude_agent_sdk.types`

## Plumbing

- [x] `AVPClaudeSDKClient(ClaudeSDKClient)` in `_client.py`. Overrides
  `connect()`, `receive_response()`, `disconnect()`. Constructor accepts
  an optional `sink: EventSink = stdio_sink` and stashes it on the
  instance. `query()` is NOT overridden -- upstream it is fire-and-forget
  (returns `None`, sends the prompt); the iterator lives on
  `receive_response()`, which is where AVP teeing happens.
- [x] `connect(prompt=None)`: `super().connect(prompt)`, then
  `await self.get_mcp_status()` for the real tool list, then create a
  `RunState`, set the ContextVar, and `await emit_prelude(state, prompt, options, status)`.
- [x] `receive_response()`: read the ContextVar; for each upstream
  message call `handle_message(state, msg)` then yield it. Wrap in
  try/except so `CancelledError` → `agent_stopped("interrupted")` and
  other exceptions → `error_occurred` + `agent_stopped("error")`. Set
  `state.stopped = True` before emitting so `disconnect()` doesn't
  double-fire.
- [x] `disconnect()`: if `state and not state.stopped`,
  `emit_agent_stopped(state, "converged")`, reset the ContextVar token,
  then `super().disconnect()`.
- [x] Per-call `RunState` (ContextVar scoped) holds `trace_id`, `run_id`,
  `agent_span_id`, `current_turn_span_id`, `step`, `tool_result_arrived`,
  `tool_spans`, `prev_cum`, `stopped`, plus a per-turn content/usage
  accumulator (`turn_started_at`, `turn_content`, `turn_usage_delta`,
  `turn_response_model`, `turn_stop_reason`) populated by merged
  `AssistantMessage`s and drained on turn close. Also holds `prices` for
  per-turn cost computation.
- [x] `handle_message(state, message)` in `_emit.py` is the single
  dispatch entry point. Class-name dispatch (`type().__name__`), not
  `isinstance`, to stay decoupled from SDK imports.
- [ ] Stage 3 `setup_avp(sink=stdio_sink)` patches
  `claude_agent_sdk.ClaudeSDKClient` (and `sys.modules` references to it)
  with `AVPClaudeSDKClient`. Idempotent via `_AVP_WRAPPED` marker on the
  class.

## Run prelude (spec §2.1) — emit in `connect()` before `receive_response()` opens

- [x] `avp.run_requested` — no Commission on the `AVPClaudeSDKClient`
  path; omit `avp.commission` and `avp.supervisor.*`. Span triple at
  `ZERO`. (Commission path lives on Stage 3 `run_avp_agent`.)
- [x] `avp.agent_described` — `AgentDescriptor` with
  `agent_name="avp-claude-agent-sdk"`, `agent_version` from package
  metadata, `spec_version="0.1"`. Tools come from
  `McpStatusResponse["mcpServers"][*]["tools"]` (per-tool: `name`,
  optional `description`; no input schema is reported by the SDK, so
  `ToolDecl.parameters` is `None`). `mcp_servers[]` carries the SDK's
  display name verbatim as `id` (`McpServerDecl.id` is intentionally
  loose -- no slug pattern -- so environment-resident server names like
  `"claude.ai Dashboard Builder"` pass through without lossy slugging
  and stay correlatable with future `mcp_server_connected` events).
  `default_model`, `system_prompt`, `skills`, `subagents` come from
  `ClaudeAgentOptions`. `parent_span_id = ZERO`.
- [x] `avp.agent_started` — opens the agent span; `agent_span_id` stored
  on `RunState`. New field names: `provider_name="anthropic"`,
  `operation_name="invoke_agent"`, `request_model=descriptor.default_model`,
  `prompt`, `system_prompt`, `tools[]`, `mcp_servers[]`, `skills[]`,
  `subagents[]`. (Old `gen_ai_*` kwargs removed from the model; the
  redundant `avp.schema_version` field also removed -- spec version is
  carried once on `agent_described.descriptor.spec_version`.)

## Per-turn loop (spec §3.1–3.3) — single `avp.assistant_message` event

v0.1 merged `model_turn_started` + `model_turn_ended` into a single
`avp.assistant_message`. Per-turn deltas + content blocks ride on it.

- [x] **Turn open** — first `AssistantMessage` after a
  `UserMessage(ToolResultBlock)` (or run start) opens a new turn:
  bumps `state.step`, allocates `current_turn_span_id`, records
  `turn_started_at`, resets `turn_content` / `turn_usage_delta`.
- [x] **Merge gate** — consecutive `AssistantMessage`s without an
  intervening `UserMessage(ToolResultBlock)` are the same LLM call
  (e.g. thinking block + text block). They APPEND to `turn_content` /
  `turn_usage_delta` for the open turn; no new turn opens.
  `tool_result_arrived` on `RunState` is the boundary flag. Mirrors
  Braintrust's `next_llm_start`.
- [x] **Turn close** — emit `avp.assistant_message` when the turn is
  about to be sealed: either a `UserMessage(ToolResultBlock)` arrives,
  or a `ResultMessage` arrives. Payload (required by `AssistantMessageData`):
  - `avp.step` = `state.step`
  - `avp.duration_ms` = wall time from `turn_started_at`
  - `avp.content` = list of translated content blocks (see below)
  - `avp.usage` = per-turn delta (input incl. cache reads, output,
    cache_read_input_tokens, cache_creation_input_tokens)
  - `avp.cost_usd` = per-turn delta from `avp.pricing.compute_cost()`
  - `avp.cost.source` = `"computed"` / `"unknown"`
  - `avp.provider.name` = `"anthropic"`
  - `avp.request.model` / `avp.response.model` = `AssistantMessage.model`
  - `avp.response.finish_reasons` = `[ResultMessage.stop_reason]` when
    available on the closing boundary (else null)
- [x] **Cumulative usage tracking** — `prev_cum` on `RunState`:
  `{input, output, cache_read, cache_creation}`. After each
  `AssistantMessage.usage`, compute the delta against `prev_cum`, update
  `prev_cum`. Silent rebase when `cum < prev` (compaction / subagent
  dispatch resets, per spec §3.3): adopt new cumulative as fresh baseline.
- [x] **Empty-output gate** — skip emitting `assistant_message` when
  `delta_output == 0` for the closed turn (spec §3.1 MUST: every model
  inference brackets only when real output happened).

### Pricing

- [x] `from avp.pricing import compute_cost, load_default_prices`
- [x] Price table loaded once per run in `connect()`; stored on `RunState.prices`.

## Content-block translation (per `AssistantMessage.content[]` accumulated across merged messages)

All of these land inside `avp.assistant_message.avp.content` (NOT
separate `text_emitted` / `reasoning_emitted` events — those don't
exist in v0.1).

- [x] `TextBlock` → `avp.content.TextBlock(text=block.text)`.
- [x] `ThinkingBlock` → `avp.content.ThinkingBlock(thinking=block.thinking,
  signature=block.signature)`.
- [x] `ToolUseBlock` → `avp.content.ToolUseBlock(id=block.id,
  name=block.name, input=block.input)` lands in `avp.content` (done in
  Stage 1). Stage 2 ALSO emits a separate `avp.tool_invoked` event for
  the bracketing pair, parented to the just-emitted `assistant_message`
  span; records `block.id → ToolCallInfo(span_id, name, step, started_at)`
  in `state.tool_spans` to pair with the result. `dispatch_target` is
  `"mcp_server"` when the tool name has the `mcp__` prefix, else
  `"local"`.
- [x] `ServerToolUseBlock` / `ServerToolResultBlock` — map into the
  corresponding AVP content block; tool dispatch target is `"local"`
  (the agent never dispatches; the provider executes server-side).
  Both events bracket within the same turn (the SDK delivers the use
  + result in the same `AssistantMessage.content`); `_close_turn` walks
  the content list in order, allocating a `tool_invoked` span for
  `ServerToolUseBlock` and pairing `ServerToolResultBlock` against it.
  The SDK's `ServerToolResultBlock` does not carry `name`; the
  translator back-fills it from the matching `ServerToolUseBlock` in
  the same turn.

`ToolResultBlock` does NOT appear in `AssistantMessage.content`; it
appears in `UserMessage.content` and is handled separately (below) as a
`tool_returned` event — NOT as content on the assistant_message.

## Tool result events

- [x] `UserMessage(ToolResultBlock)` → `avp.tool_returned`. Look up
  `tool_use_id` in `state.tool_spans` (pop on emission) for
  `parent_span_id`, `tool_name`, `step`, and `duration_ms`. Payload
  carries `avp.tool_result` (an `avp.content.ToolResultBlock` with
  `tool_use_id`, `content`, `is_error`). Failures ride `is_error=True`
  inside the block; there is no separate `tool_failed` event in v0.1.
  Unmatched ids (no preceding `tool_invoked`) drop silently to avoid
  forging a parent span. Also flips `state.tool_result_arrived = True`
  so the next `AssistantMessage` opens a new turn.

## SystemMessage subtypes (subagent dispatch via Task tool)

- [ ] `TaskStartedMessage` / `TaskNotificationMessage` →
  `avp.subagent_invoked` / `avp.subagent_returned`. Populate
  `avp.subagent.usage` (`SubagentUsage`) from `TaskUsage` — in-process
  fallback per spec §6: the SDK black-boxes the child loop, so the rollup
  on `subagent_returned` is the only signal of child spend. Use a
  `_msg_field(message, field)` helper for SDK version compatibility
  (`>=0.1.11` top-level attrs vs `0.1.10` data dict).
- [ ] `TaskProgressMessage` — drop.
- [ ] Unknown subtypes — drop (honest-silent beats fabricated events).

## Terminal events (spec §8 #3, #6)

- [x] `ResultMessage` → close pending turn (drain `turn_content` /
  `turn_usage_delta` into a final `assistant_message` if not already
  emitted), then `avp.agent_stopped`:
  - `avp.reason = "converged"` (normal) / `"error"` (`is_error=True`)
  - `avp.reason = "refused"` when `ResultMessage.stop_reason == "refusal"`
  - `avp.output` = `ResultMessage.result` when present
  - Sets `state.stopped = True` so `disconnect()` doesn't double-emit.
- [x] `receive_response()` wrapper exceptions (`CLIConnectionError`,
  `ProcessError`, etc.) → `avp.error_occurred(code="agent_crash")` then
  `avp.agent_stopped("error")` before re-raising. (Live-path coverage
  TBD; the dispatch unit tests cover the `ResultMessage` paths.)
- [x] `CancelledError` in `receive_response()` →
  `avp.agent_stopped("interrupted")`. NOTE: the current handler treats
  every `BaseException` that isn't `Exception` as a real cancellation.
  Spurious cleanup-time `CancelledError`s from the SDK have been
  observed in Braintrust's wrapper; if they surface here, lift the
  suppression comment from `_stream_messages_with_tracing` and dedupe.
- [x] `disconnect()` fallback — if `state` exists and not
  `state.stopped`, emit `avp.agent_stopped("converged")` (the run ended
  cleanly without a `ResultMessage`). `state.stopped` guard prevents
  double-emit when `ResultMessage` already fired.

## Conformance floor (spec §8)

- [x] Trajectory opens with `run_requested → agent_described → agent_started`.
- [x] CloudEvents envelope on every event; `source = "avp://agent"`.
- [x] Span triple on every event; prelude at ZERO; turns under `agent_span_id`.
- [x] Every model inference brackets with a single `assistant_message`
  carrying `avp.content`, `avp.usage`, `avp.cost_usd`, `avp.duration_ms`.
- [x] Every tool call brackets with `tool_invoked` / `tool_returned`
  (failures via `tool_result.is_error`, no `tool_failed` type).
- [x] `ResultMessage` → `agent_stopped` with correct reason.
- [x] Last event is always `agent_stopped`; exceptions handled; `disconnect()`
  fallback covers clean close without `ResultMessage`.
- [ ] All emitted events validate against `trajectory.schema.json`. (Stage 4 sweep.)

## Decisions (resolved)

1. **Primary surface** — `AVPClaudeSDKClient` (wraps `ClaudeSDKClient`).
   `query()` free function is out of scope: no pre-run lifecycle, so no
   conformant `agent_started`.
2. **Sink** — passed into `AVPClaudeSDKClient(sink=...)`; stored on the
   instance and copied onto `RunState` at `connect()`. Stage 3
   `setup_avp(sink=...)` patches the class with a default sink.
3. **State** — `RunState` dataclass on a `ContextVar`; no module globals;
   concurrent clients isolated per asyncio task.
4. **Merge gate** — `tool_result_arrived` flag on `RunState`; mirrors
   Braintrust's `next_llm_start`. Consecutive `AssistantMessage`s without
   a `UserMessage(ToolResultBlock)` = same LLM call, not a new turn.
   They APPEND into the open turn's content/usage accumulator.
5. **Single assistant_message** — v0.1 merged `model_turn_started` +
   `model_turn_ended` into one event. Emit on turn close (next tool
   result, or `ResultMessage`). `avp.content` is the merged content list.
6. **Per-turn cost** — `compute_cost()` from `avp.pricing`; stamp
   `avp.cost.source = "computed"` / `"unknown"`. `assistant_message`
   carries `avp.cost_usd`; consumers reduce the stream (spec §7.1).
7. **No Commission on `run_requested`** — `AVPClaudeSDKClient` /
   `setup_avp` path omits `avp.commission` and `avp.supervisor.*`.
   `run_avp_agent` (Stage 3) handles the Commission path.
8. **Task tool** → `subagent_invoked` / `subagent_returned` with
   `avp.subagent.usage` (in-process fallback, spec §6).
9. **`agent_stopped` payload** — only `avp.reason` + optional `avp.output`;
   no cumulative totals (spec §7.1).
10. **Class-name dispatch** — `type(message).__name__` not `isinstance`;
    decoupled from SDK imports and resilient to class hierarchy changes.
11. **Double-stop guard** — `state.stopped: bool` flips on first emit
    (`ResultMessage` handler, exception handler, or `disconnect()`
    fallback). Subsequent handlers no-op.
