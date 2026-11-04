# avp-codex

An AVP agent over the official [Codex Python SDK](https://learn.chatgpt.com/docs/codex-sdk).
Codex runs the loop; this package translates its events into a Trajectory with
the AVP SDK's Recorder. The SDK includes Codex CLI `0.162.1`, pinned because
response accounting uses its experimental raw events.

From this project:

```sh
uv sync
uv run avp-codex-cli ping
uv run avp-codex-cli describe
uv run avp-codex-cli run --commission c.json --out t.ndjson
```

The command line is the [SDK's agent command line](../../../avp-sdk/README.md#the-agent-command-line).
Each Commission starts a new Codex thread and user turn; `thread_id` is
attribution, rather than a request to resume a thread.

## What it runs

- **Models:** OpenAI models through the Responses API. `model.base_url` can
  select an OpenAI-compatible Responses endpoint; otherwise `OPENAI_BASE_URL`
  or OpenAI's default URL is used.
- **Tools:** native shell execution and polling, patching, image viewing, and
  MCP resource and tool discovery. `describe` lists the pinned profile;
  `agent_started` lists the tools its model and Commission actually use.
- **MCP:** the Commission's stdio and Streamable HTTP servers run through
  Codex's own clients. Their tools are listed before `agent_started`.
- **Skills:** all commissioned files are embedded in developer instructions,
  SKILL.md first. Discovered host and workspace skills are disabled.
- **Instructions:** `system_prompt` replaces Codex's base instructions.
- **Structured output:** `output_schema` goes to Codex's `outputSchema` and is
  checked before stopping with `converged`. Invalid output ends with
  `output_invalid` and `error`.
- **Credentials:** `proxy` sends a stand-in key; `env` reads the named variable;
  without either, `OPENAI_API_KEY` supplies the key. MCP proxy headers are
  omitted for the proxy to add. Native HTTPS trusts the launcher's CA bundle
  through `SSL_CERT_FILE` (or Codex's overriding `CODEX_CA_CERTIFICATE`).

The launcher supplies the working directory, native state directory, and OS
confinement. The adapter inherits that context. It requests and verifies
noninteractive approval. The Dockerfile supplies a fresh `CODEX_HOME` and
disables Codex's nested sandbox because OpenSandbox supplies confinement.
Dependencies and the runtime are installed at image build time; update checks,
analytics, feedback, apps, plugins, and web search are disabled.

## Sandbox

Build from the repository root so the SDK and shared data are available:

```sh
avp agent install codex agents/avp-codex/python/Dockerfile --context .
avp agent ping codex
avp agent describe codex
avp vault set openai
avp run --agent codex --commission c.json
```

These commands use the new CLI and its SDK ping update from [#86](https://github.com/portofcontext/agent-voyager-project/pull/86).
A model credential `{"proxy": "openai"}` uses the saved key without exposing
its value to the agent.

## Code

| Module | What it does |
|---|---|
| `cli.py` | The agent command line; loads Codex only for `run` |
| `descriptor.py` | The Descriptor and captured native tool definitions |
| `commission.py` | Run plan, model, credentials, MCP configuration, and skills to Codex |
| `agent.py` | The run and native lifecycle events to Recorder calls |
| `translate.py` | Raw responses, tool results, usage, and errors to AVP |

## Known gaps

- Responses are reported when complete. Raw response boundaries preserve
  separate model responses and per-response token counts; cumulative thread
  totals are not added to them.
- Context compaction and retries after partial output fail visibly because
  their response accounting has not been established.
- Built-in tool filtering is verified for `gpt-5-mini` and `gpt-5.5`. Other
  models with explicit tool lists are refused. Shell execution and polling
  must be allowed together. Environment access on `gpt-5.5` also needs patch;
  MCP servers need the resource helpers and, on `gpt-5.5`, tool search.
- Freeform patch input is recorded as `{"input": "..."}`. Its Descriptor uses
  an object schema because the native tool provides no JSON Schema.
- The native default system prompt is model-dependent and isn't exported;
  only a Commission's override is reported. Provider annotations are preserved
  in text blocks' `codex` extension.
- Multi-agent delegation, goals, interactive user input, apps, plugins, and
  web search are not offered by this profile.

## Development

```sh
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
AVP_TEST_CODEX=1 uv run pytest tests/test_native.py
uv run python scripts/capture_tools.py
```

The native tests and tool capture use local model endpoints, with no API
credits. They cover the bundled runtime, MCP calls, parallel calls, shell
polling, tool filtering, and a custom CA. Regenerate `tools.json` and run these
tests whenever the Codex dependency pin changes.
