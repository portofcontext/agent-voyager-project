# avp-gemini-cli

An AVP agent built on pinned Gemini CLI 0.63.0 and the
[TypeScript SDK](../../../avp-sdk/README.md). Gemini owns its headless session,
model calls, tool scheduler, MCP clients, skills, and subagents. The adapter
configures that runtime from a Commission and records its native events.

The standalone npm project links the SDK by path. Node 22.19 or newer is
required; the sandbox image uses Node 24 and includes the pinned `gemini` CLI,
git, and ripgrep. From the repository root:

```bash
make gemini-cli-build
make gemini-cli-check
```

With the new CLI from #86:

```bash
avp agent install gemini-cli
avp agent ping gemini-cli
avp agent describe gemini-cli
avp run --agent gemini-cli --commission commission.json
```

## Native configuration

The Descriptor reads Gemini's default headless tool, skill, and subagent
registries. Each subagent explicitly declares its own native tools, including
its completion tool. The SDK run plan applies built-in allowlists through
Gemini's native configuration. MCP servers connect once; a connection failure
stops the run before a model call. Actual native tool names and schemas, with
MCP ownership, appear in the ATIF effective configuration.

Models use provider `google`. Proxy stand-ins and environment credentials go to
Gemini's API-key client; `model.base_url` overrides its endpoint. HTTP MCP proxy
headers are omitted for the sandbox proxy to supply; environment references are
resolved before connecting. Node honors the launcher's sandbox CA.

Each run has a private Gemini home. Project agent and skill discovery paths
point into that private directory, while native tools use the launcher's working
directory. Stored OAuth state and user settings are not read. Extensions, hooks,
telemetry, model routing, automatic memory extraction, and helper model calls
are disabled. Startup needs no additional network hosts.

An explicit `system_prompt` uses Gemini's native system-file override.
Commissioned files go through its native skill loader and `activate_skill`
tool, with support files available to native filesystem tools. Skill bodies are
not embedded in the initial system prompt.

Each main model response produces one ATIF agent step, preserving native
tool-call IDs and per-response usage. Input includes cached and tool-use prompt
tokens; output includes reasoning. Shared SDK prices supply costs. The native
scheduler supplies tool results, and all Recorder writes are awaited in order.

## Known gaps

- The adapter exposes Gemini API-key authentication. Google subscription OAuth
  and Vertex authentication are outside its declared capabilities. Live sandbox
  validation covers Google API-key proxy authentication.
- Gemini CLI promotes some older Flash model IDs to newer models. The adapter
  refuses a changed main model before a provider request. Use a native model ID
  that Gemini serves unchanged; the live run used `gemini-3.5-flash-lite`.
- Gemini has no native final structured-output interface exposed here, so
  `output_schema` is refused before a model call.
- Subagents report rolled-up usage on their invocation. Their individual
  responses, expanded system instructions, and internal tool events are not exposed
  through the observed parent session. They are not also emitted as main
  responses. Native subagent model choices remain Gemini's.
- Gemini derives string-referenced subagent tools from the active parent
  registry. Parent tool allowlists therefore also constrain those child tools;
  each started subagent declaration records the resulting catalog.
- The parent stream exposes text, thought summaries, and tool calls. Provider
  thought signatures, citations, and other response content are not exposed
  by these hooks.
- MCP results retain the native model-facing content and error status. Gemini
  does not expose the original MCP structured-content field here.
- Context compaction and utility model calls cannot be represented by these
  hooks. Unexpected compaction or helper calls stop the run visibly. Missing
  response usage also fails visibly. Non-image binary tool content is unsupported.
- Native process-wide configuration makes direct library runs sequential per
  process. Use separate processes for concurrent runs. The launcher owns OS
  confinement, credentials, and workspace provisioning.

For local SDK changes, see [agent development](../../README.md#local-sdk-development).
