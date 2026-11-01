# avp-pydantic-ai

An AVP agent over [Pydantic AI](https://ai.pydantic.dev). Pydantic AI runs the
loop; this package turns each run into a Trajectory with the SDK's Recorder.

```sh
uv run avp-pydantic-ai-cli ping
uv run avp-pydantic-ai-cli describe
uv run avp-pydantic-ai-cli run --commission c.json --out t.ndjson
```

The command line is the SDK's agent command line; see the
[SDK README](../../../avp-sdk/README.md#the-agent-command-line).

## What it runs

- **Models:** at `anthropic`, `google`, and `openai`, as `describe` lists. A
  Commission for another provider is refused.
- **Tools:** only those of the Commission's MCP servers, stdio or HTTP. Pydantic
  AI agents come with no tools, skills, or subagents, so neither does this one.
- **Skills:** added to the instructions, SKILL.md first, since Pydantic AI has
  no skill loader.
- **`output_schema`:** answered through Pydantic AI's output tool.
- **Credentials:** a `proxy` credential sends a stand-in key for the proxy to
  replace; an `env` credential reads that variable; without one, the provider's
  client reads its own, such as `ANTHROPIC_API_KEY`.

## Code

| Module | What it does |
|---|---|
| `cli.py` | The command line; loads Pydantic AI only for `run` |
| `descriptor.py` | The Agent Descriptor and the providers it runs |
| `commission.py` | Commission to Pydantic AI: model, instructions, MCP toolsets |
| `agent.py` | The run: Pydantic AI's message history to Recorder calls |
| `translate.py` | Pydantic AI messages to AVP content, usage, and error codes |

## Known gaps

- Responses are reported when complete, not streamed.
- Pydantic AI's native tools (web search, code execution) are not offered.
- Compaction, speech, and files that aren't images have no AVP content block,
  so they are left out of `assistant_message`.

## Development

```sh
uv sync
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```
