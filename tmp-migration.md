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
│   └── testdata/recorder-vectors/ ⬜
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

- [ ] Python wire models from the spec reference tables
- [ ] JSON Schemas generated into `spec/v0.1/`, with spec examples as tests
- [ ] Rust and TypeScript bindings regenerated
- [ ] Recorder, with vectors written first in `avp_sdk/testdata/recorder-vectors/`
- [ ] Pricing for the Model object
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

### 5. Before `spec-v0.1-cleanup` merges to `main`

- [ ] Root docs cut down: `AGENTS.md`, `README.md`, `SKILL.md`, `PATTERNS.md`, `MAINTAINERS.md`
- [ ] `make check` passes
- [ ] `tmp-*` files removed
