# Plan: AVP trajectory via monkeypatched `claude_agent_sdk`

Five stages. Each ends with a runnable scenario validated against `trajectory.schema.json`.

Reference how it is implemented in this in `/Users/elias/code/scratch/wrap-claude-agent-sdk-python`

## Stage 0 — Foundations ✅ DONE

- `_runstate.py`: flat `RunState` dataclass (`trace_id`, `run_id`, `agent_span_id`, `sink`, `current_turn_span_id`, `tool_spans`). One `ContextVar`; `set_run` / `reset_run` / `current_run` helpers.
- `_patches.py`: `apply_patches()` / `restore_patches()` with `_AVP_WRAPPED` marker for idempotency. Direct attr swap on `claude_agent_sdk` module. `_wrap_query` is a passthrough in Stage 0.
- `_emit.py`: stub with stage-annotated comments. Stateless emitter functions (with `RunState` param) to be filled in Stage 1+.
- `_agent.py`: `run_avp_agent(commission, agent_main, sink=stdio_sink)` skeleton — applies patches, scopes a `RunState` via context-var, calls `agent_main`, resets on exit.
- `__init__.py`: exports both `query` and `run_avp_agent`.
- ✅ **Test** (`tests/test_stage0.py`, 8 cases): setup/teardown smoke; patches idempotent; `restore` before `apply` is safe; context-var isolated per asyncio task.

## Stage 1 — `query()` patch, text-only trajectory

- Monkeypatch `claude_agent_sdk.query` with a tee'd async generator. Same shape as wrap-claude-agent-sdk-python's `_create_query_wrapper_function`, minus span work.
- Reuse existing prelude emit code from current `query.py` (`run_requested` → `agent_described` → `agent_started`).
- Per-message emissions:
  - First content block of an `AssistantMessage` → `model_turn_started`
  - `TextBlock` → `text_emitted`
  - `ThinkingBlock` → `reasoning_emitted`
  - End of `AssistantMessage` → `model_turn_ended` carrying per-turn delta of
    `gen_ai.usage.{input,output,cache_read.input,cache_creation.input}_tokens`
    and `avp.cost_usd`, derived by subtracting a running cumulative baseline.
    Reset handling (`cum < prev`) silently rebases the baseline — no error event.
  - `ResultMessage` → `agent_stopped("converged")`. `ResultMessage.total_cost_usd`
    is discarded; wire total = sum of per-turn `avp.cost_usd` deltas, period.
------------ STOP FOR REVIEW -------------

- Cumulative-state tracker lives in `_runstate.py`: `prev_cum = {input, output,
  cache_read, cache_creation, cost_usd}`. Each `AssistantMessage.usage` updates
  it. Hook `PreCompact` / `SubagentStart` if accessible to anticipate resets;
  otherwise rebase silently when `cum < prev`.
- Termination paths: try/finally wraps the stream; `CancelledError` → `agent_stopped("cancelled")`; other exceptions → `error_occurred` + `agent_stopped("error")`. Lift the cancellation comment from wrap-claude-agent-sdk-python's `_stream_messages_with_tracing`.
- Record one SDK message-stream cassette of a no-tool query for replay.
- ✅ **Stop-gap 1**: `claude_agent_sdk.query(prompt="2+2")` produces a schema-valid trajectory ending in `agent_stopped("converged")` with non-zero `avp.cost_usd` and token deltas on the `model_turn_ended`. Cassette replay test + live test against the real SDK.

## Stage 2 — Local tool support

- Extend the message-stream handler:
  - `AssistantMessage` with `ToolUseBlock` → `tool_invoked` (record `tool_use_id → span_id` in runstate map)
  - `UserMessage` with `ToolResultBlock` → `tool_returned` (or `tool_failed` if `is_error`), parented to the saved span_id
  - Special-case `block.name == "Agent"` → `subagent_invoked` / `subagent_returned`.
    The Claude SDK Task tool black-boxes the child loop (only `TaskNotificationMessage`
    + `TaskUsage`), so per spec §5 #6 populate `subagent_returned.data["avp.subagent.usage"]`
    with a `SubagentUsage` carrier (`cost_usd`, `tokens_input`, `tokens_output`, `turns`)
    rather than re-parenting child per-turn events.
- Monkeypatch `claude_agent_sdk.SdkMcpTool`: wrap user-supplied handler with try/except that emits `tool_failed` if the handler raises before the SDK turns it into a `tool_result`. No thread-local span activation — AVP doesn't need it.
- Two new cassettes: tool-using query, subagent-dispatching query.
- ✅ **Stop-gap 2**: tool call + tool result paired by `span_id`; user-handler exception produces `tool_failed`; subagent dispatch produces paired `subagent_invoked` / `subagent_returned`. Schema validation green on both cassettes.

## Stage 3 — `ClaudeSDKClient` patch

- Monkeypatch `claude_agent_sdk.ClaudeSDKClient` per wrap-claude-agent-sdk-python's `_create_client_wrapper_class` shape (wrap `query`, `receive_response`, `__aenter__`, `__aexit__`, `disconnect`).
- Run-state scoping: one run spans the whole client lifetime (connect → disconnect). Multiple `query()` calls inside one client = multiple model turns in one run, not multiple runs.
- Cassette of a 3-turn `ClaudeSDKClient` session.
- ✅ **Stop-gap 3**: multi-turn session produces one `run_requested` / `agent_stopped` pair with N `model_turn_*` pairs nested under `agent_started`'s span.

## Stage 4 — Entry points

- `run_avp_agent(commission: Commission, agent_main: Callable[[], Awaitable[Any]], sink: EventSink = stdio_sink) -> Any`:
  - Apply patches (idempotent)
  - Initialize runstate from `commission`
  - Emit prelude (`run_requested` carrying `avp.commission`, `agent_described`, `agent_started`)
  - `await agent_main()` inside a try/finally that guarantees terminal `agent_stopped`
  - Return whatever `agent_main` returned
- CLI binary `avp-claude-agent`:
  - Reads `Commission` JSON from stdin
  - Default `agent_main` does `claude_agent_sdk.query(prompt=commission.prompt, options=...)` and drains the iterator
  - Writes the trajectory NDJSON to stdout via the default sink
  - `argv` for `--agent-main module:fn` to plug in a custom main
- ✅ **Stop-gap 4**: `echo '{"prompt":"hi"}' | avp-claude-agent` emits a complete conforming trajectory to stdout. Equivalent in-process via `run_avp_agent(commission, lambda: query(...))`.

## Stage 5 — Conformance sweep

- Run all four stop-gap cassettes through `trajectory.schema.json` validation in one pytest module.
- Spec §8 checklist as test cases: prelude order, terminal `agent_stopped`, per-turn `avp.cost_usd` + token deltas on every `model_turn_ended`, paired turn/tool/subagent span_ids.
- Document v0 deviations (no `mcp_server_connected` synthesis, single end-of-run `cost_recorded` if §3.3 deltas are deferred) in the package README.
- ✅ **Final acceptance**: all four cassettes + a live end-to-end CLI run produce schema-valid trajectories.

## Sequencing notes

- Each stage builds on the previous **without rewriting earlier code** — Stage 2 adds branches to the Stage 1 dispatcher, Stage 3 adds a new patch but reuses the same dispatcher.
- Cassette format: capture raw `claude_agent_sdk` `Message` objects to disk (pickle or dataclass-asdict-to-JSON), replay by yielding them from a fake `query` / `receive_response`. No need to record at the subprocess transport layer.
- wrap-claude-agent-sdk-python's `_serialize_content_blocks` helper is worth lifting verbatim — same problem (dataclass content blocks → JSON-shaped dict) regardless of consumer.

## Out of scope (deliberately)

- `mcp_server_connected` / `skill_loaded` synthesis from `SystemMessage` payloads — SDK dials MCP CLI-side via `--mcp-config` so `tools/list` is out of reach; surface registration only on `agent_started`. (Note: when Stage 4 adds Commission support with `mcp_servers`, this becomes a real conformance gap per spec §8 M1/M2 — flag for explicit decision then.)
- Hook callback instrumentation as user-visible events — not in the v0.1 event catalog. (Internal hook subscriptions for baseline-reset anticipation are fine.)

**Total: ~7–10 days**, with a working trajectory at the end of each of stages 1–4.
