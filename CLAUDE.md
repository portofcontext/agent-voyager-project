# Working in this repo

> Read this before adding code. Claude Code (and the user) will load it
> automatically; the rules below are how AVP stays correct over time.

## What AVP is built on (read before changing the wire)

AVP specializes existing industry specs — it doesn't reinvent them. Every wire
change MUST stay compatible with the upstream spec it's anchored to:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`, `source`,
  `type`, `subject`, `time`, `data`)
- **OpenTelemetry GenAI semantic conventions** for token / cost / model / tool
  attribute names inside `data` (`gen_ai.usage.input_tokens`, `gen_ai.tool.name`)
- **OTel span identification** — `trace_id` / `span_id` / `parent_span_id` on
  every event's `data`
- **JSON-RPC 2.0** for the AVP resolver protocol — agent calls `avp.resolve`
  + `avp.spawn_subagent` against a supervisor-stood-up service to dereference
  opaque refs in `Commission.{mcp_servers,skills,subagents}[].ref`
- **MCP 2025-11-25** for the connection material the resolver returns for
  each `mcp_server` ref (transport / url / auth / command etc.); the agent's
  MCP client consumes it
- **Agent Skills** (agentskills.io) for SKILL.md content (returned by the
  resolver for each `skill` ref)

AVP-specific concepts (no-mid-run-reach-in, trajectory contract) live
under the `avp.*` attribute namespace. See `FOUNDATIONS.md`
for the full mapping.

When you touch the wire, regenerate the schemas:

```bash
uv run python scripts/generate-schemas.py
```

The Pydantic models in `python/avp/src/avp/types.py` are the source of truth;
the JSON Schema files under `spec/v0.1/` are derived from them.

## The seams principle

**When you add a feature, add a test that crosses at least one seam.**

The seams in this repo:

- CLI ↔ agent — stdin parses Commission, agent runs, stdout streams events
- agent ↔ driver across multiple turns — history accumulates; the driver
  re-translates it on every turn
- translator ↔ SDK — the SDK reports state (cumulative usage, message
  classes); the translator must derive AVP wire shape from it
- supervisor ↔ agent subprocess — Commission piped in, NDJSON piped out, RPC
  replies on stdin
- agent ↔ workspace — tool inputs resolve against the agent's CWD

## Test layers and where to add tests

| Layer | Location | Catches |
|---|---|---|
| **JSON Schema** | `spec/v0.1/avp.schema.json` | Wire shape — every `Commission` and `Event` field |
| **Conformance** | `conformance/v0.1/cases/*.json` | Wire-level rules (every MUST in `SPEC.md`); driven via `avp-conformance` against the reference agent with `ScriptedModel` |
| **Unit** | `python/<pkg>/tests/test_*.py` | Single-component behavior with seams mocked |
| **Seam** | `tests/test_cli_smoke.py`, `tests/test_multi_turn.py`, translator-state tests | Cross-component bugs that unit tests can't see |
| **Real-LLM** | `tests/test_real_llm.py` (gated `-m real_llm` + `ANTHROPIC_API_KEY`) | End-to-end correctness against actual model responses |
| **Examples** | `python/supervisors/simple-supervisor-example/examples/` | Full Commission → trajectory → summary on real LLMs in narrative form |

## Decision tree when adding a feature

1. **Wire-level rule (a MUST in `SPEC.md`)** → add a conformance case.
2. **Single-component behavior** → unit test in that package's `tests/`.
3. **Behavior depends on cross-component state** (history shape, cumulative
   usage, CLI lifecycle, subprocess CWD) → **seam test**. This is the layer
   that's easy to skip and where the bugs hide.
4. **Provider-specific real-model behavior** → real-LLM smoke, gated.

## Deterministic checks

The `avp-conformance` CLI ships three subcommands; run them all before
committing wire-format changes:

```bash
uv run avp-conformance run             # execute every case against the reference agent
uv run avp-conformance validate        # schema-validate the case files themselves
uv run avp-conformance check-coverage  # every event type declared in the schema has ≥1 case
```

`check-coverage` is the deterministic floor: a new event type without a
matching conformance case fails the command. Wire it into CI when you have one.

## End-to-end sanity: `make smoke`

`make check` (format + lint + tests + conformance + bindings drift
detection) is the **free pre-commit floor** — run it on every change.
Drift detection catches the case where `types.py` or schemas changed but
the generated Rust / TypeScript bindings under `rust/avp/` and
`typescript/avp/` weren't regenerated.

`make smoke` is the **paid pre-merge ceiling** — runs `check`, then the
Rust + TS bindings test suites (`cargo test` + `npm test` against the
generated types), then the real-LLM test matrix for both agents, then
every example end-to-end against real Anthropic models. Costs ~$0.10–0.20
on Haiku.

Run `make smoke` whenever you've changed something that could pass unit /
seam tests but break real-model integration. Concretely, that's any of:

- **Wire format** — `python/avp/src/avp/types.py`, the JSON Schemas, any new
  event type or Commission field.
- **Agent loop** — `python/avp/src/avp/agent/agent.py` (tool/subagent
  dispatch, history shape).
- **Provider drivers / translators** —
  `python/agents/avp-anthropic/src/avp_anthropic/driver.py` (token / cost
  extraction), `python/agents/avp-claude-agent/src/avp_claude_agent/translator.py`
  (SDK message handling, hook installation).
- **Tracer or traced clients** — `avp.tracer` (AVPTracer, format_event,
  module-level helpers), `avp_anthropic.AnthropicTracedClient` /
  `wrap_anthropic`, `avp_claude_agent.TracedClaudeSDKClient` /
  `traced_claude_sdk_client`.
- **`build_anthropic_tools` and similar Commission → SDK translators** — they
  affect what the model actually sees.

Skip `make smoke` only for doc-only changes, internal refactors with no
observable wire impact, or test-only changes. When in doubt, run it —
the real-LLM tests have caught silent bugs that no mock could surface
(model-side flakiness, SDK-version drift, cost-calculation arithmetic
that compiled fine but undercounted by 30%).

## Things you should not do

- Do NOT add prose docs that duplicate `SPEC.md`. Two sources of truth
  drift. Either update `SPEC.md` or update `README.md`'s explanation; not
  both with the same content.
- Do NOT update test counts in any markdown doc. They will go stale within
  a week. The conformance harness CLI prints the live count.
- Do NOT skip the seam-test step "because the unit tests pass." The
  unit tests passed when each of the bugs we shipped was a bug.
- Do NOT append assistant turns to history without their `tool_calls`
  entries. The next model call will fail validation. (`agent.py` enforces
  this; if you reorganize the loop, preserve it.)

## What's intentionally out of scope

- HTTP transport (spec'd, not implemented)
- Multi-run orchestration (supervisor framework concern)
- Persistence (events live in memory per run)

## Project shape

- `spec/v0.1/` — normative spec + JSON Schema bundle (auto-generated)
- `conformance/v0.1/cases/` — language-agnostic test cases
- `python/avp/` — wire types (Pydantic) + reference agent (`AVPAgent`) +
  reference tracer (`AVPTracer` in `avp.tracer` for instrumenting an existing
  loop) + conformance harness + cross-validation interop tests (gated on the
  `[interop]` extras group)
- `python/agents/avp-anthropic/` — driver-pattern agent over Anthropic API,
  plus `AnthropicTracedClient` and `wrap_anthropic` (drop-in over an existing
  Anthropic SDK loop)
- `python/agents/avp-claude-agent/` — observer-pattern agent over Claude Agent SDK,
  plus `TracedClaudeSDKClient` and `traced_claude_sdk_client` (drop-in over an
  existing `ClaudeSDKClient` loop)
- `python/supervisors/simple-supervisor-example/` — worked supervisor example
  + the runnable real-LLM examples (`examples/01_*` through `examples/07_*`)
- `scripts/` — `generate-schemas.py`, `build-skill.sh`
- `Makefile` — `make help` lists all targets; `make smoke` is the pre-merge
  full-matrix sanity check (see above)
- `FOUNDATIONS.md` — what AVP is built on (CloudEvents, OTel GenAI, OTel spans,
  JSON-RPC 2.0, MCP, Agent Skills, JSON Schema) and what it specializes
