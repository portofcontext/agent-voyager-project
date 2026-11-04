# Working on AVP

AVP defines Commission, Agent Descriptor, and Trajectory specs for running and
observing agents. A supervisor sends one Commission; the runtime owns the loop
and streams its Trajectory. There is no mid-run supervisor push channel.

## References

- [README](README.md): setup and quickstart.
- [Specs](spec/v0.1/): normative wire contracts.
- [SDK guide](avp-sdk/README.md): types, Recorder, run plan, and agent command line.
- [Integration patterns](PATTERNS.md): adapting an existing runtime.
- [CLI command tree](avp-cli/COMMANDS.md) and [eval guide](avp-cli/docs/eval.md).
- [Skill](SKILL.md): agent and supervisor workflows.

## Design boundaries

- The runtime owns model calls, tools, and the loop. Adapters configure it from
  the Commission and report native events to the Recorder. Do not add agent
  base classes, driver protocols, or a second loop.
- The supervisor configures and observes. Runtime gating belongs in a managed
  MCP server the agent calls, never a supervisor-to-agent callback.
- AVP defines data shapes. Transport, orchestration, persistence, credentials,
  workspace provisioning, and OS confinement belong to the deployment.
- v0.1 permits breaking changes without compatibility shims. Update the specs,
  SDKs, cases, agents, examples, and docs together.

## Wire and SDKs

The reference tables in `spec/v0.1/` come first. Python's Pydantic models in
`avp-sdk/python/src/avp/` follow them; `make schemas` generates JSON Schemas and
`make bindings` generates TypeScript types. Never edit generated types by hand.
Build and decide shared behavior in Python first, then implement it in TypeScript.

- Import wire types from `avp.commission`, `avp.descriptor`, and `avp.trajectory`.
- A Commission has `avp_version`, `run_id`, `model`, and `prompt`. Its Model is an
  object with `provider` and `id`, plus optional endpoint and credential reference.
- Agent settings live under `agents`, keyed by the Descriptor's `agent_name`.
  Built-in allowlists are subtractive: absent allows all; `[]` allows none.
- Secrets travel as references, never secret values. MCP configuration and
  skill files travel inline.
- Events use the AVP envelope. CloudEvents and OpenTelemetry are optional
  consumer projections provided by the SDK, not the wire format.
- Each `assistant_message` represents one model response with per-response
  usage and cost. Never repeat cumulative totals. Preserve tool calls alongside
  assistant content and pair results by call ID.
- Share generic Recorder and run-plan behavior through `avp-sdk/testdata/`.
  Runtime-specific translation stays in the adapter.

## Repository layout

- `spec/v0.1/`: normative specs and generated schemas.
- `avp-sdk/{python,typescript}/`: SDKs; `data/` and `testdata/` are shared.
- `avp-cli/`: supervisor CLI, eval engine, and conformance cases.
- `agents/<name>/<language>/`: independent runtime adapters and Dockerfiles.
- `scripts/`: schema generation, SDK-data refresh, packaging checks, and skill packaging.
- `testing/mcp/`: shared MCP fixtures.

Each Python project has its own `pyproject.toml`, `uv.lock`, and environment;
there is no root uv workspace. Use `uv run --project <path>` or enter the project.
The CLI runs installed images through OpenSandbox with default-deny networking
and its Credential Vault. Agents implement `ping`, `describe`, and
`run --commission <path | JSON> --out <path | ->`.

## Verification

Run `make check` on every change. It checks Python formatting, lint, types and
project tests; TypeScript types, formatting and tests; shared SDK packaging;
generated TypeScript drift; and skill packaging. Tests make no paid model calls.
CLI sandbox tests run when a container engine answers; `make test-docker`
requires one. On macOS, use a `TMPDIR` shared with the container engine.

Use `make check-agent NAME=avp-<sdk>` for one Python adapter while iterating.
TypeScript adapters have `pi-check`, `gemini-cli-check`, and `opencode-check`.
Run `make schemas bindings` after wire changes and review generated diffs.

Add tests at the boundary where a change can fail: shared schema/Recorder cases
for wire behavior, native-event-to-Trajectory integration for adapters, and
subprocess or sandbox tests for launching. Report passes and capability skips
together. Native opt-in tests remain separate CI jobs where needed.

Run real-model checks after changes to wire contracts, runtime integration,
translators, or Commission-to-runtime configuration, using the affected adapter's
README. Documentation, test-only changes, and internal refactors without
observable wire impact do not require paid runs.

## Documentation and releases

Keep change notes in `CHANGELOG.md`. Keep the README concise and link to the
existing guides. Do not duplicate normative specs or put test counts in docs.
Avoid em dashes in prose.

SDKs and the CLI publish as GitHub prereleases. Follow
[the release guide](docs/releases/README.md): update the package version and
lockfile, run `make check`, and push the clean branch before `make release-sdk-python`,
`make release-sdk-typescript`, or `make release-cli`. Tags trigger artifact builds
and clean-install tests before publication. Publish the SDK before packages that
depend on it. Refresh shared provider snapshots with `make sdk-data` before an
SDK release. Never overwrite a published version.
