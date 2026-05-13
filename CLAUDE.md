# Working in this repo

> Read this before adding code. Claude Code (and the user) will load it
> automatically; the rules below are how AVP stays correct over time.

## What AVP is

AVP = **Agent Voyager Project**, an open-source collection of specs for the
agent-execution case, rolling out in two stages.

**Stage 1: standardize the agent journey** (Stable):

- **AVP Trajectory** (`spec/trajectory/v0.1/trajectory.md`): the event stream every agent emits as it runs
- **AVP Agent Descriptor** (`spec/agent-descriptor/v0.1/agent-descriptor.md`): what the agent advertises about itself

**Stage 2: standardize how we pack the ships** (Beta):

- **AVP Commission** (`spec/commission/v0.1-beta/commission.md`): the run-config a supervisor hands the agent at startup
- **AVP Resolver API** (`spec/resolver/v0.1-beta/resolver.md`): the JSON-RPC channel the agent uses to dereference Commission refs at runtime

Each spec is implementable independently. Stable specs maintain
backward compatibility within their major version; Beta specs (`-beta`
suffix) can take breaking changes before promotion while deployment
patterns settle.
Most production runs adopt both stages; trajectory-only adoption is
first-class supported. Each spec carries its own RFC 2119 keywords and
conformance criteria.

## Agents vs SDK adapters

The repo packages two kinds of things on top of the wire format. Get the
right one when picking where new code lives; the contracts differ.

**Agent.** Owns the agent loop. Reads a Commission from input, emits the
trajectory, advertises an Agent Descriptor, dispatches tools, calls the
resolver for managed assets, and produces `agent_stopped` with a stop
reason. An agent IS what `spec/` certifies as conforming. Examples
in this repo: `avp-claude-agent` (built on the Claude Agent SDK, which
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
- **OpenTelemetry GenAI semantic conventions** for token / cost / model / tool
  attribute names inside `data` (`gen_ai.usage.input_tokens`, `gen_ai.tool.name`)
- **OTel span identification**: `trace_id` / `span_id` / `parent_span_id` on
  every event's `data`
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

The Pydantic models in `python/avp/src/avp/types.py` are the source of truth;
the JSON Schema files under `spec/` are derived from them.

## Test layers and where to add tests

| Layer | Location | Catches |
|---|---|---|
| **JSON Schema** | `spec/{trajectory,commission,agent-descriptor}.schema.json` | Wire shape: every `Event`, `Commission`, and `AgentDescriptor` field |
| **Conformance** | `conformance/cases/*.json` | Wire-level rules (every MUST across the specs); driven via `avp-conformance` against the reference agent with `ScriptedModel` |
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
Drift detection catches the case where `types.py` or schemas changed but
the generated Rust / TypeScript bindings under `rust/avp/` and
`typescript/avp/` weren't regenerated.

`make smoke` is the **paid pre-merge ceiling**. It runs `check`, then the
Rust + TS bindings test suites (`cargo test` + `npm test` against the
generated types), then the real-LLM test matrix for both agents, then
every example end-to-end against real Anthropic models. Costs ~$0.10–0.20
on Haiku.

Run `make smoke` whenever you've changed something that could pass unit /
seam tests but break real-model integration. Concretely, that's any of:

- **Wire format**: `python/avp/src/avp/types.py`, the JSON Schemas, any new
  event type or Commission field.
- **Agent loop**: `python/avp/src/avp/agent/agent.py` (tool/subagent
  dispatch, history shape).
- **Provider drivers / translators**:
  `python/sdks/avp-anthropic/src/avp_anthropic/driver.py` (token / cost
  extraction), `python/agents/avp-claude-agent/src/avp_claude_agent/translator.py`
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