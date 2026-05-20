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

## How events are sourced

Every AVP event traces back to one SDK signal — no hook callbacks, no contextvar-mediated ambient state. The `handle_message` dispatcher routes incoming SDK messages to per-type handlers that mutate `RunState` and emit AVP events through the run's sink:

| AVP event | Source |
|---|---|
| `assistant_message` | `AssistantMessage` chunks merged by `message_id`, flushed at turn close |
| `tool_invoked` | `ToolUseBlock` / `ServerToolUseBlock` in `AssistantMessage.content` |
| `tool_returned` | `ToolResultBlock` in `UserMessage.content` (or inline `ServerToolResultBlock` for server tools) |
| `subagent_invoked` | `TaskStartedMessage` |
| `subagent_returned` / `subagent_failed` | `TaskNotificationMessage` (`completed` / `stopped` vs `failed`) |

Why not the SDK's `PreToolUse` / `PostToolUse` hooks? They'd work, but tool-related state would split across two execution contexts (callback vs. message handler). Sourcing everything from the message stream keeps the model uniform and the state machine in one place. Task dispatches are bracketed via the message stream specifically because `SubagentStop` doesn't carry the terminal `status` / `summary` / `usage` payload — `TaskNotificationMessage` does. Subagent-interior activity (`parent_tool_use_id is not None`) is dropped and rolls up under `subagent_returned.subagent_usage` per spec §5.6.

## Architecture

```
_client.py     AVPClaudeSDKClient (probe-then-run connect, error/cancel handling)
_emit.py       Per-message handlers, prelude/terminal emitters, SDK→AVP helpers
_runstate.py   RunState, Turn (per-inference buffer), ToolSpan, TaskInfo
_translator.py SDK init-data → AgentDescriptor fields
```

The hot path is the **deferred-emission pattern** on `Turn`. The Claude CLI fans one API response into multiple `AssistantMessage` chunks sharing a `message_id`. To keep wire ordering causal (assistant_message precedes the tool / subagent events it triggered), each turn buffers AVP events in `Turn.emissions` until a new `message_id` arrives. `RunState.drain()` then flushes one `assistant_message` followed by every buffered event in arrival order. Original timestamps are preserved.

See [CLAUDE.md](CLAUDE.md) for design notes.

## Contributing

- **AVP spec** lives at [`spec/v0.1`](../../../spec/v0.1). Conformance cases at [`conformance/v0.1`](../../../conformance/v0.1). Wire-format changes belong there, not here.
- **Code style:** avoid `Any` / `dict[str, Any]` typing where a concrete type fits; keep docstrings compact (one-line where possible). Use `uv` for dependency management.
- **Subagent-interior events are dropped** (`parent_tool_use_id is not None` on chunks; `tool_use_id` in `state.turn.tasks` on results). Subagent activity surfaces on the parent only via `subagent_invoked` / `subagent_returned` / `subagent_failed`.
- **The reference path is tested manually via [`scripts/`](scripts/).** A real test suite is on the TODO list.

## License

See repository root.
