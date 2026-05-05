# Working in this repo

> Read this before adding code. Claude Code (and the user) will load it
> automatically; the rules below are how AEP stays correct over time.

## The seams principle

**When you add a feature, add a test that crosses at least one seam.**

The seams in this repo:

- CLI ↔ runner — stdin parses Config, runner runs, stdout streams events
- runner ↔ driver across multiple turns — history accumulates; the driver
  re-translates it on every turn
- translator ↔ SDK — the SDK reports state (cumulative usage, message
  classes); the translator must derive AEP wire shape from it
- supervisor ↔ runner subprocess — Config piped in, NDJSON piped out, RPC
  replies on stdin
- runner ↔ workspace — verifier shell paths, tool inputs resolve against
  the runner's CWD

## Test layers and where to add tests

| Layer | Location | Catches |
|---|---|---|
| **JSON Schema** | `spec/v0.1/aep.schema.json` | Wire shape — every `Config` and `Event` field |
| **Conformance** | `conformance/v0.1/cases/*.json` | Wire-level rules (every MUST in `SPEC.md`); driven via `aep-conformance` against the reference runner with `ScriptedModel` |
| **Unit** | `python/<pkg>/tests/test_*.py` | Single-component behavior with seams mocked |
| **Seam** | `tests/test_cli_smoke.py`, `tests/test_multi_turn.py`, translator-state tests | Cross-component bugs that unit tests can't see |
| **Real-LLM** | `tests/test_real_llm.py` (gated `-m real_llm` + `ANTHROPIC_API_KEY`) | End-to-end correctness against actual model responses |
| **Examples** | `python/supervisors/simple-supervisor-example/examples/` | Full Config → trajectory → summary on real LLMs in narrative form |

## Decision tree when adding a feature

1. **Wire-level rule (a MUST in `SPEC.md`)** → add a conformance case.
2. **Single-component behavior** → unit test in that package's `tests/`.
3. **Behavior depends on cross-component state** (history shape, cumulative
   usage, CLI lifecycle, subprocess CWD) → **seam test**. This is the layer
   that's easy to skip and where the bugs hide.
4. **Provider-specific real-model behavior** → real-LLM smoke, gated.

## Deterministic checks

The `aep-conformance` CLI ships three subcommands; run them all before
committing wire-format changes:

```bash
uv run aep-conformance run             # execute every case against the reference runner
uv run aep-conformance validate        # schema-validate the case files themselves
uv run aep-conformance check-coverage  # every event type declared in the schema has ≥1 case
```

`check-coverage` is the deterministic floor: a new event type without a
matching conformance case fails the command. Wire it into CI when you have one.

## Things you should not do

- Do NOT add prose docs that duplicate `SPEC.md`. Two sources of truth
  drift. Either update `SPEC.md` or update `README.md`'s explanation; not
  both with the same content.
- Do NOT update test counts in any markdown doc. They will go stale within
  a week. The conformance harness CLI prints the live count.
- Do NOT skip the seam-test step "because the unit tests pass." The
  unit tests passed when each of the bugs we shipped was a bug.
- Do NOT use `>=` for boundary checks. Strict `>` per `SPEC.md` §9.2.
- Do NOT append assistant turns to history without their `tool_calls`
  entries. The next model call will fail validation. (`runner.py` enforces
  this; if you reorganize the loop, preserve it.)

## What's intentionally out of scope

- HTTP transport (spec'd, not implemented)
- Multi-run orchestration (supervisor framework concern)
- Persistence (events live in memory per run)

## Project shape

- `spec/v0.1/` — normative spec + JSON Schema bundle
- `conformance/v0.1/cases/` — language-agnostic test cases
- `python/aep/` — wire types + reference runner + conformance harness
- `python/runners/aep-anthropic/` — driver-pattern runner over Anthropic API
- `python/runners/aep-claude-agent/` — observer-pattern runner over Claude Agent SDK
- `python/supervisors/simple-supervisor-example/` — worked supervisor example
- `scripts/` — `run-examples.sh`, `check-conformance-coverage.py`, `build-skill.sh`
