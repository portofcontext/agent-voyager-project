# avp-codex

An AVP observer using the official [Codex Python SDK](https://learn.chatgpt.com/docs/codex-sdk)
(`openai-codex`). The SDK owns process management, transport, notification
routing, and typed lifecycle/tool events. Codex owns the model/tool loop.

Requires `OPENAI_API_KEY`. Installing the package also installs the SDK's
bundled Codex runtime; a separate CLI on PATH is unnecessary. SDK and runtime
are pinned to `0.162.1` because the fidelity extension described below still
uses experimental raw events.

```bash
uv sync --all-packages
uv run --no-sync python -m avp_codex.conformance run --commission c.json --out t.ndjson
uv run avp-conformance ping --agent agents/avp-codex/python/avp-conformance.json
AVP_TEST_CODEX=1 uv run --no-sync pytest agents/avp-codex/python/tests/test_native.py
```

## Mapping

| SDK notification | AVP |
|---|---|
| `rawResponseItem/completed` | assistant content, reasoning, function/custom tool calls, and paired tool outputs |
| `rawResponse/completed` | one assistant inference with delta usage, including cache and reasoning tokens |
| `item/completed` for tools | native tool failure status and MCP structured result |
| `thread/tokenUsage/updated` | contains both per-response `last` and cumulative `total`; neither is added to the usage already recorded at raw response boundaries |
| `turn/completed` | converged, error, or interrupted according to the native status |

The typed `commandExecution` item normalizes a command and its status. It does
not preserve the original function name and JSON arguments. A native seam test
covers `exec_command` followed by `write_stdin`: AVP needs both original calls,
not just the normalized command. Therefore the adapter uses the SDK's
`AsyncCodexClient` with `experimentalRawEvents` enabled. The two raw notification
methods arrive as `UnknownNotification`; their handling is isolated in the
translator. Malformed known SDK notifications fail visibly.

`rawResponse/completed` supplies the boundary for grouping raw output items
into one inference, together with that inference's usage. This avoids inferring
boundaries from tool lifecycle events or later thread usage updates. Normal
SDK usage **does** expose per-response counts through `last`; lack of such
counts is not the reason for retaining raw events. The native tests check both
`last` and `total` alongside the emitted AVP deltas.

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
workspace-write sandboxing remains enabled. The adapter requests and verifies
`approvalPolicy: never` before inference because AVP has no mid-run supervisor
callback. Explicitly commissioned MCP tools use the native `approve` policy.

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
Retries before any partial output are supported. A retry after output but before
a response usage boundary fails explicitly; it must not merge two attempts into
one inference. Context compaction is also explicitly unsupported because its
inference/usage accounting has not been established for this profile.

Native protocol changes require updated translation and native seam tests.
Scripted tests exercise the installed SDK and bundled runtime against a local
model endpoint, including real MCP calls, parallel calls, shell polling, and
retries. They spend no API credits. Live conformance remains a separate check.
