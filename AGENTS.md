# Working on AVP

AVP defines Commission, Agent Descriptor, Agent Start, and ATIF Trajectory specs. A supervisor sends
one Commission; the agent runs it and records a Trajectory. The supervisor cannot
send instructions during a run.

## References

- [README](README.md): setup and first run.
- [Specs](spec/v0.1/): wire contracts.
- [SDK guide](avp-sdk/README.md): types, Recorder, run plan, and agent command line.
- [Integration patterns](PATTERNS.md): adapting a runtime.
- [CLI commands](avp-cli/COMMANDS.md) and [evaluations](avp-cli/docs/eval.md).
- [Skill](SKILL.md): agent and supervisor workflows.

## Design boundaries

- The runtime owns model calls, tools, and the loop. Adapters configure it from
  the Commission and report native events to the Recorder. Do not add agent
  base classes, driver protocols, or another loop.
- The supervisor configures and observes runs. Put runtime gating in a managed
  MCP server the agent calls, never in a supervisor-to-agent callback.
- AVP defines data shapes. The deployment handles transport, orchestration,
  persistence, credentials, workspaces, and OS isolation.
- v0.1 permits breaking changes without compatibility layers. Update affected
  specs, SDKs, cases, agents, examples, and docs together.

## Wire and SDKs

The reference tables in `spec/v0.1/` define the wire contracts. Implement them in
`avp-sdk/python/src/avp/`, then run `make schemas` for JSON Schemas and
`make bindings` for TypeScript types. Do not edit generated files by hand.
Implement shared behavior in Python first, then TypeScript.

- Import wire types from `avp.commission`, `avp.descriptor`, `avp.agent_start`,
  and `avp.trajectory`.
- Use native ATIF-v1.8 from the pinned Harbor models. Recorder input types
  live in `avp.reports`; do not introduce another event wire contract.
- For Commission, Descriptor, and Trajectory rules, read the
  [specs](spec/v0.1/). Do not restate them here.
- Test shared Recorder and run-plan behavior with `avp-sdk/testdata/`.
  Keep runtime-specific translation in the adapter.

## Spec maintenance

- Each spec has these sections: Overview, Example, Reference, Rules for
  `<who>`, Out of scope.
- State each rule once, in prose, in Rules. Never put one only in an example,
  table, or note.
- Link to a rule instead of restating it. This applies to other specs, the
  spec README, guides, and this file.
- Use MUST, SHOULD, and MAY in capitals, in the RFC 2119 sense. Each rule names
  who it applies to.
- Cut fields that nobody sets or reads. Use one name per concept.
- Extend outside models (ATIF, MCP, Agent Skills). Never change them.

## Repository layout

- `spec/v0.1/`: specs and generated schemas.
- `avp-sdk/{python,typescript}/`: SDKs, with shared `data/` and `testdata/`.
- `avp-cli/`: supervisor CLI, built-in agent Dockerfiles, evaluations, and
  conformance cases.
- `agents/<name>/<language>/`: runtime adapters.
- `scripts/`: schema generation, SDK-data refresh, and packaging checks.
- `testing/mcp/`: MCP fixtures.

Each Python project has its own `pyproject.toml`, `uv.lock`, and environment.
Run commands from that directory or use `uv run --project <path>`.
The CLI runs installed images through OpenSandbox with default-deny networking
and its Credential Vault. Agents implement `ping`, `describe`, and
`run --commission <path | JSON> --out <path | ->`.

## Packages and built-in agents

The SDKs, each adapter, and the CLI are separate packages. In the repo, an
adapter uses the SDK source next to it, so you can work against unreleased
SDK changes. A published package never does.

- An adapter declares the SDK as a version range, such as
  `agent-voyager-project>=0.1.0b3`. Point it at the local SDK only through
  development settings that publishing drops: `[tool.uv.sources]` in Python,
  npm workspaces in TypeScript. Never use a `file:` dependency.
- Release the SDK version an adapter needs before releasing the adapter.
- A Dockerfile in `avp-cli` is for a released agent only. It installs a pinned
  version of the adapter's package and needs no build context.
- To run unreleased code in a container, build a temporary image in a test or
  script: write a Dockerfile there with the repo root as its context. Never add
  one to the CLI package.

## Verification

Run `make check` on every change. It checks formatting, lint, types, Python and
TypeScript tests, SDK packaging, generated TypeScript drift, and skill packaging.
It makes no paid model calls. CLI sandbox tests run when a container engine is
available; `make test-docker` requires one. On macOS, set `TMPDIR` to a directory
shared with the container engine.

For one Python adapter, use `make check-agent NAME=avp-<sdk>`.
TypeScript adapters have `pi-check`, `gemini-cli-check`, and `opencode-check`.
After wire changes, run `make schemas bindings` and review the generated diff.

Test where a change can fail:

- Wire behavior: shared schema and Recorder cases.
- Adapter behavior: native runtime events through the Recorder to a Trajectory.
- Launching: subprocess or sandbox integration tests.

Report conformance passes and capability skips together. Native opt-in tests run
in separate CI jobs.

Run real-model checks after changes to wire contracts, runtime integration,
translators, or Commission-to-runtime configuration. Follow the affected
adapter's README. Documentation, test-only changes, and internal refactors with
no observable wire changes do not require paid runs.

## Documentation and releases

Keep change notes in `CHANGELOG.md`. Keep the README concise and link to existing
guides. Do not duplicate specs or put test counts in docs. Avoid em dashes.

Follow the [release guide](docs/releases/README.md). Update the package version
and lockfile, run `make check`, and push the clean branch before using
`make release-sdk-python`, `make release-sdk-typescript`, or `make release-cli`.
Tags trigger GitHub Actions to build, test, and publish prereleases. Publish SDKs
before their dependents. Run `make sdk-data` before an SDK release. Never overwrite
a published version.
