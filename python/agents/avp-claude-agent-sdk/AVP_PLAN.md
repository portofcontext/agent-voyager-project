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
- Update `__init__.py` to remove the dead exports; stub the new ones.
- `_runstate.py` is unchanged -- ContextVar + `RunState` fields (`trace_id`, `run_id`,
  `agent_span_id`, `current_turn_span_id`, `step`, `tool_result_arrived`, `tool_spans`) all carry over.
- Add `stopped: bool = False` field to `RunState` to guard against double-emit of `agent_stopped`
  (emitted by `ResultMessage` handler AND by `disconnect()` -- only the first should fire).

---

## Stage 1 -- `AVPClaudeSDKClient` skeleton + text-only trajectory

New file `_client.py`:

```python
class AVPClaudeSDKClient(ClaudeSDKClient):
    async def connect(self, prompt=None) -> None:
        await super().connect(prompt)
        status = await self.get_mcp_status()
        state = RunState(trace_id=..., run_id=..., sink=self._sink)
        self._avp_token = set_run(state)
        await emit_prelude(state, prompt, status)  # agent_started with real tool list

    async def query(self, prompt, **kwargs) -> AsyncIterator[Message]:
        state = current_run()
        async for message in super().query(prompt, **kwargs):
            await handle_message(state, message)
            yield message

    async def disconnect(self) -> None:
        state = current_run()
        if state and not state.stopped:
            await emit_agent_stopped(state, StopReason.converged)
            reset_run(self._avp_token)
        await super().disconnect()
```

`_translator.py` -- replace `descriptor_from_options` with `descriptor_from_mcp_status(status, prompt, options)`:
- builds `AgentDescriptor.tools` from `status.mcp_servers[*].tools`
- pulls `default_model`, `system_prompt`, `skills`, `subagents` from `options`

`_emit.py` -- update `emit_prelude` signature to accept `McpStatusResponse` instead of `ClaudeAgentOptions`.
Per-turn emitters (`emit_model_turn_started`, `emit_agent_stopped`, `handle_message`) are unchanged.

Error + cancellation in `query()` override:
- `CancelledError` -> `agent_stopped("cancelled")`
- other exceptions -> `error_occurred` + `agent_stopped("error")`
- set `state.stopped = True` before emitting so `disconnect()` does not double-emit

Stop-gap: `AVPClaudeSDKClient` + `connect()` + `query("2+2")` + `disconnect()` produces
a schema-valid trajectory ending in `agent_stopped("converged")` with non-zero token deltas.
Cassette replay test + live test.

---

## Stage 2 -- Tool + subagent events

Extend `handle_message` in `_emit.py`:

- `AssistantMessage` with `ToolUseBlock` -> `tool_invoked` (record `tool_use_id -> span_id` in `state.tool_spans`)
- `UserMessage` with `ToolResultBlock` -> `tool_returned` / `tool_failed`, parented to saved span_id
- `block.name == "Agent"` -> `subagent_invoked` / `subagent_returned` with `SubagentUsage` carrier

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
- `mcp_server_connected` / `skill_loaded` synthesis -- deferred to v0.2
- Hook callback instrumentation -- not in v0.1 event catalog
