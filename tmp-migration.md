# Migration to the v0.1 layout

Tracks the rebuild on `spec-v0.1-cleanup`. Each item is written fresh against
the specs, not migrated, and the old code is removed when its replacement
lands. Read the old code on `main` for reference only.

## Target layout

```text
agent-voyager-project/
├── spec/v0.1/                     ✅ specs moved; schemas regenerate in step 2
├── avp-sdk/
│   ├── python/                    ⬜
│   ├── rust/                      ⬜
│   ├── typescript/                ⬜
│   └── testdata/recorder/, testdata/run_plan/ ✅ (Python passes; Rust and TypeScript to come)
├── avp-cli/                       ⬜ rewritten from scratch
│   └── src/avp_cli/conformance/   ⬜ harness and cases/v0.1/
├── avp-cli-legacy/                ⬜ the old CLI, for reference only; removed before merge
├── agents/                        ⬜ one PR per agent
├── testing/mcp/                   ✅ unchanged
├── scripts/                       ⬜ avp/scripts merged with scripts/
├── proposals/                     ✅ unchanged
└── assets/                        ✅ unchanged
```

## Steps

### 1. Specs

- [x] Rewrite the specs (#78)
- [x] Move them to `spec/v0.1/` and drop the old schemas and examples (#80)

### 2. Core SDK (`avp-sdk/`)

- [x] `avp-sdk/python` is its own uv project with its own `uv.lock`; workspace members keep the old `avp/bindings/python` until they migrate
- [x] Python wire models from the spec reference tables
- [x] JSON Schemas generated into `spec/v0.1/` (`make schemas`)
- [ ] The spec documents' JSON examples as tests, against the models and the schemas
- [ ] Rust and TypeScript SDKs, checklists below
- [x] Recorder (`avp.recorder`), with shared cases in `avp-sdk/testdata/recorder/`
- [x] Run plan (`avp.utils.run_plan`): what a run uses (`agent_started`) and what it turns off, with shared cases in `avp-sdk/testdata/run_plan/`
- [x] Pricing for the Model object (`avp.utils.pricing`, snapshot in `avp/utils/data/avp_prices.json`)
- [x] Endpoints, each provider's default base URL and auth header (`avp.utils.endpoints`, snapshot in `avp/utils/data/avp_endpoints.json`), to replace avp-cli's `PROVIDER_REGISTRY` and the conformance meter's `UPSTREAMS`
- [ ] Publishing the SDK refreshes the snapshots first (`make sdk-data`)
- [ ] Scripts kept on purpose, each reviewed, moved to `scripts/`
- [ ] Remove `avp/bindings/` and `avp/scripts/`

#### Rust and TypeScript SDKs

Each SDK is one assignment, built fresh against the specs and the
[SDK README](avp-sdk/README.md), with the Python SDK as the reference. The two
lists are the same.

We are removing AI sprawl/slop, not adding it. A person should read every line of it before it merges; passing tests is not enough.
The reviewer checks that:

- Nothing is copied or ported from `avp/bindings/`, the legacy agents, or
  another SDK's code. Read the old code for reference only.
- It does what the Python SDK does and nothing more: no extra options, helpers,
  or behavior that Python doesn't have. A gap or a disagreement goes back to
  Python first.
- Every line is needed. No dead code, no speculative abstractions, no
  defensive handling of cases the spec rules out.
- Names, comments, and docs are plain and short, match the Python SDK's
  wording, and follow the language's own style. No restated code, no
  narration, no em dashes.
- Generated code is generated, never edited by hand.
- Tests cover behavior across a boundary (the shared cases, a subprocess, a
  file), not the implementation's internals.

Rust (`avp-sdk/rust`):

- [ ] Its own crate, with its tests run from the Makefile
  - [ ] Reviewed by a person
- [ ] Wire types generated from `spec/v0.1/*.schema.json`, with a make target that regenerates them and a drift check in `make check`
  - [ ] Reviewed by a person
- [ ] Recorder, passing every case in `avp-sdk/testdata/recorder/`
  - [ ] Reviewed by a person
- [ ] Commission checks, with the same refusal messages as Python (the Recorder cases pin them)
  - [ ] Reviewed by a person
- [ ] Run plan, passing every case in `avp-sdk/testdata/run_plan/`
  - [ ] Reviewed by a person
- [ ] Pricing, shipping `avp_prices.json` and loading it like Python (bundled or cache, optional `max_age`)
  - [ ] Reviewed by a person
- [ ] Agent command line: `ping`, `describe`, `run`, with the same exit codes
  - [ ] Reviewed by a person
- [ ] Its data directory added to `DATA_DIRS` in `scripts/update-sdk-data.py`
  - [ ] Reviewed by a person
- [ ] Supervisor tools, only when a Rust supervisor needs them: OpenTelemetry, CloudEvents, default base URLs
  - [ ] Reviewed by a person

TypeScript (`avp-sdk/typescript`):

- [ ] Its own npm package, with its tests run from the Makefile
  - [ ] Reviewed by a person
- [ ] Wire types generated from `spec/v0.1/*.schema.json`, with a make target that regenerates them and a drift check in `make check`
  - [ ] Reviewed by a person
- [ ] Recorder, passing every case in `avp-sdk/testdata/recorder/`
  - [ ] Reviewed by a person
- [ ] Commission checks, with the same refusal messages as Python (the Recorder cases pin them)
  - [ ] Reviewed by a person
- [ ] Run plan, passing every case in `avp-sdk/testdata/run_plan/`
  - [ ] Reviewed by a person
- [ ] Pricing, shipping `avp_prices.json` and loading it like Python (bundled or cache, optional `max_age`)
  - [ ] Reviewed by a person
- [ ] Agent command line: `ping`, `describe`, `run`, with the same exit codes
  - [ ] Reviewed by a person
- [ ] Its data directory added to `DATA_DIRS` in `scripts/update-sdk-data.py`
  - [ ] Reviewed by a person
- [ ] Supervisor tools, only when a TypeScript supervisor needs them: OpenTelemetry, CloudEvents, default base URLs
  - [ ] Reviewed by a person

### 3. Conformance (`avp-cli`)

- [ ] `avp conformance` subcommand, with no meter, sandbox, or credential swapping
- [ ] One case per agent rule, reported by rule
- [ ] Remove `avp/core/conformance/`

#### avp-cli CI

avp-cli talks to the container engine only through the Docker API, and has
only been tested on podman 6.0.1 on macOS. The sandbox tests
(`avp-cli/tests/test_agent.py`) install, ping, describe, and uninstall a test
agent, and skip when no engine answers.

- [ ] A workflow that runs avp-cli's ruff, ty, and tests on each PR
- [ ] Its sandbox tests on Linux with Docker (the GitHub runner's own)
- [ ] Its sandbox tests on Linux with rootless podman through its Docker
  socket, to settle whether rootless podman allows the egress sidecar's
  network policy
- [ ] Docker Desktop and OrbStack, checked by hand before a release, since
  GitHub's macOS runners can't run them
- [ ] `avp sandbox status` names the engine correctly on each of them

#### Open: the hosts an agent needs

`avp run` denies all network except the model's host, the Commission's HTTP MCP
servers, and `--allow-host`. It can't allow the hosts an agent needs on its
own: its built-in remote MCP servers (which `describe` may also connect to) and
anything else it calls, such as telemetry. The Descriptor's MCP server entries
leave out connection details on purpose, so avp sees only each server's `id`.

The agent needs a way to report those hosts, so avp can allow them, minus the
built-in servers a Commission turns off with `enabled_mcp_servers`. Either:

- [ ] A host field in the Agent Descriptor spec, or
- [ ] A non-spec standard, as the agent command line is, such as a field in
  `ping`'s reply or a label on the agent's image

### 4. Agents (`agents/`)

One PR per agent. TypeScript and Rust agents wait for their SDKs.

| Agent | Language | New SDK | `<agent>-cli` command | Live run | Old files removed |
|---|---|---|---|---|---|
| `avp-pydantic-ai` | Python | ✅ | ✅ | ✅ Anthropic | ⬜ |
| `_template` | Python, Rust | ⬜ | ⬜ | ⬜ | ⬜ |
| `avp-claude-agent-sdk` | Python | ⬜ | ⬜ | ⬜ | ⬜ |
| `avp-codex` | Python | ⬜ | ⬜ | ⬜ | ⬜ |
| `avp-deep-agents` | Python | ⬜ | ⬜ | ⬜ | ⬜ |
| `avp-openai-agents` | Python | ⬜ | ⬜ | ⬜ | ⬜ |
| `avp-gemini-cli` | TypeScript | ⬜ | ⬜ | ⬜ | ⬜ |
| `avp-opencode` | TypeScript | ⬜ | ⬜ | ⬜ | ⬜ |
| `avp-pi` | TypeScript | ⬜ | ⬜ | ⬜ | ⬜ |
| `avp-goose` | Rust | ⬜ | ⬜ | ⬜ | ⬜ |

- **New SDK:** its own project on `avp-sdk`; `ping`, `describe`, and `run` work.
- **`<agent>-cli` command:** the command line is installed as a command, to be
  the image's entrypoint.
- **Live run:** one real model call through the command line.
- **Old files removed:** once avp-cli decides how agent images are built, remove
  what the old tools still read: `avp-conformance.json`, its `Makefile` lines
  (manifest variable, `make conformance`, `TEST_PKGS`), its entry in the legacy
  CLI's `agents.json`, `[tool.avp.release]`, and any `avp-conformance` example in
  its README.

### 5. Split the uv workspace into separate projects

The SDK, avp-cli, and each agent are released separately, so each gets its own
`pyproject.toml`, `uv.lock`, and `.venv`, using the SDK by path. An agent's own
lock then produces its release `requirements.txt`.

- [x] `avp-sdk/python`
- [ ] `avp-cli`
- [ ] Each Python agent, in its agent PR
- [ ] Remove the root workspace, and run each project's checks from the Makefile

### 6. Before `spec-v0.1-cleanup` merges to `main`

- [ ] Root docs cut down: `AGENTS.md`, `README.md`, `SKILL.md`, `PATTERNS.md`, `MAINTAINERS.md`
  - `AGENTS.md` still describes the old wire: CloudEvents and OTel compatibility, `source: avp://agent`, `avp.*` attributes, `schema_version`, `origin/model` slugs, and `avp/bindings` as the source of truth
- [ ] `make check` passes
- [ ] `avp-cli-legacy/` removed
- [ ] `tmp-*` files removed

### 7. Beta release: `0.1.0b1`

The Python SDK and each migrated agent go to PyPI as `0.1.0b1`, a beta of
`0.1.0`, so `0.1.0` stays free for the final release. `pip install` skips
betas unless the version is pinned or `--pre` is given.

Clear the old releases first:

- [ ] Delete the old GitHub releases and their tags (`agent-<name>-v*` and
  `pypi-v*`). The legacy CLI (`avp-cli` 0.5.0 and earlier on PyPI) downloads
  agent releases from them, so deleting them breaks it.
- [ ] Yank `avp-cli` 0.1.0 to 0.5.0 on PyPI. PyPI never reuses a version, so the
  new CLI's first release is above 0.5.0, such as `0.6.0b1`.
- [ ] Remove the old release workflows: `release-<agent>.yml`,
  `agent-release.yml`, and `release-pypi.yml`.

Then publish:

- [ ] One release workflow per package, run by its tag (such as
  `sdk-python-v0.1.0b1` or `avp-pydantic-ai-v0.1.0b1`), publishing to PyPI with
  trusted publishing
- [ ] SDK: `make sdk-data`, version `0.1.0b1`, published as
  `agent-voyager-project` (`avp-sdk` on PyPI is an unrelated project)
- [ ] Each migrated agent: version `0.1.0b1`, depending on
  `agent-voyager-project>=0.1.0b1,<0.2`, since its `[tool.uv.sources]` path
  applies only in the repository
- [ ] Before publishing, install the built wheels in a clean image and run
  `ping` and `describe`
- [ ] `avp agent install` can install the project's own agents from the
  published versions, without a checkout
