# avp-opencode

An AVP agent using pinned OpenCode 1.18.34 and the
[TypeScript SDK](../../../avp-sdk/README.md). OpenCode's native server owns the
session, model calls, tool loop, MCP clients, skills, and subagents. The adapter
maps a Commission into native configuration and sends native events through
the SDK Recorder.

The standalone npm project links the SDK by path. It requires Node 22.19 or
newer. The sandbox image uses Node 24 and installs the pinned native binary,
git, ripgrep, and CA certificates before launch. From the repository root:

```bash
make opencode-build
make opencode-check
```

With the new CLI from #86:

```bash
avp agent install opencode agents/avp-opencode/typescript/Dockerfile
avp agent ping opencode
avp agent describe opencode
avp run --agent opencode --commission commission.json
```

## Native configuration

The Descriptor surveys native tool catalogs for both editing implementations,
its built-in skill, native subagents, and providers whose SDKs are compiled into
the binary. `agent_started` records the actual model's tool catalog and each
subagent's own selected items. The SDK run plan limits those built-ins through
native tool switches and permissions. OpenCode's shared edit permission needs
a native wildcard allowance to leave `write` or `apply_patch` usable when
`edit` alone is withheld.

The Model's provider and ID select its native route. A proxy credential becomes
a stand-in API key; environment references resolve before launch, and
`model.base_url` sets the provider's native `baseURL`. The native process inherits
the launcher's environment and sandbox CA. Other provider authentication can
use its native environment variables; stored user credentials are not read.

Every server gets private config, data, state, cache, and native home directories.
It listens only on loopback, on a random port with a random password. Project
configuration, ambient plugins, external skill discovery, sharing, updates,
model-list refreshes, LSP downloads, automatic compaction, and helper agents are
disabled. Shutdown disposes native instances and stops the owned process group.
The launcher owns the working directory, OS confinement, and credentials.

A bundled plugin observes OpenCode's assembled system prompt through its native
`experimental.chat.system.transform` hook. The adapter records that prompt in
`agent_started` before allowing the model request. An explicit `system_prompt`
replaces the entire parent prompt, including native environment and skill
instructions; an empty override sends no system instructions. Child sessions
keep their native prompts. The hook communicates over an authenticated private
loopback connection, and a missing hook stops before a model request. No plugin
packages are installed at runtime.

Commissioned skill files go through native skill discovery and activation, with
support files available to native tools. Only declared skills and subagents are
permitted. Object-valued `output_schema` uses OpenCode's native structured-output
tool; its schema is included among the started tools.

Each native `step-finish` is one response with per-response cache-inclusive
input and reasoning-inclusive output. OpenCode reports its own response cost,
so the Recorder labels it `reported`. Child responses and tool results carry
their invocation's scope; their costs are not also rolled up on subagent returns.
Native timestamps provide response and tool durations. Recorder writes are
awaited, including with asynchronous sinks. Interruptions retain available
partial content with unknown usage, abort the native session, and close the run.

## Known gaps

- OpenCode's public HTTP API omits MCP tool schemas. An additional discovery
  connection lists them before the run; OpenCode's separate connection executes
  them. A discovery or native connection failure stops before a model request.
  Stateful MCP servers must tolerate that extra connection. Tool names retain
  OpenCode's native sanitization, with ownership declared in the Trajectory;
  collisions are refused.
- The API reports model usage after its tools have run. Response and child events
  are therefore delayed until that native response completes. Native timestamps
  preserve their timing. Unattributed child responses fail visibly.
- Parent tool denies also constrain native child sessions. Started child tool
  declarations include those native restrictions. Subagents use OpenCode's
  shared skill and MCP registries, declared explicitly for each child.
- Original provider response-model IDs, thought signatures, and original MCP
  structured content are not reliably exposed by these hooks. Tool text and
  base64 images are retained. Other file/image locations and native repair-tool
  calls cannot be translated and fail visibly.
- Native response costs are authoritative here; the runtime can report zero
  when it has no catalog price. The adapter cannot distinguish that from a free
  response. Live sandbox verification covers Anthropic API-key proxy
  authentication. Provider subscriptions and other authentication remain unverified.
- Commissioned skills require the native `skill` tool. Unexpected compaction
  stops visibly. The agent exposes no background subagent capability.

For local SDK changes, see [agent development](../../README.md#local-sdk-development).
