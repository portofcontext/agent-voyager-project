# Trajectory implementation checklist — `query()` wrapper

Goal: a user swaps `from claude_agent_sdk import query` for
`from avp_claude_agent import query` and receives a fully AVP-conforming
trajectory out of the box, with the wrapper still yielding the same
`Message` objects upstream `query()` does.

Cross-references:
- Spec: [`spec/v0.1/trajectory.md`](../../../spec/v0.1/trajectory.md)
- AVP event types: [`python/avp/src/avp/trajectory.py`](../../avp/src/avp/trajectory.py)
- AVP agent base / sink: [`python/avp/src/avp/agent/`](../../avp/src/avp/agent/)
- Upstream message shapes: `claude_agent_sdk.types`

## Plumbing: where do AVP events go?

**Decision:** add a `sink: EventSink | None = None` keyword-only param
to the wrapper's `query()`. When `None`, default to `avp.agent.stdio_sink`.
The wrapper still yields the same `Message` objects upstream does, so
the drop-in is preserved as long as callers don't print Messages to
stdout (the default sink writes NDJSON to stdout — note this in the
docstring so users with mixed-stdout concerns pass a file-backed sink).

- [ ] Extend the wrapper signature: `async def query(*, prompt, options=None,
  transport=None, sink: EventSink | None = None) -> AsyncIterator[Message]`.
  Import `EventSink` and `stdio_sink` from `avp.agent`.
- [ ] Inside `query()`, construct a per-call `AVPAgentSink(sink or stdio_sink)`
  and pass it through the translator state. Per-call construction (not
  module state) keeps concurrent `query()` invocations from cross-firing.

## Run prelude (spec §2.1) — emit before consuming any SDK message

Three events, in order. There's no Commission in a bare `query()` call
(it's the library-invocation path), so `run_requested` omits the
Commission/supervisor attribution fields per spec §2.1; the agent's
invocation surface is advertised on `agent_described` instead.

- [x] `avp.run_requested` (source `avp://agent`). No Commission → omit
  both `data["avp.commission"]` and `data["avp.supervisor.*"]` entirely
  (per spec §2.1, absence — not `"unknown"` — is the canonical signal).
  The event still anchors the run via `subject = run_id` and a fresh
  span triple (`parent_span_id = ZERO`). Run-config details (`cwd`,
  `permission_mode`, `allowed_tools`, etc.) stay agent-internal; they
  don't ride on the wire.
- [x] `avp.agent_described`. Minimal `AgentDescriptor` with
  `name = "avp-claude-agent-sdk"`, `version` from `pyproject.toml`,
  `avp_spec_version = "0.1"`. `parent_span_id = ZERO`.
- [x] `avp.agent_started`. Open the agent span (`span_id` here is the
  parent for every subsequent event). Populate:
  - `gen_ai.provider.name = "anthropic"`, `gen_ai.request.model` from options
  - `prompt` (str form when available)
  - `system_prompt` (resolve `SystemPromptFile` → file body; preset →
    omit, since the preset name isn't the literal prompt)
  - `tools[]` (start empty; appended after MCP `tools/list` lands if we
    ever see one)

## Per-turn loop — translator over `query()`'s async iterator

The SDK doesn't ship explicit `turn_started` / `turn_ended` hooks. Use
this rule: a turn is one `AssistantMessage` that carries new model
output. Per spec §3.1 + §3.3 + the docstring on `ResultMessage`, the
SDK reports usage cumulatively, so the wrapper MUST derive deltas.

- [ ] Open a turn span when an `AssistantMessage` arrives. Emit
  `avp.model_turn_started(step=N)` with `parent_span_id =
  agent_span_id`. Track `step` 0-indexed (or 1-indexed — match the
  reference agent).
- [ ] Track cumulative usage state in the wrapper: `prev_cum = {input,
  output, cache_read, cache_creation, cost_usd}`. After each
  `AssistantMessage.usage`, compute deltas. If `cum < prev`, emit
  `avp.error_occurred(code="accounting_reset")` per spec §3.3.
- [ ] `avp.model_turn_ended` at the end of each turn. Map:
  - `gen_ai.usage.input_tokens` = delta input (incl. cache reads, per §3.3)
  - `gen_ai.usage.output_tokens` = delta output
  - `gen_ai.usage.cache_read.input_tokens`,
    `gen_ai.usage.cache_creation.input_tokens` = deltas
  - `gen_ai.response.model` = `AssistantMessage.model`
  - `gen_ai.response.finish_reasons = [AssistantMessage.stop_reason]`
    when present
  - `avp.cost_usd` = per-turn delta computed via the
    `compute_cost(...)` helper (see *Pricing* below); stamp
    `avp.cost.source="computed"`, or `"unknown"` when the model id
    isn't in the price table. The post-`ResultMessage` reconciliation
    `cost_recorded` event uses `"reported"`.

### Pricing (per-turn cost computation)

Use [`avp.pricing`](../../avp/src/avp/pricing.py) at the core package:
`ModelPrice`, `load_default_prices()`, `compute_cost(...)`. Promoted out
of archive so future Anthropic-model adapters (LangChain, etc.) share
the same price table and provenance constants.

- [ ] In the wrapper, `from avp.pricing import compute_cost,
  load_default_prices`.
- [ ] Load the price table once at the top of `query()` (not per turn),
  pass it through translator state.
- [ ] `avp.cost_recorded` at least once per turn (spec §8 conformance
  #5). Carries the cumulative `RunStateSnapshot`. Same `parent_span_id
  = agent_span_id`.

## Content-block translation (per `AssistantMessage.content[]`)

`AssistantMessage.content` is a list of `TextBlock | ThinkingBlock |
ToolUseBlock | ServerToolUseBlock` and `UserMessage.content` is where
`ToolResultBlock` lands. Walk each block in order.

- [ ] `TextBlock` → `avp.text_emitted(step=N, avp.text=block.text)`.
- [ ] `ThinkingBlock` → `avp.reasoning_emitted(step=N,
  avp.reasoning.text=block.thinking,
  avp.reasoning.signature=block.signature)`.
- [ ] `ToolUseBlock` → `avp.tool_invoked` with
  `gen_ai.tool.call.id=block.id`, `gen_ai.tool.name=block.name`,
  `gen_ai.tool.call.arguments=block.input`,
  `avp.tool.dispatch_target="local"` (built-in) or `"mcp_server"` (if
  name maps to an MCP server). Use a `pending_tool_calls: dict[id →
  start_ts]` to time the round-trip.
- [ ] `ToolResultBlock` (arrives in a subsequent `UserMessage.content`)
  → `avp.tool_returned` (or `avp.tool_failed` if `is_error=True`). Look
  up `tool_use_id` to pair with the `tool_invoked`, compute
  `duration_ms`, set `avp.tool.result.text` (stringify `content`).
- [ ] `ServerToolUseBlock` / `ServerToolResultBlock` → same
  `tool_invoked` / `tool_returned` mapping; tag
  `avp.tool.dispatch_target="local"` (the API ran it for us, so from
  AVP's view it's not MCP). Note this in code so we don't accidentally
  emit MCP-server fields.
- [ ] Refusal: when `AssistantMessage.stop_reason == "refusal"` (or
  `error == "rate_limit"` etc. on a turn that produced no useful
  content), emit `avp.refusal_recorded` and stop with
  `reason="refused"`.

## SystemMessage subtypes

`SystemMessage` is a discriminated bag. Most subtypes are runtime
telemetry; map only the ones with AVP equivalents, drop the rest.

- [ ] `SystemMessage(subtype="init")` — refine
  `agent_started.data.gen_ai.request.model` / tools list using the init
  payload if it lands before we emit. Otherwise ignore.
- [ ] `TaskStartedMessage` / `TaskProgressMessage` /
  `TaskNotificationMessage` — the SDK's Task tool is a subagent. Map to
  `avp.subagent_invoked` / `avp.subagent_returned` (or
  `subagent_failed`) keyed on `task_id`. `gen_ai.agent.name = task_type
  or "task"`, `avp.subagent.usage` from `TaskUsage`. Open the subagent
  frame span on `TaskStartedMessage`; pair on notification.
  `avp.subagent.run_id` stays `None` (the SDK doesn't surface a
  separate AVP run for the Task tool); per
  `SubagentInvokedData` docstring this is the in-process pattern.
  `TaskProgressMessage` is informational — drop unless we want
  intermediate `cost_recorded` snapshots scoped to the subagent (defer
  to a v0.2 iteration).
- [ ] `MirrorErrorMessage` → drop (non-fatal session-store telemetry).
- [ ] Unknown subtype → drop (don't fabricate events; honest-silent
  beats fabricated events).

## Terminal events

- [ ] `ResultMessage` → emit a reconciliation `avp.cost_recorded` with
  `avp.cost.source="reported"` (see `CostRecordedData` docstring in
  `avp.trajectory`), using `total_cost_usd` and `usage` totals. Then
  emit `avp.agent_stopped`:
  - `avp.reason` = `converged` (normal), `error` (when `is_error=True`),
    `refused` (refusal path)
  - `avp.state` = final `RunStateSnapshot`
  - Use the convenience aliases (`avp.total_*`) populated from `state`
    — the model validator on `AgentStoppedData` enforces they match
- [ ] `RateLimitEvent` → `avp.error_occurred(code=rate_limit,
  message=...)`. Don't stop the run on its own; let the SDK's behavior
  decide.
- [ ] Wrapper-raised exceptions (e.g., `CLIConnectionError`,
  `ProcessError`) → emit `avp.error_occurred(code=agent_crash,
  message=str(e))` then `avp.agent_stopped(reason="error")` before
  re-raising. Spec §8 #6: last event MUST be `agent_stopped`.
- [ ] `StreamEvent` → optional; can be used to populate
  `gen_ai.response.time_to_first_chunk` on the next `model_turn_ended`.
  Skip if you want a v0 cut.

## State / context plumbing inside the wrapper

- [ ] Hold per-call state: `agent_span_id`, `current_turn_span_id`,
  `step_counter`, `prev_cum_usage`, `pending_tool_calls`,
  `pending_subagent_frames`, `start_ts`. Keep it on a local dataclass
  — not module globals (concurrency).
- [ ] Use `avp._envelope.new_trace_id() / new_span_id() / now_iso()`
  for IDs and timestamps.
- [ ] Use `event_to_wire()` only when serializing for the sink; emit
  Pydantic events to the `AVPAgentSink` directly otherwise.

## Conformance floor (spec §8)

These are the hard MUSTs to satisfy before declaring the wrapper
"AVP-conforming":

- [ ] Trajectory opens with `run_requested → agent_described →
  agent_started` in that order.
- [ ] Every model inference brackets with `model_turn_started` /
  `model_turn_ended`.
- [ ] Every tool call brackets with `tool_invoked` and exactly one of
  `tool_returned` / `tool_failed`.
- [ ] At least one `cost_recorded` per turn; `data["avp.state"]`
  validates against `RunStateSnapshot`.
- [ ] Last event is `agent_stopped`; nothing after.
- [ ] All emitted events validate against `trajectory.schema.json`
  (gate this with a unit test that runs each emitted event through
  `parse_event`).

## Decisions (resolved)

1. **Sink** — kwarg `sink: EventSink | None = None` on `query()`,
   defaulting to `avp.agent.stdio_sink` (NDJSON to stdout).
2. **Per-turn cost** — `compute_cost()` from `avp.pricing`, stamping
   `avp.cost.source` as `computed` / `unknown` / `reported`.
3. **No Commission on `run_requested`** — `query()` is the
   library-invocation path; per spec §2.1, omit `avp.commission` and
   `avp.supervisor.*`. A separate Commission-aware entry point (for
   AVP supervisors) is the place to relay a snapshot.
4. **Task tool** — modeled as `avp.subagent_invoked` /
   `subagent_returned` (`avp.subagent.run_id` stays `None`).
