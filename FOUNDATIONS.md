# Foundations — what AEP is built on

> **Thesis.** AEP does not reinvent telemetry, RPC, schemas, or skill formats.
> It specializes existing industry-standard wire formats for the
> agent-execution case. The way MCP specialized JSON-RPC for LLM tools, AEP
> specializes the broader telemetry-and-RPC stack for runs.

The unique work AEP does is small and focused: **verifiers, boundary
semantics, the no-mid-run-reach-in topology, and the trajectory-as-source-of-truth
contract.** Everything else — event envelopes, token/cost telemetry, run
spans, the RPC channel for agent-initiated tool execution, tool descriptors,
skill loading — comes from existing specs that already have ecosystems,
tooling, and documentation.

This document maps each spec we build on to the part of AEP it covers, names
what we deliberately do NOT take from each, and explains how the layers
compose into a single trajectory.

---

## The stack at a glance

```
┌─────────────────────────────────────────────────────────────────┐
│                          AEP v0.1                                 │
│  Wire format for agent execution observability + policy           │
└─────────────────────────────────────────────────────────────────┘

  Specializes existing specs (AEP wraps these for the agent case):
  ──────────────────────────────────────────────────────────────────
  CloudEvents 1.0        Event envelopes (every AEP event IS a CloudEvent)
  OTel GenAI sem-conv    Token / cost / model attribute naming
  OTel spans (OTLP)      Run lifecycle as parent-child span hierarchy
  JSON-RPC 2.0           Agent ↔ supervisor-service RPC channel for tool exec
  MCP                    Tool descriptors (Config.tools[] is MCP-compatible)
  Agent Skills           SKILL.md format + skill-source resolution
  JSON Schema 2020-12    Wire-format validation
  RFC 2119 / 8174        Normative-keyword semantics (MUST/SHOULD/MAY)
  ISO 8601 / RFC 3339    Timestamp format

  AEP-specific contributions (no upstream equivalent):
  ──────────────────────────────────────────────────────
  Verifier               First-class deterministic Boolean rule checks
                         with declared trigger and on_failure action
  Boundary               Hard execution limits with strict-greater semantics
                         and exact-N step guarantees
  Trajectory contract    Runner-emitted facts are canonical; supervisor
                         observes; supervisor RPC replies recorded verbatim
  No mid-run reach-in    Architectural constraint declared on the wire:
                         the agent's environment is fully specified at setup
```

---

## What each spec gives us

### CloudEvents 1.0

[CNCF spec](https://cloudevents.io/) for event payloads. Defines a JSON
envelope with required fields (`specversion`, `id`, `source`, `type`) and
optional fields (`subject`, `time`, `datacontenttype`, `data`). Has bindings
for HTTP, MQTT, Kafka, AMQP, NATS — so any AEP trajectory can be transported
on standard event infrastructure without re-encoding.

**What AEP takes:** the event envelope. Every AEP event is a valid CloudEvent.
`type` is reverse-DNS (`aep.model_turn_ended`); `source` is a URI
(`aep://runner` or `aep://supervisor`); `subject` carries `run_id`; `time`
carries the timestamp; `data` carries the AEP-specific payload.

**What AEP does NOT take:** the binary mode, datacontentencoding, or any
specific transport binding. Our base transport is stdio NDJSON; HTTP/SSE is
v0.2.

### OpenTelemetry — GenAI semantic conventions

[OTel semantic conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
define standard attribute names for LLM telemetry. Adopting these means
trajectories are immediately ingestable by any OTel-aware backend
(Datadog, Honeycomb, Tempo, Langfuse, Helicone, Arize, ...) with no custom
adapter.

The conventions AEP adopts (verified against the upstream
`open-telemetry/semantic-conventions` repo):

| Attribute | What it is |
|---|---|
| `gen_ai.provider.name` | Provider id — `anthropic`, `openai`, `aws.bedrock`, `gcp.gemini`, etc. (renamed from the older `gen_ai.system`) |
| `gen_ai.operation.name` | Operation kind — `chat`, `invoke_agent`, `embeddings`, ... |
| `gen_ai.request.model` / `gen_ai.response.model` | Request / response model id |
| `gen_ai.usage.input_tokens` | Total input tokens for the call. Per the spec: "should encompass all input token types, including cached ones" — exactly AEP's convention today. |
| `gen_ai.usage.output_tokens` | Output tokens for the call |
| `gen_ai.usage.cache_read.input_tokens` | Cache-read portion of input (note dotted form, not underscore) |
| `gen_ai.usage.cache_creation.input_tokens` | Cache-creation portion of input |
| `gen_ai.usage.reasoning.output_tokens` | Reasoning-model output tokens (Claude thinking, o-series). Recommended when applicable. |
| `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments` | Tool dispatch attributes |
| `gen_ai.response.finish_reasons` | Termination reasons array |
| `gen_ai.request.stream`, `gen_ai.response.time_to_first_chunk` | Streaming-specific attributes |

**What AEP takes:** the attribute namespace. Our token/model/tool fields
are renamed to match. AEP's run-level span uses `gen_ai.operation.name: "invoke_agent"`
(the conventions define both CLIENT and INTERNAL invoke_agent spans).
New per-event attributes that don't have a GenAI equivalent — most
notably **cost** and AEP-specific concepts like verifier outcomes — get
the `aep.*` namespace.

**What AEP does NOT take:** experimental conventions still flagged as
unstable. The GenAI conventions overall are still under the
`gen_ai_latest_experimental` stability flag (consumers opt in via
`OTEL_SEMCONV_STABILITY_OPT_IN`); AEP `SPEC.md` pins a specific
upstream commit and only adopts attributes whose names have stabilized.

**On cost specifically:** OTel has not standardized a cost attribute as
of this writing (verified against the live spec repo). AEP keeps cost
in the `aep.*` namespace as `aep.cost_usd`. When upstream standardizes
a name (e.g., `gen_ai.usage.cost`), AEP adopts it in the next minor
version and aliases the old field for one release.

### OpenTelemetry — OTLP / spans

[OTLP](https://opentelemetry.io/docs/specs/otlp/) defines the wire format
for spans (and metrics, logs). Spans are the canonical "thing that happened
over an interval" — they have `trace_id`, `span_id`, `parent_span_id`,
`start_time`, `end_time`, `attributes`, `events`, and `status`.

**What AEP takes:** the span identification model. Every AEP event carries
`trace_id`, `span_id`, `parent_span_id` so a downstream consumer can
reconstruct the run's span hierarchy:

```
agent.run                              (top-level span)
├─ model_turn (step 1)                 (child)
│  └─ tool_call (read_file)           (grandchild)
├─ model_turn (step 2)
└─ model_turn (step 3)
```

The wire stays flat NDJSON — events stream one per line — but the IDs let
any OTel collector rebuild the tree.

**What AEP does NOT take:** the OTel SDK at runtime. We are a producer of
span-shaped JSON, not a span exporter. Consumers who want spans in
Datadog/etc. use their own collector. AEP introduces zero infrastructure
dependencies.

### JSON-RPC 2.0

[JSON-RPC 2.0](https://www.jsonrpc.org/specification) is the standard JSON
RPC protocol: `{jsonrpc: "2.0", id, method, params}` ↔
`{jsonrpc: "2.0", id, result | error}`. Has standard error codes
(`-32700` parse error, `-32600` invalid request, `-32601` method not found,
`-32602` invalid params, `-32603` internal error). Reserved range
`-32000` to `-32099` for application-defined codes.

**What AEP takes:** the RPC channel for tool execution. `tool_exec_request`
carries a JSON-RPC request payload; `tool_exec_resolved` carries a
JSON-RPC response. Our `request_id` is the JSON-RPC `id`; our `tool` is
the JSON-RPC `method`; our `input` is `params`. Errors map to the standard
error envelope. Timeouts use a registered code in the `-32000` range.

**What AEP does NOT take:** JSON-RPC's batching or notifications. Each
tool_exec is a single request/response pair.

### MCP (Model Context Protocol)

[MCP](https://modelcontextprotocol.io/) is built on JSON-RPC 2.0. It
specifies how an LLM client talks to a server that exposes tools, resources,
and prompts. The relevant part for AEP is the tool descriptor:
`{name, description, inputSchema}` — exactly what `Config.tools[]` declares.

**What AEP takes:** the tool descriptor format. `Config.tools[]` entries are
MCP-compatible JSON. Anyone running an MCP server can drop tool descriptors
into a Config verbatim. Anyone reading a Config can register the tools as
MCP tools verbatim.

**What AEP does NOT take:** MCP's server protocol. AEP doesn't run MCP
servers; it consumes MCP-shaped tool descriptions. The supervisor is free
to back tool execution with anything (an MCP server, a local function, a
remote HTTP service) — the wire describes the tool, not the implementation.

### Agent Skills

[Agent Skills](https://agentskills.io/specification) defines the SKILL.md
format: YAML frontmatter (`name`, `description`) plus markdown body
describing what the skill does and how to use it. Distribution is via
filesystem paths, HTTPS URLs, or a registry scheme (e.g., `anthropic:<id>@<version>`).

**What AEP takes:** the SKILL.md format and the source-resolution scheme.
`Config.skills[]` entries are `{name, source, config?}` where `source`
is one of: `anthropic:<id>@<version>`, an HTTPS URL, or a filesystem path.
Runners load the SKILL.md, expose it to the agent, and emit `skill_loaded`
into the trajectory. The repo's own [`SKILL.md`](./SKILL.md) is a worked
example.

**What AEP does NOT take:** skill execution semantics. AEP records that a
skill was loaded; whether and how the agent uses it is between the agent
and the skill.

### JSON Schema 2020-12

Standard schema for declarative JSON validation. Used throughout AEP for
both the wire schema bundle (`spec/v0.1/aep.schema.json`) and tool
`inputSchema` fields.

**What AEP takes:** Draft 2020-12 with `$ref` resolution. Already a
dependency.

**What AEP does NOT take:** schema dialects other than 2020-12. We require
exactly that draft.

### RFC 2119 / 8174

Normative keywords (MUST, SHOULD, MAY, MUST NOT, SHOULD NOT). Standard for
conformance language in protocol specs.

**What AEP takes:** the keyword vocabulary. Used throughout `SPEC.md` to
distinguish hard requirements from recommendations.

### ISO 8601 / RFC 3339

Standard timestamp format. UTC-suffixed (`Z`) recommended.

---

## What AEP specializes (the actual contribution)

These four concepts have no equivalent in any of the upstream specs.
They're AEP's reason for existing.

### Verifier

A `Verifier` is a deterministic Boolean check the agent runs at a declared
trigger. It has a name, a trigger (e.g., `on_tool:write_file`,
`after_each_turn`), a source (e.g., a shell command), and an `on_failure`
action (`halt` / `inject_correction` / `continue`).

OTel has spans and events; it doesn't model declared rules with
agent-side enforcement and supervisor-readable outcomes. The closest
adjacent concept is OPA/Rego policy, but that's external evaluation.
Verifiers compile to ON-WIRE primitives that the agent enforces directly.

### Boundary

`Boundary` declares hard execution limits — `max_cost_usd`, `max_steps`,
`max_tokens` — with strict-greater enforcement, an exact-N promise for
steps, and specific monotonicity guarantees (cumulative-usage SDKs MUST
detect resets; cache-read tokens count as input).

OTel has resource attributes and rate-limiting in collectors. None of
those model "the agent stops itself when it crosses this line." Boundary
semantics are policy-on-the-wire, evaluated by the runner without
mid-run supervisor involvement.

### Trajectory contract

The runner's stdout is the canonical record. Three classes of facts are
declared distinct: what the agent did, what the rules said, what the run
cost. Supervisor RPC replies are recorded verbatim into the same stream.
Implementations MUST NOT strip or rewrite supervisor-emitted records.

OTel has trace export pipelines but the canonicality model is different —
spans flow to a backend and are queried. AEP makes the trajectory itself
the truth, not a derived view of it.

### No mid-run reach-in

The supervisor declares the environment in a Config sent at startup and
observes the trajectory. It does not reach in mid-run. The agent's
environment is fully specified up front. The one exception — environmental
services via JSON-RPC — is agent-initiated, not supervisor-initiated.

This is an architectural constraint expressed as a wire constraint:
`SupervisorMessage` is restricted to `tool_exec_resolved` (RPC replies)
in v0.1. Nothing else crosses that channel. This is what makes
trajectories meaningful: every fact in the record was produced by either
agent action or a service the agent called, not by a controller pushing
in unilateral decisions.

---

## How the layers compose: one event walked through

A `model_turn_ended` event illustrates every layer:

```jsonc
{
  // CloudEvents 1.0 envelope
  "specversion": "1.0",
  "id": "ev-7f3a-0042",
  "source": "aep://runner",
  "type": "aep.model_turn_ended",
  "subject": "auth-refactor-20260502-abc123",      // run_id
  "time": "2026-05-06T14:32:01.428Z",
  "datacontenttype": "application/json",

  "data": {
    // OTel span identification — lets a collector rebuild the tree
    "trace_id": "5b8efff798038103d269b633813fc60c",
    "span_id": "eee19b7ec3c1b173",
    "parent_span_id": "0000000000000001",          // top-level run span

    // OTel GenAI semantic conventions — recognizable to any GenAI backend
    "gen_ai.provider.name": "anthropic",
    "gen_ai.operation.name": "chat",
    "gen_ai.request.model": "claude-haiku-4-5-20251001",
    "gen_ai.response.model": "claude-haiku-4-5-20251001",
    "gen_ai.usage.input_tokens": 628,                       // includes cache reads/writes
    "gen_ai.usage.output_tokens": 71,
    "gen_ai.usage.cache_read.input_tokens": 0,              // dotted, per spec
    "gen_ai.usage.cache_creation.input_tokens": 0,
    "gen_ai.usage.reasoning.output_tokens": 0,              // recommended when applicable

    // AEP-specific (no upstream equivalent)
    "step": 3,
    "duration_ms": 1430,
    "aep.cost_usd": 0.00098                                 // OTel GenAI hasn't standardized cost as of this writing
  }
}
```

A consumer who has never heard of AEP can still:
- Validate the envelope as a CloudEvent (any CloudEvents library)
- Reconstruct the span tree via `trace_id` / `span_id` / `parent_span_id`
- Read token usage with the same code that handles OpenAI, Gemini, Bedrock telemetry — `gen_ai.provider.name` identifies the backend, `gen_ai.usage.*` carries token counts in the upstream-standard naming
- Treat unknown `aep.*` attributes as opaque extensions (cost, verifier outcomes, AEP-specific lifecycle)

A consumer who DOES know AEP gets, on top: verifier outcomes, boundary
context, the no-mid-run-reach-in promise, and the trajectory's three-class
structure.

---

## How `Config` composes

A Config sent at startup uses three of these specs:

```jsonc
{
  "schema_version": "0.1",
  "run_id": "...",

  // MCP-shaped tool descriptors
  "tools": [
    { "name": "lookup_user",
      "description": "...",
      "inputSchema": { ... } }                     // camelCase per MCP
  ],

  // Agent Skills source-resolution scheme
  "skills": [
    { "name": "domain-glossary",
      "source": "anthropic:domain-glossary@1.0" }, // Anthropic registry
    { "name": "style-guide",
      "source": "./skills/style-guide" }            // filesystem
  ],

  // AEP-specific: verifier, boundary
  "verifiers": [ { "name": "tests-pass", ... } ],
  "boundary":  { "max_cost_usd": 2.0, "max_steps": 30 }
}
```

A Config validates against:
- The AEP `config.schema.json` (whole document)
- MCP tool-descriptor schema (each `tools[]` entry)
- Agent Skills source-resolution scheme (each `skills[]` entry)
- AEP-specific schemas for `verifiers[]` and `boundary` (no upstream)

---

## How `tool_exec_*` composes

Every `tool_exec_request` and `tool_exec_resolved` event carries a
JSON-RPC 2.0 payload as its `data`:

```jsonc
// Request — tool_exec_request.data
{
  "jsonrpc": "2.0",
  "id": "req-7",                                   // = AEP request_id
  "method": "lookup_user",                          // = AEP tool
  "params": { "email": "x@y.z" }                   // = AEP input
}

// Reply — tool_exec_resolved.data
{
  "jsonrpc": "2.0",
  "id": "req-7",
  "result": { "user_id": "u-42", "name": "Alice" }
}

// Error reply
{
  "jsonrpc": "2.0",
  "id": "req-7",
  "error": {
    "code": -32603,                                  // JSON-RPC: internal error
    "message": "lookup failed",
    "data": "no such user"                          // application detail
  }
}
```

A timeout on the supervisor side surfaces in AEP as `tool_exec_timed_out`
(an AEP event, not a JSON-RPC payload — the request never received a
response). The runner's fallback string sent to the model is
`"Error: tool execution timed out after Nms"`, mirroring the §8 `Error: `
prefix convention.

---

## The philosophy

> **Boring infrastructure where possible. Novel contracts where necessary.**

Every spec AEP adopts is one less thing the consumer has to learn, one
more set of tools that already work. CloudEvents libraries already exist
in 12 languages. OTel collectors already integrate with every observability
backend. JSON-RPC libraries are everywhere. MCP servers are proliferating.
Agent Skills has a registry.

We get all of that for free if we put our wire format on top of those
specs. The cost is one renaming pass and a few normative paragraphs in
the spec saying "every AEP event is a CloudEvent; here's the mapping."

What we don't get for free, we earn:

- Verifier as a first-class on-wire concept, with the agent enforcing
  declared rules and the supervisor reading outcomes from the same
  trajectory. **Earned.** No upstream covers this.
- Boundary semantics with the strict-greater rule, exact-N step promise,
  cache-read math, and accounting-reset detection. **Earned.** Policy
  on the wire is novel.
- The trajectory contract — three classes of facts, supervisor RPC replies
  recorded verbatim, runners MUST NOT strip. **Earned.** This is what
  lets a non-technical reviewer answer "did this run respect the
  contract?" without an LLM judge.
- No mid-run reach-in. **Earned.** The architectural constraint is the
  reason trajectories are meaningful.

Adopting standards isn't a humility move. It's a leverage move. The four
AEP-specific concepts above are what the agent-execution case actually
needs that nothing else provides. Everything else is plumbing, and we
should use the plumbing the rest of the industry already uses.

---

## What AEP deliberately does NOT define

To make the bounded-context discipline concrete:

- **Transport beyond stdio + HTTP/SSE (v0.2).** AEP events are
  CloudEvents; use any CloudEvents binding (Kafka, NATS, AMQP, MQTT) if
  you need it. AEP doesn't constrain the transport.
- **Identity / authentication / encryption.** Deployment-layer concerns
  (per `SPEC.md` §14). The transport you pick handles these.
- **Persistence.** Events live in memory per run. If you want a
  trajectory database, build it on top — every event is already a
  CloudEvent and goes through any standard ingestion pipeline.
- **Multi-run orchestration.** AEP describes one run. A supervisor
  framework that schedules and correlates runs across time is a layer
  above AEP.
- **MCP server runtime.** AEP describes tool surfaces in MCP-compatible
  JSON. Whether your tools are backed by an MCP server, an internal
  function, or a remote HTTP service is implementation detail.
- **OTel collector / exporter.** AEP produces span-compatible JSON.
  Plug it into your existing OTel collector if you want; otherwise the
  events are still useful as-is.
- **Skill execution semantics.** AEP records `skill_loaded`. The Agent
  Skills spec defines what the skill body means.

Each of these has a mature spec or convention you can adopt
independently. AEP's job is to compose them coherently for the
agent-execution case, not to subsume them.

---

## Versioning and stability

`schema_version: "0.1"` covers the AEP-specific surface. The upstream
specs we build on have their own versions, pinned in `SPEC.md`:

- CloudEvents: 1.0
- OpenTelemetry GenAI semantic conventions: pinned to a specific upstream
  commit. The conventions are gated by `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`
  in OTel implementations and remain experimental as of v0.1; AEP adopts
  only the attributes that have stabilized (`gen_ai.provider.name`, the
  full `gen_ai.usage.*` family, `gen_ai.tool.*`, `gen_ai.request.model` /
  `gen_ai.response.model`, `gen_ai.operation.name`). When OTel marks
  these stable, AEP drops the "experimental upstream" caveat without a
  wire change.
- JSON-RPC: 2.0
- MCP: latest stable as of `SPEC.md` cut date
- Agent Skills: SKILL.md format v1
- JSON Schema: Draft 2020-12

When upstream specs evolve, AEP's bumps are minor (no wire-breaking
changes within a major version). When AEP-specific surface evolves, AEP's
own version increments. Two independent axes; neither cascades.
