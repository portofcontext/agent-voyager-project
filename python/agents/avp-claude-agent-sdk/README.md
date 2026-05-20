# avp-claude-agent-sdk

An [AVP](../../../spec/v0.1)-compliant wrapper around the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python). Exposes [`AVPClaudeSDKClient`](src/avp_claude_agent_sdk/_client.py), a drop-in subclass of `ClaudeSDKClient` that emits a conforming AVP trajectory across `connect()` → `query()` / `receive_response()` → `disconnect()`.

## Install

> [!NOTE]
> TODO: install instructions

## Usage

> [!NOTE]
> TODO: minimal example


## What it does

For every run of a `claude-agent-sdk` session, this package produces the AVP event stream:

- `run_requested` — anchors the run
- `agent_described` — pre-Commission capability surface, discovered via a probe session
- `agent_started` — merged-state snapshot of tools / MCP servers / skills / subagents
- `assistant_message` — one event per inference (one Anthropic `message_id`), with full content, usage, and cost
- `tool_invoked` / `tool_returned` — bracketing every tool dispatch (success and failure paths)
- `subagent_invoked` / `subagent_returned` / `subagent_failed` — bracketing every Task dispatch with the subagent's terminal summary and usage
- `agent_stopped` — final event of the run

The wire format is defined by the [`avp`](../../avp) package; this adapter contributes no schema of its own.

## Hooks where possible

Tool bracketing uses the Claude Agent SDK's [hook callbacks](https://code.claude.com/docs/en/agent-sdk/hooks), not content-block inference:

- **`PreToolUse`** → `tool_invoked` (records a [`ToolSpan`](src/avp_claude_agent_sdk/_runstate.py) keyed by `tool_use_id`)
- **`PostToolUse`** → `tool_returned` (successful dispatch)
- **`PostToolUseFailure`** → `tool_returned` with `is_error=True` (errors, permission denials, interrupts)

Task (subagent) dispatches are bracketed separately by `TaskStartedMessage` → `subagent_invoked` and `TaskNotificationMessage` → `subagent_returned` / `subagent_failed`, since those carry richer payload (task_type, summary, usage) than the tool hooks. The tool hooks skip `tool_name == "Task"` to avoid double-emission. Tools fired *from inside* a subagent are dropped (they roll up under `subagent_returned.subagent_usage` per spec §5.6).

The CLI's hooks are the authoritative "this dispatch actually happened" signal — they fire for every dispatched tool regardless of whether it produced a `ToolUseBlock` the SDK surfaces back to us. Inferring tool calls from `AssistantMessage.content` would miss eager-dispatch and parallel cases the CLI handles internally.

User-supplied hook callbacks under the same names are preserved — ours are appended alongside, not in place of.


## Architecture

```
_client.py     AVPClaudeSDKClient + hook registration (_install_avp_hooks)
_emit.py       Emitters, hook callbacks, SDK→AVP translation helpers
_runstate.py   RunState, Turn (per-inference buffer), ToolSpan
_translator.py SDK init-data → AgentDescriptor fields
```

The hot path is the **deferred-emission pattern** in `_runstate.py:Turn`. The Claude CLI fans one API response into multiple `AssistantMessage` chunks (one per content block) sharing a `message_id`, and dispatches tools eagerly between them. To keep wire ordering causal (assistant_message precedes its tool_invokeds), each turn buffers in `Turn.emissions` until a new `message_id` arrives — then `RunState.drain()` flushes one `assistant_message` followed by every buffered event in arrival order. Original timestamps are preserved on each event.

See [CLAUDE.md](CLAUDE.md) for the design rationale and active development notes.

## Contributing

- **AVP spec** lives at [`spec/v0.1`](../../../spec/v0.1). Conformance cases at [`conformance/v0.1`](../../../conformance/v0.1). Wire-format changes belong there, not here.
- **Code style:** avoid `Any` / `dict[str, Any]` typing where a concrete type fits; keep docstrings compact (one-line where possible). Use `uv` for dependency management.
- **Subagents are out of scope for now.** All three hooks short-circuit when `input_data["agent_id"]` is present (the SDK's marker for "fires inside a Task-spawned subagent"). Subagent activity will surface via `subagent_invoked` / `subagent_returned` in a later pass.
- **The reference (success) path is tested manually via [`scripts/`](scripts/).** A real test suite is on the TODO list.

## License

See repository root.
