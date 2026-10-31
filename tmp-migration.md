# Migration to the v0.1 layout

Tracks the rebuild on `spec-v0.1-cleanup`. Each item is written fresh against
the specs, not migrated, and the old code is removed when its replacement
lands. Read the old code on `main` for reference only.

## Target layout

```text
agent-voyager-project/
├── spec/v0.1/                     ✅ specs moved; schemas regenerate in step 2
├── avp_sdk/
│   ├── python/                    ⬜
│   ├── rust/                      ⬜
│   ├── typescript/                ⬜
│   └── testdata/recorder/, testdata/run_plan/ ✅ (Python passes; Rust and TypeScript to come)
├── avp-cli/                       ⬜ cleanup TBD
│   └── src/avp_cli/conformance/   ⬜ harness and cases/v0.1/
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

### 2. Core SDK (`avp_sdk/`)

- [x] `avp_sdk/python` is its own uv project with its own `uv.lock`; workspace members keep the old `avp/bindings/python` until they migrate
- [x] Python wire models from the spec reference tables
- [x] JSON Schemas generated into `spec/v0.1/` (`make schemas`)
- [ ] The spec documents' JSON examples as tests, against the models and the schemas
- [ ] Rust and TypeScript SDKs, checklists below
- [x] Recorder (`avp.recorder`), with shared cases in `avp_sdk/testdata/recorder/`
- [x] Run plan (`avp.utils.run_plan`): what a run uses (`agent_started`) and what it turns off, with shared cases in `avp_sdk/testdata/run_plan/`
- [x] Pricing for the Model object (`avp.utils.pricing`, snapshot in `avp/utils/data/avp_prices.json`)
- [x] Default base URLs (`avp.utils.base_urls`, snapshot in `avp/utils/data/avp_base_urls.json`), to replace avp-cli's `PROVIDER_REGISTRY` and the conformance meter's `UPSTREAMS`
- [ ] Publishing the SDK refreshes the snapshots first (`make sdk-data`)
- [ ] Scripts kept on purpose, each reviewed, moved to `scripts/`
- [ ] Remove `avp/bindings/` and `avp/scripts/`

#### Rust and TypeScript SDKs

Each SDK is one assignment, built fresh against the specs and the
[SDK README](avp_sdk/README.md), with the Python SDK as the reference. The two
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

Rust (`avp_sdk/rust`):

- [ ] Its own crate, with its tests run from the Makefile
  - [ ] Reviewed by a person
- [ ] Wire types generated from `spec/v0.1/*.schema.json`, with a make target that regenerates them and a drift check in `make check`
  - [ ] Reviewed by a person
- [ ] Recorder, passing every case in `avp_sdk/testdata/recorder/`
  - [ ] Reviewed by a person
- [ ] Commission checks, with the same refusal messages as Python (the Recorder cases pin them)
  - [ ] Reviewed by a person
- [ ] Run plan, passing every case in `avp_sdk/testdata/run_plan/`
  - [ ] Reviewed by a person
- [ ] Pricing, shipping `avp_prices.json` and loading it like Python (bundled or cache, optional `max_age`)
  - [ ] Reviewed by a person
- [ ] Agent command line: `ping`, `describe`, `run`, with the same exit codes
  - [ ] Reviewed by a person
- [ ] Its data directory added to `DATA_DIRS` in `scripts/update-sdk-data.py`
  - [ ] Reviewed by a person
- [ ] Supervisor tools, only when a Rust supervisor needs them: OpenTelemetry, CloudEvents, default base URLs
  - [ ] Reviewed by a person

TypeScript (`avp_sdk/typescript`):

- [ ] Its own npm package, with its tests run from the Makefile
  - [ ] Reviewed by a person
- [ ] Wire types generated from `spec/v0.1/*.schema.json`, with a make target that regenerates them and a drift check in `make check`
  - [ ] Reviewed by a person
- [ ] Recorder, passing every case in `avp_sdk/testdata/recorder/`
  - [ ] Reviewed by a person
- [ ] Commission checks, with the same refusal messages as Python (the Recorder cases pin them)
  - [ ] Reviewed by a person
- [ ] Run plan, passing every case in `avp_sdk/testdata/run_plan/`
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

### 4. Agents (`agents/`)

- [ ] `_template`
- [ ] `avp-claude-agent-sdk`
- [ ] `avp-codex`
- [ ] `avp-deep-agents`
- [ ] `avp-gemini-cli`
- [ ] `avp-goose`
- [ ] `avp-openai-agents`
- [ ] `avp-opencode`
- [ ] `avp-pi`
- [ ] `avp-pydantic-ai`

### 5. Split the uv workspace into separate projects

The SDK, avp-cli, and each agent are released separately, so each gets its own
`pyproject.toml`, `uv.lock`, and `.venv`, using the SDK by path. An agent's own
lock then produces its release `requirements.txt`.

- [x] `avp_sdk/python`
- [ ] `avp-cli`
- [ ] Each Python agent, in its agent PR
- [ ] Remove the root workspace, and run each project's checks from the Makefile

### 6. Before `spec-v0.1-cleanup` merges to `main`

- [ ] Root docs cut down: `AGENTS.md`, `README.md`, `SKILL.md`, `PATTERNS.md`, `MAINTAINERS.md`
  - `AGENTS.md` still describes the old wire: CloudEvents and OTel compatibility, `source: avp://agent`, `avp.*` attributes, `schema_version`, `origin/model` slugs, and `avp/bindings` as the source of truth
- [ ] `make check` passes
- [ ] `tmp-*` files removed
