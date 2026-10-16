# Integration patterns

AVP adapters connect existing agent runtimes to supervisors. The runtime owns
model calls, tool execution, and the agent loop. The adapter translates a
Commission into runtime configuration and reports native events to the Recorder.

## Adapt an agent runtime

An adapter supplies three pieces:

- **Commission mapping:** configure the runtime's model, prompts, managed MCP
  servers, skills, output schema, and built-in allowlists.
- **Event translation:** report native model responses, tool results, subagents,
  and completion through the shared Recorder. Preserve per-response usage;
  the Recorder handles trajectory ordering, spans, pairing, and cost.
- **Descriptor:** describe the capabilities and built-ins the runtime exposes.

The stock entrypoint supplies `ping`, `describe`, and `run --commission --out`.
Start with the [adapter template](agents/_template/README.md).

The [Claude Agent SDK adapter](agents/avp-claude-agent-sdk/python/) exposes a
`ClaudeSDKClient` subclass:

```python
async with AVPClaudeSDKClient(commission=commission, sink=sink) as client:
    await client.query(commission.prompt)
    async for message in client.receive_response():
        ...  # application message handling
```

Other adapters observe [Goose](agents/avp-goose/rust/),
[OpenAI Agents](agents/avp-openai-agents/python/), and
[Codex](agents/avp-codex/python/). Each adapter documents the native events it
uses and the capabilities it can represent.

## Conformance

Run `avp-conformance check --agent <manifest> --suite v0.1` against a real model.
Use `--model <origin>/<model>` to override the fixture model. The suite checks
event content, lifecycle, accounting, and span structure, including a managed
MCP invocation, result, and subsequent model response.

Cases requiring an undeclared optional capability report SKIP. Report those
skips alongside passes; see the [coverage notes](avp/core/conformance/src/avp_conformance/COVERAGE.md).

## Supervisors

Supervisors construct Commissions and consume trajectories. The local
[AVP CLI](avp-cli/) runs agents and compares Commission variants over datasets.
Agent adapters live under `agents/`; supervisor code lives separately.

## Launch context

The launcher owns workspace provisioning, credentials, native SDK config/state
paths, and cleanup. Adapters inherit that context; they do not create a private
home, override a supplied state directory, or delete caller-owned state. This is
a deployment convention, outside the Commission and trajectory wire formats.

The CLI and conformance runner share `avp.launch`: each invocation gets a fresh
home, workspace, and native state directories for **all** adapters. Container
runs use the mounted workspace. Host conformance runs use a scratch workspace.
`CODEX_HOME`/`CODEX_SQLITE_HOME`, `CLAUDE_CONFIG_DIR`, `GOOSE_PATH_ROOT`, and XDG
paths are assigned centrally. Explicit manifest environment settings override
these defaults, so callers can deliberately retain native state. Only the
launcher's temporary root or container is cleaned up.

Source commands bootstrap in the manifest directory. The stock Python and Rust
entrypoints enter `AVP_WORKSPACE` before `describe` or `run`, so SDKs and MCP child
processes inherit the same working directory. Relative CLI input/output paths
still resolve against the launch directory. Direct library calls inherit the
caller's working directory and native environment unchanged. Persistent SDKs
with process-global configuration, such as Goose, need that context established
before SDK initialization; use a separate process for a different context.

Credential injection and OS confinement remain launcher responsibilities. Host
conformance inherits provider environment variables; the CLI container launcher
selects credentials for the commissioned provider or routes through its broker.
A launcher redirects a provider with `<PROVIDER>_HOST`, the root standing in for
the provider's origin, and `<PROVIDER>_BASE_URL`, that root plus the API's
version path (`OPENAI_BASE_URL=http://broker/llm/openai/v1`). Adapters route
every model call through them, translating to the SDK's own setting when it
reads neither; `avp-conformance check` meters the traffic to verify it.
Fresh state directories are not a security sandbox. Host launchers preserve uv
and Rust build caches so bootstrapping does not require reinstalling toolchains.
SDK-specific Commission mapping and tool/skill restrictions remain in adapters.
