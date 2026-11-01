# avp-pydantic-ai

An AVP agent over [Pydantic AI](https://ai.pydantic.dev) (`pydantic-ai-slim`,
import `pydantic_ai`). Pydantic AI owns the loop (`Agent.iter`); after each
node of its run graph this package reads what the node added to the message
history, reports it to the binding's `Recorder`, and exposes the stock
entrypoint (`ping` / `describe` / `run`).

```bash
uv run --no-sync python -m avp_pydantic_ai.cli run --commission c.json --out t.ndjson
uv run avp-conformance ping --agent agents/avp-pydantic-ai/python/avp-conformance.json
```

## What maps where

| Pydantic AI | AVP |
|---|---|
| `ModelResponse` | one turn: `Recorder.assistant(content, usage, finish_reasons, duration_ms)` |
| `TextPart` / `ThinkingPart` | `TextBlock` / `ThinkingBlock` (`signature` kept) |
| `ToolCallPart` (output tools included) | `ToolUseBlock` keyed by `tool_call_id` |
| `RequestUsage` | `Usage` (`cache_read_tokens` → `cache_read_input_tokens`, `cache_write_tokens` → `cache_creation_input_tokens`, `output_reasoning_tokens` → `reasoning_output_tokens`) |
| `ToolReturnPart` | `Recorder.tool_result(call_id, content)`; a `failed` outcome is an error |
| `RetryPromptPart` answering a call | `Recorder.tool_result(call_id, content, is_error=True)` |
| run ends | `stop(converged, output)` |
| `content_filter` finish | `stop(refused)` |
| HTTP 401/403, 429, context overflow | `error(auth_error / rate_limit / context_limit)` + `stop(error)` |
| cancellation | `stop(interrupted)` |

Commission: `model` `<origin>/<id>` runs as Pydantic AI's `<origin>:<id>` for
`openai` (Responses API), `anthropic`, and `google`; `provider.base_url`
redirects it. Another origin fails fast with `unsupported_model`, and a
`provider.id` other than the model's origin with `unsupported_provider`.
`system_prompt` → `instructions`; inline `skills` are appended to the
instructions (all files, SKILL.md first); inline `mcp_servers` are connected
before `agent_started` as `MCPToolset`s and their tools listed with
`avp.mcp_server_id`; `output_schema` becomes a `StructuredDict` output type,
which the model answers through Pydantic AI's `final_result` output tool.

No built-ins. Pydantic AI is a framework: its agents ship with no tools,
skills, or subagents, and the descriptor mirrors that (see
`agents/_template/README.md` §3). Tools come from the Commission's
`mcp_servers`; every `enabled_builtin_*` list under `avp-pydantic-ai` must be
empty. Cases requiring built-in tools or subagents report SKIP.

An MCP tool error reaches the model as a failed tool result
(`tool_error_behavior="failed"`), so it does not spend Pydantic AI's retry
budget. The adapter sets no usage limits; the supervisor bounds the run.

## Known gaps

- Native tools (web search, code execution, and the like) are not offered, so
  `server_tool_use` blocks are never produced.
- Turns are reported once a response completes, not streamed.
