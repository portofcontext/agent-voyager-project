# avp-codex

An AVP observer over the native [Codex app-server](https://developers.openai.com/codex/app-server).
Codex owns the loop and tool execution. This package translates its JSON-RPC
notifications into the Python Recorder; it does not implement a second loop.

Requires `codex-cli 0.162.1` on PATH and `OPENAI_API_KEY`. The exact runtime pin
is deliberate: per-inference raw events are experimental. Other versions fail
before inference until their event contract is verified.

```bash
uv sync --all-packages
uv run --no-sync python -m avp_codex.conformance run --commission c.json --out t.ndjson
uv run avp-conformance ping --agent agents/avp-codex/python/avp-conformance.json
AVP_TEST_CODEX=1 uv run --no-sync pytest agents/avp-codex/python/tests/test_native.py
```

## Mapping

| Native signal | AVP |
|---|---|
| `rawResponseItem/completed` | assistant content, reasoning, function/custom tool calls, and paired tool outputs |
| `rawResponse/completed` | one assistant inference with delta usage, including cache and reasoning tokens |
| `item/completed` for tools | native tool failure status and MCP structured result |
| `thread/tokenUsage/updated` | ignored: cumulative usage would double count |
| `turn/completed` | converged, error, or interrupted according to the native status |

One Commission starts an ephemeral Codex thread and one user turn. That turn
may contain multiple model calls and tool calls. Commission `thread_id` is
attribution, not a request to resume a persisted Codex conversation.

`model` requires `openai/<model>`; `provider.base_url` redirects the Responses
endpoint. `system_prompt` becomes base instructions; inline skills append all
files to developer instructions. `output_schema` becomes `outputSchema`.
Commission MCP servers are configured in the native runtime, enumerated before
`agent_started`, and their tools carry `avp.mcp_server_id`. Credentials remain a
deployment concern, as with the other adapters.

The child gets a temporary CODEX_HOME and does not use the user's login or
config. Discovered host/repository skills are disabled; only Commission skills
are advertised. Workspace is `AVP_WORKSPACE` or the current directory. Native
workspace-write sandboxing remains enabled; interactive requests receive a
protocol error because AVP has no mid-run supervisor callback.

## Supported profile and limits

The profile offers native shell, patch, image-viewing, user-input, and MCP
resource tools. Codex selects the applicable native tools from model metadata;
the descriptor lists the available surface. Multi-agent delegation, goals,
apps, plugins, and web search are disabled. This is a single-agent, API-key integration,
not support for every feature of the OpenAI suite.

Codex cannot enforce arbitrary built-in tool allow-lists. In particular,
`request_user_input` remains exposed when other tools are disabled. The adapter
rejects an unrepresentable allow-list, including `[]`, before inference with
`commission_collision`. Consequently it does **not** pass the complete v0.1
conformance suite: the empty-allow-list case is a known failure, not a skip.

Missing raw response boundaries, malformed arguments, unknown output item types,
and unmatched tool results fail the run instead of fabricating usage or success.
Native protocol changes require updated translation and native seam tests.
The scripted native test uses a local model endpoint and real MCP process;
it spends no API credits. Live conformance remains a separate check.
