# ClaudeSDKClient and Braintrust Integration Review

## Part 1: ClaudeSDKClient

Source package: `claude_agent_sdk` (installed at `.venv/lib/python3.13/site-packages/claude_agent_sdk/`)

### Overview

`ClaudeSDKClient` is a stateful, bidirectional client for driving the Claude Code CLI as a subprocess. Unlike the one-shot `query()` helper, the client maintains conversation state across multiple turns and exposes hooks, control-protocol commands, and session-resume capabilities.

The class is defined in `client.py:26-628`. The internal workhorse is a `Query` object (in `_internal/query.py`) that owns the I/O loop; `ClaudeSDKClient` is a thin session-management shell on top of it.

---

### Lifecycle

```
__aenter__ / connect()
    → validate options, materialize session-store if resuming
    → create SubprocessCLITransport (spawns claude CLI subprocess)
    → create Query: register hooks, set up MCP, initialize() handshake
    → optional: send initial prompt or stream AsyncIterable of messages

query(prompt)           # send a new user turn

receive_response()      # async iterator; stops on ResultMessage
receive_messages()      # async iterator; never stops on its own

disconnect() / __aexit__
    → close Query, terminate transport, clean up temp dirs
```

`connect()` (`client.py:99-145`) handles two cases: a fresh session and a resumed one. When resuming from a `session_store`, the transcript is materialized into a temporary `CLAUDE_CONFIG_DIR` before the subprocess starts so the CLI can load it.

---

### Sending Messages: `query()`

`client.py:283-311`. Serializes the prompt into a JSONL message and writes it to the subprocess stdin via `transport.write()`.

Message wire shape:

```json
{
  "type": "user",
  "message": {"role": "user", "content": "<prompt>"},
  "parent_tool_use_id": null,
  "session_id": "default"
}
```

When `prompt` is an `AsyncIterable[dict]`, each item is JSON-serialized and written in sequence. There is no built-in synchronization between writes and reads; the caller coordinates with `receive_response()`.

---

### Receiving Responses: `receive_response()` and `receive_messages()`

`receive_messages()` (`client.py:271-281`) is an infinite async generator that yields every message coming out of the `Query` stream.

`receive_response()` (`client.py:567-606`) wraps it and returns after the first `ResultMessage`, making it convenient for a single-turn request/response pattern.

Internally, `Query._read_messages()` (`query.py:247-373`) runs as a background task. It reads JSONL from CLI stdout and routes each line:

| Message subtype | Action |
|---|---|
| `control_response` | Resolves a pending outgoing request future |
| `control_request` | Spawns a handler task (hooks, tool permissions, MCP) |
| `control_cancel_request` | Cancels an inflight handler |
| `transcript_mirror` | Enqueues into SessionStore batcher (not yielded) |
| `result` | Flushes SessionStore, sets `_first_result_event`, then yields |
| Everything else | Yields directly to message stream |

---

### Message Types

Defined in `types.py`. The `Message` union (`types.py:1260-1267`):

| Type | When it appears |
|---|---|
| `UserMessage` | Echo of the user turn sent via `query()` |
| `AssistantMessage` | Claude response; contains `content` blocks, `model`, `usage`, `stop_reason` |
| `SystemMessage` | Base for task lifecycle and hook events, discriminated by `subtype` |
| `TaskStartedMessage` | Long-running task has begun |
| `TaskProgressMessage` | Periodic progress update with cumulative usage |
| `TaskNotificationMessage` | Task finished, failed, or stopped |
| `HookEventMessage` | Hook lifecycle (requires `include_hook_events=True`) |
| `MirrorErrorMessage` | SessionStore append failure (non-fatal) |
| `ResultMessage` | End of turn; carries `duration_ms`, `total_cost_usd`, `usage`, `stop_reason` |
| `StreamEvent` | Raw Anthropic API stream event (requires `include_partial_messages=True`) |
| `RateLimitEvent` | Rate limit status change |

`AssistantMessage.content` is a list of typed blocks: `TextBlock`, `ThinkingBlock`, `ToolUseBlock`, `ToolResultBlock`, etc.

---

### Hooks

`ClaudeAgentOptions.hooks` is a `dict[HookEvent, list[HookMatcher]]`. Each `HookMatcher` holds:

- `matcher`: optional tool-name filter (regex string)
- `hooks`: list of async callback functions
- `timeout`: per-hook timeout

Callback signature (`types.py:572-579`):

```python
async def my_hook(
    input: HookInput,          # event-specific typed dict
    tool_use_id: str | None,
    context: HookContext,
) -> HookJSONOutput: ...
```

On `initialize()`, the Query converts the user's `HookMatcher` list into a dict keyed by generated IDs (e.g., `hook_0`). When the CLI fires a `control_request` with `subtype: "hook_callback"`, the Query looks up the callback and invokes it, then sends the result back as a `control_response`.

Hook events include: `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`, `Notification`, `SubagentStart`, `PermissionRequest`.

---

### Control Protocol Commands

Mid-conversation control commands send a `control_request` to the CLI and await a `control_response`. The relevant `ClaudeSDKClient` methods:

| Method | Lines | Purpose |
|---|---|---|
| `interrupt()` | 313-317 | Send interrupt signal |
| `set_permission_mode(mode)` | 319-344 | Change permission mode |
| `set_model(model)` | 346-368 | Switch model |
| `rewind_files(user_message_id)` | 370-400 | Rewind filesystem to a prior state |
| `reconnect_mcp_server(name)` | 402-422 | Reconnect a dropped MCP server |
| `toggle_mcp_server(name, enabled)` | 424-448 | Enable or disable an MCP server |
| `stop_task(task_id)` | 450-471 | Stop a running task |
| `get_mcp_status()` | 473-504 | Query live MCP connection status |
| `get_context_usage()` | 506-540 | Query context window usage |
| `get_server_info()` | 542-565 | Get server initialization info |

---

### MCP Server Integration

MCP servers can be passed via `ClaudeAgentOptions.mcp_servers`. The SDK supports four transport types: stdio, SSE, HTTP, and "SDK MCP" (in-process Python handlers).

For SDK MCP servers, the Query intercepts `control_request: mcp_message` from the CLI and handles the JSON-RPC protocol directly in Python (`query.py:585-714`): `initialize`, `tools/list`, `tools/call`, and `notifications/initialized`.

---

### Transport

`SubprocessCLITransport` is the default. It spawns the Claude Code CLI as a subprocess and communicates via stdin/stdout JSONL. The abstract `Transport` interface (`_internal/transport/__init__.py:8-69`) requires: `connect()`, `write(data)`, `read_messages()`, `close()`, `is_ready()`, `end_input()`. A custom transport can be injected via `ClaudeSDKClient(transport=...)`.

---

### Key Options (`ClaudeAgentOptions`)

Selected notable options from `types.py:1577-1932`:

| Option | Purpose |
|---|---|
| `model` | Claude model to use |
| `tools` / `allowed_tools` / `disallowed_tools` | Tool availability and auto-allow list |
| `permission_mode` | `default`, `acceptEdits`, `bypassPermissions`, etc. |
| `mcp_servers` | MCP server configurations |
| `max_turns` / `max_budget_usd` | Hard stop conditions |
| `continue_conversation` / `resume` | Session continuity |
| `hooks` | Hook callbacks dict |
| `can_use_tool` | Custom permission callback (requires AsyncIterable prompt) |
| `session_store` | External transcript mirror |
| `thinking` | Extended thinking control |
| `include_partial_messages` | Stream raw Anthropic events |
| `cwd` | Working directory for the subprocess |
| `env` | Environment variables for the subprocess |

---

## Part 2: `setup_claude_agent_sdk` (Braintrust Integration)

Source: `/Users/elias/code/scratch/wrap-claude-agent-sdk-python/py/src/braintrust/integrations/claude_agent_sdk/`

### What It Does

`setup_claude_agent_sdk()` instruments the Claude Agent SDK for automatic tracing into Braintrust. It works by replacing SDK classes in place so that imports made before or after the call both get the instrumented versions.

Entry point (`__init__.py:29-64`):

```python
def setup_claude_agent_sdk(api_key=None, project_id=None, project=None) -> bool:
    span = current_span()
    if span == NOOP_SPAN:
        init_logger(project=project, api_key=api_key, project_id=project_id)
    return ClaudeAgentSDKIntegration.setup()
```

It initializes the Braintrust logger only if there is no active parent span (avoids redundant re-initialization when called inside an existing trace). Then it calls `setup()` which applies all patchers.

---

### Patching Strategy (`patchers.py`)

Three `ClassReplacementPatcher` subclasses swap out SDK symbols:

| Patcher | Target | Purpose |
|---|---|---|
| `ClaudeSDKClientPatcher` | `claude_agent_sdk.ClaudeSDKClient` | Wraps the interactive client class |
| `ClaudeSDKQueryPatcher` | `claude_agent_sdk.query` | Wraps the one-shot query helper |
| `SdkMcpToolPatcher` | `claude_agent_sdk.SdkMcpTool` | Intercepts in-process MCP tool construction |

Class replacement (not function wrapping) means the patch affects any module that already imported the SDK before `setup()` was called. The `ClassReplacementPatcher` base class handles the mechanics of replacing the symbol in the module's namespace.

---

### Wrapper Classes (`tracing.py`)

#### `WrappedClaudeSDKClient`

Created by `_create_client_wrapper_class()` (`tracing.py:1042-1162`). Wraps the original class and adds per-instance tracing state:

- `__last_prompt`: captured from `query()` call
- `__query_start_time`: timestamp when `query()` was called
- `__request_tracker`: active `RequestTracker` for the current turn
- `__instrumented_hook_callbacks`: set of callback IDs already wrapped

**`query()` override** (`tracing.py:1112-1135`): captures the prompt, creates a `RequestTracker` (which opens the root `"Claude Agent"` TASK span), then calls the original `query()`. It also scans the internal `_query.hook_callbacks` dict and wraps each callback with `trace_hook_callback()`.

**`receive_response()` override** (`tracing.py:1137-1147`): pipes messages through `_stream_messages_with_tracing()` which feeds each message to the `RequestTracker` before yielding it to the caller.

#### `_create_query_wrapper_function`

Wraps the one-shot `claude_agent_sdk.query()` helper the same way: captures prompt and start time, creates a `RequestTracker`, streams messages through the tracing pipeline.

#### `WrappedSdkMcpTool`

Created by `_create_tool_wrapper_class()` (`tracing.py:216-233`). Intercepts handler registration in `__init__` and wraps each handler with `_wrap_tool_handler()`. This ensures that when an in-process MCP tool handler runs, it executes under the stream-based TOOL span that was opened for that tool call (matched via `ToolSpanTracker`).

---

### Span Hierarchy

For each `query()` + `receive_response()` cycle, the integration creates this span tree:

```
TASK "Claude Agent"                   # root span, one per query() call
  LLM "anthropic.messages.create"     # one per AssistantMessage
    TOOL "<tool_name>"                 # one per ToolUseBlock; closed on ToolResultBlock
      FUNCTION "<event> hook"          # one per hook callback invocation
  TASK "<task description>"            # one per TaskStarted system message
```

Multiple LLM spans can appear within one root TASK span (multi-turn or multi-agent runs). Subagent contexts are tracked separately via `parent_tool_use_id` keying in `ContextTracker`.

---

### Tracing Components (`tracing.py`)

#### `ContextTracker` (lines 567-884)

Single consumer of the raw SDK message stream. Maintains one `_AgentContext` per `parent_tool_use_id` (None = root orchestrator, non-None = subagent context).

Message handlers:

- `_handle_assistant(message)`: opens or merges LLM spans; calls `ToolSpanTracker.start_tool_spans()` for each `ToolUseBlock`
- `_handle_user(message)`: calls `ToolSpanTracker.finish_tool_spans()` for each `ToolResultBlock`
- `_handle_result(message)`: extracts usage via `extract_anthropic_usage()`, logs `total_cost_usd`, `duration_ms`, and final output to the root span
- `_handle_system(message)`: opens/updates TASK spans for `TaskStarted`, `TaskProgress`, `TaskNotification`

#### `ToolSpanTracker` (lines 274-459)

Manages the lifecycle of TOOL spans independently from message ordering.

**Problem it solves:** The SDK emits `ToolUseBlock` in `AssistantMessage` and `ToolResultBlock` in a later `UserMessage`. In parallel and subagent scenarios, multiple tool calls with the same name can be in flight simultaneously. `ToolSpanTracker` tracks them by `tool_use_id` and uses `(tool_name, input_signature)` dispatch queues to match a stream-based span to the handler execution that needs to attach to it.

`acquire_span_for_handler()` (lines 375-395): called from `_wrap_tool_handler()` to claim the matching TOOL span before the handler runs.

#### `RequestTracker` (lines 886-966)

Request-scoped coordinator. Delegates `add_message()` to `ContextTracker` and wraps hook callbacks in FUNCTION spans via `trace_hook_callback()` (lines 916-939). `finish()` finalizes all open spans and optionally logs the final output.

---

### What Gets Recorded

| Span | Input | Output | Key Metadata |
|---|---|---|---|
| TASK `"Claude Agent"` | Prompt | Final result text | `num_turns`, `session_id`, `stop_reason`, `total_cost_usd`, `duration_ms` |
| LLM `"anthropic.messages.create"` | Messages array | Content blocks | `model`, `prompt_tokens`, `completion_tokens`, `time_to_first_token` |
| TOOL `"<name>"` | Tool input dict | Tool result content | `gen_ai.tool.name`, `gen_ai.tool.call.id`, `mcp.server` (if MCP) |
| TASK `"<description>"` | N/A | Task summary | `task_id`, `task_type`, `status`, `last_tool_name`, `usage` |
| FUNCTION `"<event> hook"` | Serialized hook input | Hook output | `claude_agent_sdk.hook.event_name`, `claude_agent_sdk.hook.callback_name` |

Token counts are sourced from `ResultMessage.usage` (end-of-turn summary, not per-chunk). MCP tool names are parsed from the `mcp__<server>__<tool>` format and stored with the MCP server name as a separate attribute.

---

### Thread-Local State

`tracing.py:29` declares a `threading.local()` to store the active `ToolSpanTracker` during request processing. This lets `_wrap_tool_handler()` retrieve the correct TOOL span from inside a handler callback without passing it explicitly through user code. Cleaned up in `ContextTracker.cleanup()`.

---

### End-to-End Flow

```
setup_claude_agent_sdk(project="my-project")
  initializes Braintrust logger
  replaces ClaudeSDKClient, query, SdkMcpTool in the SDK module

async with ClaudeSDKClient(options=...) as client:
  # WrappedClaudeSDKClient.__aenter__ → original connect()

  await client.query("analyze this file")
  # captures prompt + start_time
  # creates RequestTracker → opens TASK "Claude Agent" span
  # wraps any registered hook callbacks
  # calls original query()

  async for message in client.receive_response():
  # pipes through _stream_messages_with_tracing()
  # AssistantMessage → opens LLM span, opens TOOL spans per ToolUseBlock
  # UserMessage      → closes TOOL spans per ToolResultBlock
  # ResultMessage    → logs usage + output, closes LLM span, closes TASK span

  # if a tool handler runs during this:
  #   _wrap_tool_handler() acquires the matching TOOL span
  #   handler body executes as child of that TOOL span
  #   hook callbacks execute as FUNCTION spans under their parent
```
