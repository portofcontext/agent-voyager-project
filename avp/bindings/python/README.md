# avp — Python wire types for the Agent Voyager Project v0.1

Spec: [`avp/core/spec/v0.1/`](../../core/spec/v0.1/)
Conformance suite: the separate [`avp-conformance`](../../core/conformance/) package.

This package is **wire-types-only**: the Pydantic source of truth for the AVP
v0.1 wire format plus a minimal event sink. It ships NO agent loop, driver
protocols, or tracer. Those belong in the integrator package that needs them
(an agent inlines its own loop and emits events to an `EventSink`). See
[`CLAUDE.md`](CLAUDE.md) for the package charter.

It ships:

- **Wire types**: Pydantic v2 models for every Commission, Event, and
  AgentDescriptor variant, with discriminated unions on `type`. Spec-scoped
  modules: `avp.commission`, `avp.descriptor`, `avp.trajectory`, plus
  `avp.content` (assistant content blocks), `avp.envelope` (the CloudEvents
  envelope + OTel span-id helpers), `avp.gen_ai` (the AVP to `gen_ai.*`
  projection), `avp.history` (provider-history helpers), and `avp.pricing`
  (the bundled price table + `compute_cost`).
- **Sink** (`avp.sink`): `EventSink`, the async-callable type for "consume one
  trajectory event", with the built-in `stdio_sink` (NDJSON to stdout) and
  `jsonl_sink(path)`. No base class, no agent abstraction.

The JSON Schemas under `avp/core/spec/v0.1/` are generated FROM these models
(`make schemas`); the models are the source of truth. The Rust and TypeScript
bindings are generated from the same schemas, so the three languages cannot
drift.

`src/avp/archive/` holds the retired pre-restructure implementation (old agent
loop, driver protocols, tracer, resolver). Do NOT import from it; it exists for
review only.

## Quickstart

The repo is a uv workspace; bootstrap once from the repo root:

```bash
cd /path/to/agent-voyager-project
make sync
```

Then:

```bash
uv run python -m pytest avp/bindings/python   # this package's tests
uv run avp-conformance validate               # validate every packaged conformance case
```

## Package layout

```
src/avp/
  __init__.py       # SCHEMA_VERSION, __version__
  commission.py     # Commission (source of truth)
  descriptor.py     # AgentDescriptor + ToolDecl / SubagentDecl / SkillDecl / McpServerDecl
  trajectory.py     # Event union + per-event data payloads, parse_event / event_to_wire
  content.py        # AVPContentBlock union (text / thinking / tool_use / tool_result / ...)
  envelope.py       # CloudEvents 1.0 envelope + OTel span-id helpers
  gen_ai.py         # AVP to OpenTelemetry gen_ai.* projection
  history.py        # provider-history helpers
  pricing.py        # bundled price table + compute_cost
  sink.py           # EventSink type + stdio_sink / jsonl_sink
  data/prices.json  # bundled price table (synced from models.dev)
  archive/          # retired pre-restructure impl, do NOT import
```
