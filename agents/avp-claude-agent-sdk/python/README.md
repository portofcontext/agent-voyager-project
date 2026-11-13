# avp-claude-agent-sdk

An AVP agent over the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/python).
Claude Code owns the model calls and tools. This package maps a Commission into
native options and reports the run through the AVP SDK's Recorder.

The standalone project pins Claude Agent SDK `0.2.87`. The image installs
Claude Code `2.1.303` and Node 24 when built, with Python 3.14 as the agent runtime.

From this project:

```sh
uv sync
uv run avp-claude-agent-sdk-cli ping
uv run avp-claude-agent-sdk-cli describe
uv run avp-claude-agent-sdk-cli run --commission c.json --out t.ndjson
```

The command follows the [SDK command line](../../../avp-sdk/README.md#the-agent-command-line).
The Descriptor's native tools, skills, and subagents are captured from the pinned
CLI. Commission allowlists use the SDK's run plan and configure Claude's native
filters. The launcher supplies the workspace, native state directory, and OS
confinement; each Commission starts a new session.

## Sandbox

Install the built-in agent with the CLI:

```sh
avp agent install claude-code
avp agent ping claude-code
avp agent describe claude-code
avp run --agent claude-code --commission c.json
```

The image bundles the SDK and shared provider data. It starts with its own
`CLAUDE_CONFIG_DIR`, disables nonessential traffic and update checks, and uses
noninteractive permissions inside OpenSandbox's confinement. No runtime
installation or model-list fetch is required. Claude Code's native HTTPS client
uses the launcher's CA settings for credential-proxy connections.

## Commission mapping

- `model.provider` must be `anthropic`; `model.id` goes to Claude unchanged.
  `base_url` selects an Anthropic-compatible gateway.
- `system_prompt` replaces Claude's system prompt. Without an override, the
  native Claude Code preset is used. Commissioned skill files are appended to
  the instructions, SKILL.md first; host settings and skills are not loaded.
- Stdio and HTTP MCP servers use Claude's own clients. Their native names and
  connection statuses are reported before response events. Proxy headers are
  omitted so the sandbox proxy can add them; environment references are resolved
  inside the agent.
- `output_schema` uses native structured output and is validated before a
  `converged` stop. Invalid output reports `output_invalid`.
- Raw message boundaries produce separate model responses. Anthropic cache
  reads and writes are included in AVP input tokens; session totals are not
  added again. Eager tool results and child events wait for their parent
  response's completion so its usage stays attached to a single response.
  Foreground and background subagent responses retain their parent invocation
  IDs. When a foreground child exposes only an aggregate Agent result, its
  cache-inclusive usage is recorded there; it is not added again when individual
  child responses were recorded. Opaque background children can omit the token
  breakdown; their usage remains unknown instead of being inferred from a total.

## Authentication

| Method | Support |
|---|---|
| API key with `model.credential.proxy` | Sends a stand-in API key for the sandbox proxy to replace |
| API key with `model.credential.env` | Reads the named variable; the agent sees the key |
| `ANTHROPIC_API_KEY`, without a credential reference | Native environment authentication; use launcher `--env` |
| `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` | Native gateway bearer authentication through `--env`; the agent sees the token |
| `CLAUDE_CODE_OAUTH_TOKEN` | Native `--env` only; subscription credentials have not been verified. The API-key proxy does not implement this auth method |
| `avp vault login` for a Claude subscription | Unsupported; that command handles MCP OAuth and does not log in to or refresh Claude subscription tokens |
| Bedrock, Vertex, Foundry | Outside this agent's Anthropic API profile; their native backend switches are disabled |

## Known gaps

- Responses are reported when complete. Context compaction fails visibly
  because its response accounting has not been established.
- The native default system prompt is model-dependent and is not exported;
  only a Commission's replacement is reported in the ATIF effective configuration.
- Claude's MCP status API does not export input schemas. Those tools use the
  spec's object-schema fallback, preserving the descriptions and annotations
  the SDK does expose.
- Tool search is disabled so commissioned MCP tools are available directly.
- Task notifications report background-agent completion. An agent still
  running when the native turn ends is reported as abandoned by the Recorder.
- The legacy instrumentation subclass, monkeypatch API, and resumable session
  helpers are removed. The agent command line is this package's entrypoint.

## Development

```sh
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
AVP_TEST_CLAUDE=1 uv run pytest tests/test_native.py
uv run python scripts/capture_catalog.py
```

Native tests and catalog capture require the pinned `claude` command on PATH
(or `AVP_CLAUDE_CLI`) and use local model endpoints without API credits.
Regenerate the catalog and run them when updating the native CLI pin.

For local SDK changes, see [agent development](../../README.md#local-sdk-development).
