# avp-openai-agents

An AVP agent over the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
(`openai-agents`, import `agents`). The SDK owns the loop (`Runner.run_streamed`);
this package translates its stream into calls on the binding's `Recorder` and
exposes the stock entrypoint (`ping` / `describe` / `run`).

```bash
uv run --no-sync python -m avp_openai_agents.conformance run --commission c.json --out t.ndjson
uv run avp-conformance ping --agent agents/avp-openai-agents/python/avp-conformance.json
```

## What maps where

| SDK signal | AVP |
|---|---|
| raw `response.completed` / `response.incomplete` | one turn: `Recorder.assistant(content, usage, finish_reasons, duration_ms)` |
| `ResponseOutputText` / `ResponseOutputRefusal` | `TextBlock` (annotations as citations) / `RefusalBlock` |
| `ResponseFunctionToolCall` | `ToolUseBlock` keyed by `call_id`, JSON arguments parsed |
| `ResponseReasoningItem` | `ThinkingBlock` (summary text; `encrypted_content` as `signature`) |
| `ResponseUsage` | `Usage` (`cached_tokens` → `cache_read_input_tokens`, `cache_write_tokens` → `cache_creation_input_tokens`, `reasoning_tokens` → `reasoning_output_tokens`) |
| `tool_output` run item | `Recorder.tool_result(call_id, output)` |
| stream ends | `stop(converged, final_output)` |
| `ModelRefusalError` | `stop(refused)` |
| auth / rate-limit / context errors | `error(auth_error / rate_limit / context_limit)` + `stop(error)` |
| cancellation | `stop(interrupted)` |

Commission: `model` `openai/<id>` runs natively (`provider.base_url` redirects
it); another origin routes through the SDK's LiteLLM extension as
`litellm/<slug>` and needs the `litellm` extra, else the run fails fast with
`unsupported_model`. A `provider.id` other than the model's origin fails fast
with `unsupported_provider`. `system_prompt` → `instructions`; inline `skills`
are appended to the instructions (all files, SKILL.md first); inline
`mcp_servers` are dialed before `agent_started` and their tools listed with
`avp.mcp_server_id`; `output_schema` becomes a non-strict JSON output type.

No built-ins. The OpenAI Agents SDK is a framework: its agents ship with no
tools, skills, or subagents, and the descriptor mirrors that rather than adding
any (see `agents/_template/README.md` §3). Tools come from the Commission's
`mcp_servers`; every `enabled_builtin_*` list under `avp-openai-agents` must be
empty. The conformance cases that need tools or subagents report SKIP. The
adapter sets no turn cap (`max_turns=None`) and uses the SDK's MCP connect
timeout; the supervisor bounds the run.

## Known gaps

- Tool errors: the SDK's tool output item has no error flag. MCP tool failures
  that raise are flagged `is_error`; an MCP result that returns `isError: true`
  without raising is not.
- Hosted tools (web search, file search, code interpreter, hosted MCP) are not
  offered, so `server_tool_use` blocks are never produced.
