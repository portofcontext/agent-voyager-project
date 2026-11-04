# avp-deep-agents

An AVP agent using [LangChain Deep Agents](https://github.com/langchain-ai/deepagents).
The native graph owns model calls, tools, and delegation. The adapter maps a
Commission into its configuration and sends native callbacks through the
[Python SDK Recorder](../../../avp-sdk/README.md).

The project has its own lockfile and installs the Python SDK beta from GitHub.
From this directory:

```bash
uv sync --locked
uv run avp-deep-agents-cli ping
uv run avp-deep-agents-cli describe
uv run avp-deep-agents-cli run --commission commission.json --out trajectory.ndjson
```

Install the built-in agent with the CLI:

```bash
avp agent install deep-agents
avp agent ping deep-agents
avp agent describe deep-agents
avp run --agent deep-agents --commission commission.json
```

Installation requires the SDK's versioned `ping` response from #86. The image
uses Python 3.14, installs its dependencies at build time, and disables LangSmith
tracing during runs. It needs no startup downloads or model-list refreshes.

## Native capabilities

The Descriptor reads tools from the native graph: `ls`, `read_file`, `write_file`,
`edit_file`, `delete`, `glob`, `grep`, `execute`, and `task`. It declares the native
`general-purpose` subagent with its own filesystem and shell tools. Commissioned
MCP tools are connected through LangChain's MCP clients, with their actual names
and schemas reported in `agent_started`.

The local shell backend uses the launcher's working directory. Virtual file
paths such as `/notes.txt` resolve under that directory; shell commands run there
with the inherited environment. The launcher provides OS confinement.

Models use `openai`, `anthropic`, or `google` provider IDs. Deep Agents' provider
profile configures the native chat model, including OpenAI's Responses API.
Model credentials accept proxy stand-ins or environment references; `base_url`
is forwarded to the provider client. HTTP MCP proxy headers are omitted so the
sandbox proxy can supply them, while environment references are resolved locally.

The run plan hides disabled parent tools and rejects calls to them. Turning off
`general-purpose` also hides `task`. The subagent has its own declared tools;
parent tool filters do not remove them. Inline skill files become instructions,
as in the Pydantic AI reference agent. An explicit `system_prompt` replaces the
parent harness instructions. JSON Schema output uses native provider structured
output and is validated before the run reports success.

Each completed native chat-model call produces one `assistant_message`, including
child calls under their subagent invocation ID. Cache counts are already included
in LangChain input usage. Child responses are recorded individually, without
adding a second subagent usage total. Tool results preserve MCP error status and
structured content when available.

## Known gaps

- Native model profiles can change prompts, descriptions, or add tools. The
  Descriptor captures the default graph's built-ins; models that introduce extra
  tool names are refused. Profile-specific prompt expansions are not enumerated
  in the Descriptor. An explicit Commission prompt overrides parent expansions.
- Native context compaction is not representable by this adapter yet. A
  summarization model request stops the run with an error before that request
  executes, rather than reporting it as a conversation response.
- Text, normalized reasoning, base64 images, tool calls, and provider refusals
  are translated. Other model content kinds stop the run with an error. Other
  MCP content remains JSON text inside the tool result.
- Skills are embedded as instructions rather than exposed through native
  filesystem skill discovery. The agent ships no built-in skills or MCP servers.
- Only the default synchronous `general-purpose` subagent is exposed. Custom
  application graphs, remote/background subagents, and generic callback-handler
  integration are outside this agent's interface.
- Live sandbox verification covers Anthropic API-key proxy authentication.
  OpenAI and Google configuration is tested through their native clients; their
  live provider behavior, subscription OAuth, and managed cloud identity are
  unverified. The sandbox proxy supports fixed API-key headers.

For local SDK changes, see [agent development](../../README.md#local-sdk-development).
