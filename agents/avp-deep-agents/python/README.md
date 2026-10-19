# avp-deep-agents

An AVP agent over [LangChain Deep Agents](https://github.com/langchain-ai/deepagents)
(`deepagents`, built on LangChain and LangGraph), and `AvpCallbackHandler`, a
LangChain callback handler that records any LangChain or LangGraph run as an AVP
trajectory. Deep Agents owns the loop (`create_deep_agent(...).ainvoke`); the
adapter maps the Commission onto it and attaches the handler, which reports to
the binding's `Recorder`. The stock entrypoint provides `ping` / `describe` / `run`.

```bash
uv run --no-sync python -m avp_deep_agents.conformance run --commission c.json --out t.ndjson
uv run avp-conformance check --agent agents/avp-deep-agents/python/avp-conformance.json \
  --suite v0.1 --model openai/gpt-5-mini
```

## What ships

The descriptor is read off an agent built exactly as runs build it, so it
mirrors the pinned `deepagents` rather than a hand-kept list:

- Tools: `ls`, `read_file`, `write_file`, `edit_file`, `delete`, `glob`, `grep`
  (the filesystem tools) and `execute` (shell), all on a `LocalShellBackend`
  rooted at the working directory, and `task`, which runs a subagent.
- Subagents: `general-purpose`, the default Deep Agents adds behind `task`.

Files land in the real workspace. Paths are virtual (`/notes.txt` is
`<cwd>/notes.txt`, and `..` cannot leave it); `execute` runs in the workspace
with the process environment, unconfined, as Deep Agents' local shell does.
The launcher's sandbox is the isolation boundary. Deep Agents 0.7 no longer
adds `write_todos` by default; it appears only under the harness profile Deep
Agents registers for Codex models, so the descriptor does not declare it.

## What maps where

| Commission | Deep Agents |
|---|---|
| `model` `openai/<id>`, `anthropic/<id>`, `google/<id>` | `init_chat_model` (`openai`, `anthropic`, `google_genai`) with Deep Agents' provider profile, so OpenAI runs on the Responses API; Google models make at most three attempts, like the other SDKs |
| `provider.base_url` | the chat model's `base_url` |
| `provider.id` other than the model's origin, any other origin | fail fast: `unsupported_provider` / `unsupported_model` |
| `system_prompt` | `create_deep_agent(system_prompt=...)`; Deep Agents appends its harness profile's suffix for the models it has one for (Claude Haiku 4.5, Sonnet 4.6, Opus 4.7, the Codex models) |
| `prompt` | the first user message |
| `output_schema` | `response_format` (LangChain picks provider-native or tool-based structured output); the result is `agent_stopped.output` |
| `skills` | Deep Agents' `SkillsMiddleware`: files written to a private directory mounted at `/.avp-skills/`; the model sees each skill's name and description and reads `SKILL.md` with `read_file` |
| `mcp_servers` (stdio, http) | `langchain-mcp-adapters` sessions held for the run; tools named `mcp__<server>__<tool>`, listed with `avp.mcp_server_id`; a server that fails to connect is `mcp_connect_failed` and the run continues |
| `enabled_builtin_tools` / `enabled_builtin_subagents` | hidden from the model and rejected if called anyway (a `tool_returned` error), in the main agent and the general-purpose subagent; hiding `general-purpose` hides `task` |

| LangChain callback | AVP |
|---|---|
| `on_llm_end` (one chat-model call) | one turn: `Recorder.assistant(content, usage, model, finish_reasons, duration_ms)` |
| `AIMessage.content_blocks` text / reasoning | `TextBlock` / `ThinkingBlock` (Anthropic signatures kept) |
| `AIMessage.tool_calls` | `ToolUseBlock` keyed by the call id |
| `usage_metadata` | `Usage`: `input_tokens` (cache included), `cache_read`, `cache_creation` (or the TTL split), `reasoning` |
| `on_tool_end` / `on_tool_error` | `tool_result(call_id, ...)`, `is_error` from `ToolMessage.status` or the exception |
| `task` tool start / end | `subagent_start` / `subagent_result` with the child's spend as `avp.subagent.usage` |
| `on_llm_error` | nothing: a failed attempt is not a turn |
| run ends | `stop(converged, output)`; a refusal is `stop(refused)` |
| auth (incl. Gemini's 400 `API_KEY_INVALID`) / rate limit (incl. `insufficient_quota`, and a 503 / 529 overload once retries are spent) / context overflow | `error(auth_error / rate_limit / context_limit)` + `stop(error)` |
| SIGINT / SIGTERM | `stop(interrupted)` |

**Why callbacks, not `astream_events`.** A chat model's callback run is exactly
one inference: `on_llm_end` carries that call's complete `AIMessage` with its own
`usage_metadata`, so turns need no chunk merging, and a failed attempt ends in
`on_llm_error` with nothing to retract. `run_id` / `parent_run_id` give the run
tree directly, which is how child calls are told apart from the parent's, and
tool callbacks carry the `tool_call_id`. `astream_events` is built from the same
callbacks; it would add an event loop and chunk reassembly without adding
information.

## Recording your own LangGraph app

The handler needs only a started `Recorder`; it does not depend on Deep Agents:

```python
from avp.pricing import load_default_prices
from avp.recorder import Recorder
from avp.trajectory import StopReason
from avp_deep_agents.callbacks import AvpCallbackHandler

rec = Recorder(sink, run_id="r1", provider="openai", prices=load_default_prices())
await rec.prelude(commission, descriptor)
await rec.start(request_model="openai/gpt-5-mini", prompt=prompt, tools=tool_decls)
handler = AvpCallbackHandler(rec, request_model="openai/gpt-5-mini")
try:
    result = await graph.ainvoke({"messages": [("user", prompt)]}, {"callbacks": [handler]})
    await rec.stop(StopReason.converged, result["messages"][-1].text)
except asyncio.CancelledError:
    await rec.stop(StopReason.interrupted)
    raise
```

- Run the graph asynchronously (`ainvoke` / `astream`). Sync tools are fine:
  LangGraph runs them on worker threads and the handler hands their callbacks
  back to the run's event loop.
- Pass `subagent_tool=` if your graph delegates through a tool other than `task`.
- A tool call answered without a tool run (rejected by middleware, or naming an
  unknown tool) is paired from the `ToolMessage` the next model call or the
  root run's output carries.
- Recording errors raise into the run (`raise_error = True`): they are bugs.

## Gaps

- Subagent turns are rolled up, not nested. The child's calls are visible, and
  the spec prefers them as events under the frame span, but the Recorder parents
  every turn under the agent span. The child's spend arrives as
  `avp.subagent.usage` (turns, input and output tokens, cost when every call is
  priced); its tool calls stay out of the parent trajectory.
- MCP `auth` and `provider.credential` handles are not resolved here; the
  launcher injects credentials into the environment.
- `enabled_builtin_skills` / `enabled_builtin_mcp_servers`: the agent ships
  none, so any listed name is a `commission_collision`.
- A Commission skill needs `name` and `description` frontmatter: Deep Agents'
  loader skips a `SKILL.md` without them. Skills are read with `read_file`, so
  hiding `read_file` also hides skill bodies.
- An MCP transport failure during a call (the server dies mid-run) is not a
  tool error in LangGraph's `ToolNode`; it ends the run as `agent_crash`.
- The allow-list hides tools the way Deep Agents' own `excluded_tools` does: the
  tools stay registered and a call is rejected before it runs.
