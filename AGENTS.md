# Working on AVP

AVP (Agent Voyager Project) defines Commission, Agent Descriptor, and Trajectory
specs for running and observing agents. A supervisor sends one Commission; the
agent runs and streams its trajectory. There is no mid-run supervisor push channel.

## References

- [README](README.md): installation and quickstart.
- [Specs](avp/core/spec/v0.1/): normative wire contracts.
- [Integration patterns](PATTERNS.md): runtime adaptation and launch context.
- [Adapter template](agents/_template/README.md): adding a runtime.
- [CLI guide](avp-cli/README.md): Commissions, environments, and evaluations.
- [Skill](SKILL.md): agent and supervisor workflows.

## Design boundaries

- The existing agent runtime owns model calls, tool execution, and the loop.
  Adapters map Commissions into runtime configuration and report native events to
  the Recorder. Do not reintroduce agent base classes or driver protocols.
- The supervisor configures and observes. Runtime gating belongs in a managed
  MCP server the agent calls, never a supervisor-to-agent callback.
- Workspace provisioning, credentials, native SDK state, and OS confinement are
  launcher responsibilities, outside the wire specs. Adapters inherit that
  context. Stock entrypoints honor `AVP_WORKSPACE`; direct library callers own
  their working directory, state, and cleanup.
- AVP defines data shapes. Transport, multi-run orchestration, and persistence
  belong to the deployment or supervisor. In-tree agents use the file contract
  `run --commission <path> --out <ndjson>`.
- v0.1 permits breaking changes without compatibility shims or a deprecation
  cycle. Update every affected schema, binding, case, adapter, example, and doc
  together. Question unnecessary concepts rather than preserving them by habit.

## Wire conventions

- Import wire types from `avp.commission`, `avp.descriptor`, and `avp.trajectory`;
  never redefine them inline. Pydantic models under `avp/bindings/python/src/avp/`
  are the source of truth. Run `make schemas` after wire changes and
  `make bindings` to regenerate Rust and TypeScript bindings.
- Models use canonical `origin/model` slugs, never bare model names.
- Commission requires `schema_version`, `run_id`, and `model`. Inline MCP server
  configuration and skill content travel on the Commission. Built-in allowlists
  are subtractive: absent exposes all, `[]` exposes none.
- Preserve compatibility with CloudEvents 1.0, OTel span identification,
  MCP, and Agent Skills. AVP attributes use `avp.*`; the `gen_ai.*`
  projection is for consumers, not the wire.
- Agent events use `source: avp://agent`. A trajectory opens `run_requested`,
  `agent_described`, `agent_started` and closes `agent_stopped` with a stop reason.
- Each `assistant_message` represents a model response with per-response usage
  and cost. Consumers reduce these deltas; never add cumulative runtime totals.
  Preserve tool calls alongside assistant content when translating history.

## Repository layout

- `avp/core/spec/v0.1/`: normative specs and generated JSON Schemas.
- `avp/core/conformance/`: separate harness, cases, and shared Recorder vectors.
- `avp/bindings/{python,rust,typescript}/`: wire bindings and shared helpers.
  Follow the [Python binding charter](avp/bindings/python/AGENTS.md) there.
- `agents/<name>/<lang>/`: runtime adapters, descriptors, and conformance manifests.
  Scaffold with `make new-agent NAME=avp-<sdk>` or `make new-agent-rust`.
- `avp-cli/`: the supervisor CLI. Evaluations are JSON configurations containing
  `name`, `agents`, `dataset`, `scorer`, and `commissions`; each Commission carries
  its own model. `avp eval run` and `avp run` use Docker-backed OpenSandbox containers
  with default-deny networking. Vault credentials go through the host-side broker.
- `avp/scripts/`: schema/binding generation, prices, and skill packaging.
- The repository root is the uv workspace. `make help` lists development commands.

## Verification

Run `make check` on every change. It covers format, lint, Python tests,
conformance validation and liveness, and generated-binding drift. Rust and
TypeScript tests run with `make bindings-test`; they do not make model calls.
`make test-docker` exercises real container launches and requires a Docker daemon.
While iterating on one Python agent, `make check-agent NAME=avp-<sdk>` runs its
share of `make check` without building the other agents.
`make test-fresh` runs the released Python agents' tests on fresh installs of
their wheels (newest allowed dependencies), as CI does weekly.

Add tests at the boundary where a change can fail:

- Wire requirements: conformance cases plus schema validation.
- Local behavior: the affected package's tests.
- Cross-component behavior: a integration test, such as SDK events to Recorder output,
  cumulative usage to per-response accounting, subprocess trajectories, or
  workspace-relative tool execution.
- Native/provider behavior: the affected adapter's real-model conformance suite.

Features need a test crossing a relevant boundary. Do not rely on unit tests alone
for stateful translation or lifecycle behavior. Report conformance passes and
capability skips together.

Run paid conformance after changes to wire contracts, runtime integration,
translators, drop-in SDK clients, or Commission-to-SDK configuration. Use
`avp-conformance check --agent <manifest> --suite v0.1`, optionally with
`--model <origin>/<model>`, and the appropriate provider credentials.
`make conformance-check` runs Claude, Goose, and Pi with Anthropic credentials;
`make gemini-cli-check` runs Gemini CLI with `GEMINI_API_KEY`.
Documentation, test-only changes, and internal refactors without observable
wire impact do not require paid runs. When uncertain about integration impact,
run the real-model checks.

## Documentation

Keep change notes in `CHANGELOG.md`. Keep the README concise and link to existing
guides. Do not duplicate normative specs, add compatibility guides for draft
changes, or put test counts in documentation. Avoid em dashes in prose.

## Releases

Release tags trigger CI publication. Use the Makefile targets from a clean `main`
that matches `origin/main`:

- `make release-cli`: derives `pypi-v<version>` from `avp-cli/pyproject.toml`.
  The CLI wheel vendors the Python wire types.
- `make release-goose` / `make release-claude-code` / `make release-codex` /
  `make release-openai-agents` / `make release-pi` / `make release-gemini-cli` /
  `make release-deep-agents` / `make release-pydantic-ai` /
  `make release-opencode`: derive the agent tag from
  its package version, checked against `container_version` in `avp_cli.agents`.
  Update the package version and artifact pin together before publishing.
