# Integration patterns

An AVP adapter configures an existing runtime from a Commission and reports its
native events as a Trajectory. The runtime owns model calls, tools, and the loop.
The [SDK guide](avp-sdk/README.md) describes the shared Recorder and run plan.

## Adapt a runtime

Use a migrated adapter as a reference: [Pydantic AI](agents/avp-pydantic-ai/python/)
for Python or [Pi](agents/avp-pi/typescript/) for TypeScript. Each project has its
own package file, lockfile, tests, installed command, and Dockerfile.

1. Describe the runtime's actual built-in tools, MCP servers, skills, subagents,
   and supported models. Frameworks with no built-ins declare none.
2. Apply the SDK's run plan through the runtime's native configuration. Honor
   model and credential references, prompt replacement, output schema, MCP
   connections, skill files, and the per-agent allowlists.
3. Report native responses and results through the Recorder. Document data and
   capabilities that the runtime cannot expose in the adapter's Known gaps.
4. Expose `ping`, `describe`, and `run` through the SDK's agent command line.
   Keep runtime initialization out of `ping`.
5. Build the runtime and all dependencies into the image. Avoid startup
   downloads, telemetry, and helper model calls outside the observed loop.

## Translate native events

- Record one `assistant_message` per model response. Preserve all of its content
  and tool calls, and use the final usage for that response.
- Convert cumulative runtime usage to deltas before reporting it. Include cache
  and reasoning tokens as the spec defines them; never count child usage again
  as parent usage.
- Match tool results to calls by ID, including parallel calls and error results.
  Preserve MCP structured results when the runtime exposes them.
- Scope child responses and tools to the subagent invocation that owns them.
  Preserve cancellation and failure outcomes, even when the parent recovers.
- Stop the runtime on cancellation and close the Trajectory with the appropriate
  reason. Invalid adapter reports are bugs; don't suppress Recorder errors.

The [Trajectory spec](spec/v0.1/trajectory.md) defines the required events and
ordering. Shared SDK cases test the Recorder; adapter integration tests must also
exercise native events through it.

## Launch and verify

The launcher owns workspaces, environment, credentials, and OS isolation.
The CLI installs an image, checks `ping` and `describe`, and starts a fresh
OpenSandbox sandbox for each command. A Commission contains references to secrets;
the Credential Vault injects proxy credentials outside the agent.

Build an adapter from the repository root while its SDK dependency is local:

```sh
uv run --project avp-cli avp agent install pd agents/avp-pydantic-ai/python/Dockerfile --context .
uv run --project avp-cli avp agent describe pd
uv run --project avp-cli avp conformance check --agent pd
```

Report conformance passes and skips together. The case inventory is still growing;
a passing check does not establish coverage for rules with no cases. Use native
integration tests and the adapter README's real-model checks as well.
