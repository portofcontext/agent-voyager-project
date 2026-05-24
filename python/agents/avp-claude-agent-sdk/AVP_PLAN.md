# Plan: AVP trajectory via `AVPClaudeSDKClient`

Primary surface is `AVPClaudeSDKClient` (wraps `ClaudeSDKClient`). `query()` is out of scope:
it has no pre-run lifecycle, so a conformant `agent_started` with real tool info is impossible.

## File disposition (clean slate -- no backward compat needed, unreleased)

| File | Action |
|---|---|
| `_runstate.py` | **Keep** -- `RunState` dataclass + ContextVar helpers are reusable as-is |
| `_emit.py` | **Replace** -- `emit_prelude` signature changes (takes `McpStatusResponse` not `ClaudeAgentOptions`); `handle_message` and per-turn emitters are reusable |
| `_translator.py` | **Replace** -- `descriptor_from_options` becomes `descriptor_from_mcp_status`; input changes |
| `_patches.py` | **Delete** -- wraps `query()` exclusively; dead code under the new approach |
| `_agent.py` | **Delete** -- `run_avp_agent` referenced `_patches.py` and scoped runstate around a `query()` call; replaced by Stage 3 entry point |
| `_client.py` | **New** -- `AVPClaudeSDKClient` |
| `__init__.py` | **Replace** -- export `AVPClaudeSDKClient`, `run_avp_agent`, `setup_avp` |

---

## Stage 0 -- Clean slate (needs cleanup)

- Delete `_patches.py` and `_agent.py`.
- Delete `tests/test_stage0.py` (patch idempotency) and `tests/test_query.py`
  (`_wrap_query` harness). Both target the deleted surfaces; new tests land
  against `AVPClaudeSDKClient` in Stage 1.
- Update `__init__.py` to remove the dead exports; stub the new ones.
- `_runstate.py` is unchanged -- ContextVar + `RunState` fields (`trace_id`, `run_id`,
  `agent_span_id`, `current_turn_span_id`, `step`, `tool_result_arrived`, `tool_spans`) all carry over.
- Add `stopped: bool = False` field to `RunState` to guard against double-emit of `agent_stopped`
  (emitted by `ResultMessage` handler AND by `disconnect()` -- only the first should fire).

### Wire-shape drift to absorb (changed since this plan was first written)

- `AgentStartedData` field renames: `gen_ai_provider_name` → `provider_name`
  (alias `avp.provider.name`), `gen_ai_operation_name` → `operation_name`,
  `gen_ai_request_model` → `request_model`. Current `_emit.py` passes the
  old kwargs; they no longer exist on the model.
- `AssistantMessageData` is one merged event (no separate `model_turn_started`
  / `_ended`). Required fields: `step`, `duration_ms`, `content: list[AVPContentBlock]`,
  `usage: Usage`, `cost_usd: float`. Current emit passes zeros for the old
  `gen_ai_usage_*` kwargs; rewrite to populate the real shape (see Stage 1).
- `tool_failed` event type is gone. Failures ride on `tool_returned` with
  `is_error=True` inside the `ToolResultBlock`. Stage 2 dispatch is
  `ToolResultBlock` → `tool_returned` only.

---

## Stage 1 -- `AVPClaudeSDKClient` skeleton + text-only trajectory

New file `_client.py`:

```python
class AVPClaudeSDKClient(ClaudeSDKClient):
    def __init__(self, options=None, transport=None, *, sink=stdio_sink):
        super().__init__(options=options, transport=transport)
        self._sink = sink
        self._avp_token = None

    async def connect(self, prompt=None) -> None:
        await super().connect(prompt)
        status = await self.get_mcp_status()
        state = RunState(trace_id=..., run_id=..., sink=self._sink)
        self._avp_token = set_run(state)
        await emit_prelude(state, prompt, self.options, status)  # agent_started with real tool list

    async def receive_response(self) -> AsyncIterator[Message]:
        # ClaudeSDKClient.query() is fire-and-forget (returns None); the
        # message stream lives on receive_response(). Tee here.
        state = current_run()
        async for message in super().receive_response():
            await handle_message(state, message)
            yield message

    async def disconnect(self) -> None:
        state = current_run()
        if state and not state.stopped:
            await emit_agent_stopped(state, StopReason.converged)
        if self._avp_token is not None:
            reset_run(self._avp_token)
            self._avp_token = None
        await super().disconnect()
```

`query()` is NOT overridden -- it just sends a prompt; teeing happens on `receive_response()`.

`_translator.py` -- replace `descriptor_from_options` with `descriptor_from_mcp_status(prompt, options, status)`:
- builds `AgentDescriptor.tools` from `status["mcpServers"][*]["tools"]`
  (each `McpToolInfo` has `name` + optional `description`; no input schema
  -- `ToolDecl.parameters` is `None` from this source)
- pulls `default_model`, `system_prompt`, `skills`, `subagents` from `options`

`_emit.py` -- update `emit_prelude` signature to accept `McpStatusResponse`
instead of `ClaudeAgentOptions`, and absorb the wire-shape drift listed in
Stage 0:
- `emit_prelude`: use new `provider_name` / `operation_name` / `request_model`
  kwargs on `AgentStartedData`.
- `emit_assistant_message` is the merged event. Build real `content` (translated
  from `AssistantMessage.content[]` -- `TextBlock` → `avp.content.TextBlock`,
  `ThinkingBlock` → `ReasoningBlock`, `ToolUseBlock` → `ToolUseBlock`), real
  `usage` (per-turn delta from `AssistantMessage.usage` against `RunState.prev_cum`),
  and real `cost_usd` (via `avp.pricing.compute_cost`).
- Add `prev_cum` to `RunState` (`{input, output, cache_read, cache_creation}`)
  for cumulative-delta tracking. Silent rebase when `cum < prev` (compaction,
  per `spec/v0.1/trajectory.md` §3.3). Gate the emit on `delta_output > 0`.

The merge gate still gates *turn opening*; the content + usage + cost are
collected across all merged AssistantMessages and emitted once at turn close
(next `UserMessage(ToolResultBlock)` or `ResultMessage`).

Error + cancellation in `receive_response()` override:
- `CancelledError` -> `agent_stopped("interrupted")`
- other exceptions -> `error_occurred` + `agent_stopped("error")`
- set `state.stopped = True` before emitting so `disconnect()` does not double-emit

Stop-gap: `AVPClaudeSDKClient` + `connect()` + `query("2+2")` + `receive_response()` drain +
`disconnect()` produces a schema-valid trajectory ending in `agent_stopped("converged")`
with non-zero token deltas. Cassette replay test + live test.

---

## Stage 2 -- Tool + subagent events

Extend `handle_message` in `_emit.py`:

- `AssistantMessage` with `ToolUseBlock` -> `tool_invoked` (record `tool_use_id -> span_id`
  in `state.tool_spans`). The `ToolUseBlock` also lands in the merged turn's
  `avp.content` list emitted on `assistant_message` (Stage 1 already builds that).
- `UserMessage` with `ToolResultBlock` -> `tool_returned` (single event;
  `is_error=True` flows through `ToolResultBlock.is_error` inside `avp.tool_result`).
  Parent to the saved span_id.
- `block.name == "Agent"` -> `subagent_invoked` / `subagent_returned` with
  `SubagentUsage` carrier on the returned event (in-process fallback per
  `spec/v0.1/trajectory.md` §6: the SDK black-boxes the child loop).

Stop-gap: tool call + result paired by `span_id`; subagent dispatch produces paired events. Schema validation green.

---

## Stage 3 -- Entry points

`run_avp_agent(commission: Commission, agent_main: Callable[[AVPClaudeSDKClient], Awaitable[Any]], sink: EventSink = stdio_sink)`:
- Constructs `AVPClaudeSDKClient` with options derived from `commission`, injects `sink`
- Calls `agent_main(client)` -- caller drives the session
- Guarantees `agent_stopped` in finally

`setup_avp(sink: EventSink = stdio_sink)` monkeypatch:
- Replaces `claude_agent_sdk.ClaudeSDKClient` with `AVPClaudeSDKClient` (not `query`)
- Scans `sys.modules` for stale references (same idempotency pattern as old `_patches.py`)
- Idempotent via `_AVP_WRAPPED` marker on the class

CLI `avp-claude-agent`:
- Reads `Commission` JSON from stdin
- Calls `run_avp_agent` with a default `agent_main`
- Writes trajectory NDJSON to stdout

Stop-gap: `echo '{"prompt":"hi"}' | avp-claude-agent` emits a conforming trajectory to stdout.

---

## Stage 4 -- Conformance sweep

- All cassettes through `trajectory.schema.json` validation.
- Spec MUST checklist: prelude order, `agent_stopped` terminal, per-turn deltas, paired span_ids.
- Document any v0.1 gaps in package README.

Final acceptance: cassettes + live CLI run produce schema-valid trajectories.

---

## Out of scope

- `query()` wrapper -- no pre-run lifecycle, cannot produce conformant `agent_started`
- Per-server MCP lifecycle events -- removed from v0.1 wire (the SDK dials MCP CLI-side with no discrete connect signal exposed to the observer layer). MCP state surfaces as `agent_started.data["avp.mcp_servers"][].status` and tools carry `avp.mcp_server_id`.
- `skill_loaded` -- removed from the v0.1 spec; no wire event exists for it
- Hook callback instrumentation -- not in v0.1 event catalog
