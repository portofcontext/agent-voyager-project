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
- [ ] Python wire models from the spec reference tables
- [ ] JSON Schemas generated into `spec/v0.1/`, with spec examples as tests
- [ ] Rust and TypeScript bindings regenerated
- [x] Recorder (`avp.recorder`), with shared cases in `avp_sdk/testdata/recorder/`
- [x] Run plan (`avp.utils.run_plan`): what a run uses (`agent_started`) and what it turns off, with shared cases in `avp_sdk/testdata/run_plan/`
- [x] Pricing for the Model object (`avp.utils.pricing`, snapshot in `avp/utils/data/avp_prices.json`)
- [ ] Publishing the SDK refreshes the snapshot first (`make prices`, `scripts/update-prices.py`)
- [ ] Scripts kept on purpose, each reviewed, moved to `scripts/`
- [ ] Remove `avp/bindings/` and `avp/scripts/`

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
