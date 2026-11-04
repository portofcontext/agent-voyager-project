# avp-pi

An AVP agent using the pinned [Pi coding agent](https://github.com/earendil-works/pi).
Pi owns the session, model calls, and tool execution. Native response and tool
results feed the [TypeScript SDK Recorder](../../../avp-sdk/README.md).

The project has its own npm lockfile and depends on `avp-sdk/typescript` by path.
It requires Node 22.19 or newer; its sandbox image uses Node 24. From the
repository root:

```bash
make pi-build
make pi-check
node agents/avp-pi/typescript/dist/src/main.js describe
```

The package exposes `avp-pi-cli` through its `bin` entry. With the new CLI from
#86, build and run its sandbox image from the repository root:

```bash
avp agent install pi agents/avp-pi/typescript/Dockerfile --context .
avp agent ping pi
avp agent describe pi
avp run --agent pi --commission commission.json
```

## Native configuration

The Descriptor reads Pi's default tools (`read`, `bash`, `edit`, `write`) and
bundled model providers from the native SDK. Commission models resolve against
that bundled catalog. Its network refresh and local model configuration are
disabled, so startup needs no additional network access.

The run plan limits built-ins using Pi's native tool allowlist. Added MCP servers
use Pi's MCP client, with one connection held for each server and native custom
tools registered in the session. `agent_started` records the active tool names
and schemas, including server ownership. Names receive a hash suffix when they collide after sanitization or exceed
the provider's name limit. A server
that cannot connect stops the run before a model call.

Model credentials accept proxy stand-ins and environment references, and
`model.base_url` overrides the native endpoint. HTTP MCP proxy headers are omitted
so the sandbox proxy can supply them; environment references are resolved before
connecting. Credentials and model caches stay in memory. The launcher supplies
the working directory, environment, CA, and OS confinement.

An explicit `system_prompt` replaces Pi's instructions through its native
`before_agent_start` hook. Inline skill files become instructions as in the
Pydantic AI reference agent. Native extensions, workspace context files, skills,
and prompt templates are not discovered. Sessions and settings are in memory;
install telemetry, cache warming, and automatic compaction are off.

Each complete model response produces one `assistant_message`; input usage
includes the cache reads and writes Pi reports separately. AVP's shared prices
supply the response cost. Native error or aborted messages are not reported as
successful responses. Recorder writes are serialized so an asynchronous sink
preserves response and tool order. MCP results retain error status and structured
content when it is an object. Signals abort the session and close its Trajectory.

## Known gaps

- Pi has no native structured-output interface exposed here. `output_schema`
  is refused before the run starts.
- The bundled model catalog limits supported model IDs. Other native Pi tools,
  extensions, custom model routes, and subagents are outside this agent's
  declared capabilities.
- Skills are embedded as instructions rather than loaded through filesystem
  skill discovery. The agent ships no built-in skills or MCP servers.
- Context compaction and deferred model responses cannot be recorded by this
  adapter. Automatic compaction is disabled; unexpected compaction or deferred
  response events stop the run with an error.
- Text, reasoning, tool calls, and base64 images are translated. Other model
  content kinds fail visibly. MCP content uses Pi's native model-facing
  conversion; resource discovery and OAuth sign-in are not provided. Non-object
  MCP structured content cannot populate AVP's object-valued field.
- Live sandbox validation covers Anthropic API-key proxy authentication.
  Other native providers and subscription OAuth remain unverified. Stored
  credentials are not read; the launcher can supply provider environment keys.
