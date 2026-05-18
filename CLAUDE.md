# Working in this repo

> Read this before adding code. Claude Code (and the user) will load it
> automatically; the rules below are how AVP stays correct over time.

> [!IMPORTANT]
> ## v0.1 is a work in progress. Breaking changes are allowed.
>
> AVP is in active design iteration. The wire format, event types,
> Commission / Descriptor shape, conformance criteria, and any of the
> Pydantic source-of-truth models in `python/avp/src/avp/` may change
> without backwards-compatibility shims while we are on v0.1.x. There is
> no deprecation cycle, no compatibility layer, no "keep the old name
> too." A change lands cleanly, sweeps every dependent surface in the
> repo (schemas, generated bindings, conformance cases, in-tree agents
> and adapters, examples, prose docs), and that is the new shape.
>
> When something on the wire looks wrong, push back on it directly.
> When a design choice feels like a burden on agent implementors
> (e.g. agent-side accumulators, snapshot duplication, fields that
> are reconstructable from raw events), propose dropping or restructuring
> it; do not preserve it out of momentum. v0.2 will lock the shape;
> until then, nothing here is load-bearing for compatibility.

## What AVP is

AVP = **Agent Voyager Project**, an open-source collection of specs for the
agent-execution case:

- **AVP Trajectory** (`spec/v0.1/trajectory.md`): event stream
- **AVP Commission** (`spec/v0.1/commission.md`): run-config object
- **AVP Agent Descriptor** (`spec/v0.1/agent-descriptor.md`): agent self-description
- **AVP Resolver API** (`spec/v0.1/resolver.md`): JSON-RPC for ref dereferencing

The three data-shape specs (Trajectory/Commission/Agent Descriptor) compose
independently; the Resolver API is the only thing that's actually a
protocol (wire-level request/response). Each spec carries its own RFC
2119 keywords and conformance criteria for its layer; an
implementation may adopt one or all.

## Agents vs SDK adapters

The repo packages two kinds of things on top of the wire format. Get the
right one when picking where new code lives; the contracts differ.

**Agent.** Owns the agent loop. Reads a Commission from input, emits the
trajectory, advertises an Agent Descriptor, dispatches tools, calls the
resolver for managed assets, and produces `agent_stopped` with a stop
reason. An agent IS what `spec/v0.1/` certifies as conforming. Examples
in this repo: `avp-claude-agent-sdk` (built on the Claude Agent SDK, which
already owns a loop), and the reference agent at
`python/supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py`
(built on the `avp-anthropic` SDK adapter plus `AVPAgent`).

**SDK adapter.** Translates one raw API / client surface to AVP. Ships a
`ModelDriver` (turn-by-turn translation that plugs into `AVPAgent`), a
`TracedClient` (drop-in observability over an existing SDK loop), and
Commission-to-API translators. Ships NO agent loop and NO built-in tools:
the underlying API doesn't have them, so neither does the adapter. Agents
wrap the adapter. Example: `avp-anthropic` for the Anthropic Messages API.

Rule of thumb for new providers: if the upstream SDK ships its own agent
loop and tool catalog, package a complete agent under `python/agents/`.
If the upstream is a raw HTTP client, package an SDK adapter under
`python/sdks/` and add a reference agent in
`python/supervisors/simple-supervisor-example/examples/`. The descriptor
helper and the driver protocol are designed so the agent does the
minimum of plumbing.

The folder split reflects this: `python/agents/` for agents,
`python/sdks/` for adapters, `python/supervisors/.../examples/` for
worked reference agents that sit on top of adapters.

Agents-vs-adapters is the packaging axis. The orthogonal *integration*
axis (who owns the loop, what role Commission plays) is described in
`PATTERNS.md`. When the question is "where does new code live," consult
this section; when it's "how does an application wire onto AVP," consult
`PATTERNS.md`.

## What AVP is built on (read before changing the wire)

AVP specializes existing industry specs, it doesn't reinvent them. Every wire
change MUST stay compatible with the upstream spec it's anchored to:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`, `source`,
  `type`, `subject`, `time`, `data`)
- **OTel span identification**: `trace_id` / `span_id` / `parent_span_id` on
  every event's `data`
- **OpenTelemetry GenAI semantic conventions** are NOT on the wire. AVP
  owns its attribute namespace (`avp.usage.input_tokens`, `avp.tool.name`,
  ...) and ships a documented AVP → `gen_ai.*` projection in
  `FOUNDATIONS.md` for consumers forwarding into OTel-native backends.
- **JSON-RPC 2.0** for the AVP Resolver API. Agent calls `avp.resolve`
  and `avp.spawn_subagent` against a supervisor-stood-up service to dereference
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
make schemas    # uv --directory python run python ../scripts/generate-schemas.py
```

The Pydantic models under `python/avp/src/avp/` (`avp.commission`,
`avp.descriptor`, `avp.trajectory`) are the source of truth; the JSON
Schema files under `spec/v0.1/` are derived from them.

## The seams principle

**When you add a feature, add a test that crosses at least one seam.**

The seams in this repo:

- CLI ↔ agent: stdin parses Commission, agent runs, stdout streams events
- agent ↔ driver across multiple turns: history accumulates; the driver
  re-translates it on every turn
- translator ↔ SDK: the SDK reports state (cumulative usage, message
  classes); the translator must derive AVP wire shape from it
- supervisor ↔ agent subprocess: Commission piped in, NDJSON piped out, RPC
  replies on stdin
- agent ↔ workspace: tool inputs resolve against the agent's CWD

## Test layers and where to add tests

| Layer | Location | Catches |
|---|---|---|
| **JSON Schema** | `spec/v0.1/{trajectory,commission,agent-descriptor}.schema.json` | Wire shape: every `Event`, `Commission`, and `AgentDescriptor` field |
| **Conformance** | `conformance/v0.1/cases/*.json` | Wire-level rules (every MUST across the specs); driven via `avp-conformance` against the reference agent with `ScriptedModel` |
| **Unit** | `python/<pkg>/tests/test_*.py` | Single-component behavior with seams mocked |
| **Seam** | `tests/test_cli_smoke.py`, `tests/test_multi_turn.py`, translator-state tests | Cross-component bugs that unit tests can't see |
| **Real-LLM** | `tests/test_real_llm.py` (gated `-m real_llm` + `ANTHROPIC_API_KEY`) | End-to-end correctness against actual model responses |
| **Examples** | `python/supervisors/simple-supervisor-example/examples/` | Full Commission → trajectory → summary on real LLMs in narrative form |

## Decision tree when adding a feature

1. **Wire-level rule (a MUST in any spec)** → add a conformance case.
2. **Single-component behavior** → unit test in that package's `tests/`.
3. **Behavior depends on cross-component state** (history shape, cumulative
   usage, CLI lifecycle, subprocess CWD) → **seam test**. This is the layer
   that's easy to skip and where the bugs hide.
4. **Provider-specific real-model behavior** → real-LLM smoke, gated.

## Deterministic checks

The `avp-conformance` CLI ships three subcommands; run them all before
committing wire-format changes:

```bash
make conformance                                  # runs all three below

# or directly via uv (Python workspace root lives at python/):
uv --directory python run avp-conformance run             # execute every case against the reference agent
uv --directory python run avp-conformance validate        # schema-validate the case files themselves
uv --directory python run avp-conformance check-coverage  # every event type declared in the schema has ≥1 case
```

`check-coverage` is the deterministic floor: a new event type without a
matching conformance case fails the command. Wire it into CI when you have one.

## End-to-end sanity: `make smoke`

`make check` (format + lint + tests + conformance + bindings drift
detection) is the **free pre-commit floor**. Run it on every change.
Drift detection catches the case where the AVP Pydantic models
(`avp.commission` / `avp.descriptor` / `avp.trajectory`) or schemas
changed but the generated Rust / TypeScript bindings under `rust/avp/`
and `typescript/avp/` weren't regenerated.

`make smoke` is the **paid pre-merge ceiling**. It runs `check`, then the
Rust + TS bindings test suites (`cargo test` + `npm test` against the
generated types), then the real-LLM test matrix for both agents, then
every example end-to-end against real Anthropic models. Costs ~$0.10–0.20
on Haiku.

Run `make smoke` whenever you've changed something that could pass unit /
seam tests but break real-model integration. Concretely, that's any of:

- **Wire format**: `python/avp/src/avp/{commission,descriptor,trajectory}.py`,
  the JSON Schemas, any new event type or Commission field.
- **Agent loop**: `python/avp/src/avp/agent/agent.py` (tool/subagent
  dispatch, history shape).
- **Provider drivers / translators**:
  `python/sdks/avp-anthropic/src/avp_anthropic/driver.py` (token / cost
  extraction), `python/agents/avp-claude-agent-sdk/src/avp_claude_agent/translator.py`
  (SDK message handling, hook installation).
- **Tracer or traced clients**: `avp.tracer` (AVPTracer, format_event,
  module-level helpers), `avp_anthropic.AnthropicTracedClient` /
  `wrap_anthropic`, `avp_claude_agent.TracedClaudeSDKClient` /
  `traced_claude_sdk_client`.
- **`build_anthropic_tools` and similar Commission → SDK translators**: they
  affect what the model actually sees.

Skip `make smoke` only for doc-only changes, internal refactors with no
observable wire impact, or test-only changes. When in doubt, run it.
The real-LLM tests have caught silent bugs that no mock could surface
(model-side flakiness, SDK-version drift, cost-calculation arithmetic
that compiled fine but undercounted by 30%).

## Things you should not do

- Do NOT add prose docs that duplicate the specs under `spec/v0.1/`. Two
  sources of truth drift. Either update the relevant spec
  (`trajectory.md` / `commission.md` / `agent-descriptor.md` / `resolver.md`) or
  update `README.md`'s explanation; not both with the same content.
- Do NOT update test counts in any markdown doc. They will go stale within
  a week. The conformance harness CLI prints the live count.
- Do NOT skip the seam-test step "because the unit tests pass." The
  unit tests passed when each of the bugs we shipped was a bug.
- Do NOT append assistant turns to history without their `tool_calls`
  entries. The next model call will fail validation. (`agent.py` enforces
  this; if you reorganize the loop, preserve it.)
- Do NOT use em dashes in prose. Use commas, periods, semicolons, colons,
  or parentheses instead.

## What's intentionally out of scope

- Supervisor↔agent transport. AVP defines the JSON shape of Commission and trajectory events; how bytes move (stdio, HTTP, message bus, in-process) is a deployment concern. The reference implementations bind to stdio; everything else is up to the implementer.
- Multi-run orchestration (supervisor framework concern)
- Persistence (events live in memory per run)

## Project shape

- `spec/v0.1/`: the four normative specs (Trajectory, Commission, Agent Descriptor, Resolver API), their JSON Schemas (auto-generated), and an umbrella `README.md` that indexes them.
- `conformance/v0.1/cases/`: language-agnostic test cases.
- `python/avp/`: wire types (Pydantic), reference agent (`AVPAgent`),
  reference tracer (`AVPTracer` in `avp.tracer` for instrumenting an existing
  loop), conformance harness, and cross-validation interop tests (gated on the
  `[interop]` extras group).
- `python/sdks/avp-anthropic/`: SDK adapter for the raw Anthropic Messages API:
  `AnthropicModelDriver` (plugs into `AVPAgent` as a `ModelDriver`),
  `AnthropicTracedClient` + `wrap_anthropic` (drop-in over an existing
  Anthropic SDK loop), and Commission-to-API translators. No agent loop or
  built-in tools: the API itself ships neither, and agents wrap the SDK.
- `python/agents/avp-claude-agent-sdk/`: observer-pattern agent over Claude Agent SDK,
  plus `TracedClaudeSDKClient` and `traced_claude_sdk_client` (drop-in over an
  existing `ClaudeSDKClient` loop). The Claude Agent SDK ships its own loop +
  tools, so this is a complete agent rather than an adapter.
- `python/supervisors/simple-supervisor-example/`: worked supervisor example
  plus runnable real-LLM examples (`examples/01_*` through `examples/07_*`)
  and `examples/_anthropic_reference_agent.py`: a reference agent built on
  the `avp-anthropic` SDK adapter, demonstrating how to wire a `ModelDriver`
  to `AVPAgent` with a local `ToolDriver` (`ShellTools`).
- `scripts/`: `generate-schemas.py`, `build-skill.sh`.
- `Makefile`: `make help` lists all targets; `make smoke` is the pre-merge
  full-matrix sanity check (see above).
- `FOUNDATIONS.md`: what AVP is built on (CloudEvents, OTel GenAI, OTel spans,
  JSON-RPC 2.0, MCP, Agent Skills, JSON Schema) and what it specializes.
