# Integration patterns

An AVP adapter configures an existing runtime from a Commission and records its
native events as a Trajectory. The runtime calls models, executes tools, and controls the loop.
Use the SDK's [Recorder and run plan](avp-sdk/README.md) for shared behavior.

## Adapt a runtime

Start with [Pydantic AI](agents/avp-pydantic-ai/python/) for Python or
[Pi](agents/avp-pi/typescript/) for TypeScript. Each adapter has its own package,
lockfile, tests, and command line. Built-in agents' Dockerfiles live in
[`avp-cli/src/avp_cli/agents/dockerfiles/`](avp-cli/src/avp_cli/agents/dockerfiles/).

1. Describe the runtime's built-in tools, MCP servers, skills, subagents, and
   supported models. Leave out capabilities the runtime does not provide.
2. Configure the runtime from the Commission and SDK run plan: model,
   credentials, system prompt, output schema, MCP servers, skills, and allowlists.
3. Send native responses and tool results to the Recorder. Document unsupported
   capabilities and unavailable event data in the adapter's README.
4. Expose `ping`, `describe`, and `run` through the SDK's agent command line.
   `ping` must work without initializing the runtime.
5. Bundle the runtime and its dependencies in the image. Disable startup
   downloads, telemetry, and model calls the adapter cannot record.

## Translate native events

- Record one ATIF agent step per model response, including its content,
  tool calls, and final usage.
- Convert cumulative usage to per-response deltas. Include cache and reasoning
  tokens as the spec defines them. Count subagent usage once.
- Match tool results to calls by ID, including parallel calls and errors.
  Keep MCP structured results when the runtime exposes them.
- Attach child responses and tool events to their subagent invocation.
  Record child cancellations and failures even when the parent recovers.
- Stop the runtime on cancellation and close the Trajectory with the matching
  reason. Fix invalid Recorder reports; do not suppress their errors.

Follow the [Trajectory spec](spec/v0.1/trajectory.md) for ATIF fields and delivery.
Adapter integration tests should pass native runtime events through the Recorder
and check the resulting Trajectory.

## Launch and verify

The launcher sets up the workspace, environment, credentials, and OS isolation.
The CLI starts a fresh OpenSandbox sandbox for each command. Commissions refer to
secrets by name; the Credential Vault adds proxy credentials to outgoing requests.

From the repository root, build and check an adapter using its Dockerfile and
repository root as the build context:

```sh
uv run --project avp-cli avp agent install pd \
  avp-cli/src/avp_cli/agents/dockerfiles/pydantic-ai.Dockerfile \
  --context .
uv run --project avp-cli avp agent describe pd
uv run --project avp-cli avp conformance check --agent pd
```

For SDK changes, see [local SDK development](agents/README.md#local-sdk-development).
Use `avp conformance list` to see which rules have cases. Report passes and skips
together, and identify rules with no coverage. Also run the adapter's native
integration tests and real-model checks.
