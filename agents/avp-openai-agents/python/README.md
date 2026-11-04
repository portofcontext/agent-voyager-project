# avp-openai-agents

An AVP agent over the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/).
The SDK's Runner owns the loop. This package maps a Commission to its native
model and MCP configuration and sends each model response and tool result to
the AVP SDK's Recorder.

The standalone project pins OpenAI Agents `0.23.1`. From this directory:

```sh
uv sync
uv run avp-openai-agents-cli ping
uv run avp-openai-agents-cli describe
uv run avp-openai-agents-cli run --commission c.json --out t.ndjson
```

See the [SDK command line](../../../avp-sdk/README.md#the-agent-command-line).

## What it runs

- OpenAI models through the Responses API. `model.base_url` selects an
  OpenAI-compatible endpoint. Installing the `litellm` extra also offers
  Anthropic models through the SDK's native LiteLLM extension; `describe`
  reflects the installed profile.
- The framework supplies no built-in tools, skills, or subagents. Tools come
  from the Commission's stdio and HTTP MCP servers, using native SDK clients.
  The started event records the actual names and schemas the Runner exposes.
- `system_prompt` becomes the agent's instructions. Commissioned skill files
  follow those instructions, SKILL.md first.
- `output_schema` uses a native SDK output schema, with JSON Schema validation
  before `converged`. Invalid output reports `output_invalid`.
- A `proxy` model credential sends a stand-in key. An `env` reference reads its
  named variable; without one the client uses `OPENAI_API_KEY` or
  `ANTHROPIC_API_KEY`. MCP proxy headers are left for the sandbox proxy to add.
  Missing environment references fail before model calls.

The launcher supplies the working directory, credentials, and confinement.
Each Commission starts a fresh native run. SDK tracing is disabled; the image
installs dependencies when built and uses the bundled pricing snapshot offline.
Its HTTPS clients inherit the launcher's CA bundle for credential proxies.

## Sandbox

Build from the repository root with the new CLI from [#86](https://github.com/portofcontext/agent-voyager-project/pull/86):

```sh
avp agent install openai-agents agents/avp-openai-agents/python/Dockerfile --context .
avp agent ping openai-agents
avp agent describe openai-agents
avp run --agent openai-agents --commission c.json
```

The default image installs the OpenAI profile. A model credential
`{"proxy": "openai"}` uses the named vault key without exposing its value to
the agent. The LiteLLM extra must be installed when building a profile that
uses Anthropic.

## Known gaps

- Responses are reported when complete. Each raw response boundary has its own
  usage; the run's cumulative usage is not added again.
- OpenAI annotations remain in text blocks' `openai` extension. Audio, files,
  compaction, and other unsupported response item kinds fail visibly rather
  than silently losing content or usage.
- The agent does not add hosted tools or handoffs. Those are application
  features a caller would configure on its own SDK agent.
- MCP images with inline data are recorded as images. Other unsupported tool
  content is retained as JSON text.

## Development

```sh
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```

Tests drive the real Runner with its scripted model and native stdio MCP
fixture, using no API credits.
