# Foundations — what AVP is built on

> **Thesis.** AVP does not reinvent telemetry, RPC, schemas, or skill formats.
> It specializes existing industry-standard wire formats for the
> agent-execution case. The way MCP specialized JSON-RPC for LLM tools, AVP
> specializes the broader telemetry-and-RPC stack for runs.

The unique work AVP does is small and focused: **the no-mid-run-reach-in
topology, and the trajectory-as-source-of-truth contract.** Everything
else — event envelopes, token/cost telemetry, run
spans, the RPC channel for agent-initiated tool execution, tool descriptors,
skill loading — comes from existing specs that already have ecosystems,
tooling, and documentation.

This document maps each spec we build on to the part of AVP it covers, names
what we deliberately do NOT take from each, and explains how the layers
compose into a single trajectory.

---

## The stack at a glance

```
┌─────────────────────────────────────────────────────────────────┐
│                          AVP v0.1                               │
│  Wire format for agent execution observability + policy         │
└─────────────────────────────────────────────────────────────────┘

  Specializes existing specs (AVP wraps these for the agent case):
  ──────────────────────────────────────────────────────────────────
  CloudEvents 1.0        Event envelopes (every AVP event IS a CloudEvent)
  OTel GenAI sem-conv    Token / cost / model attribute naming
  OTel spans (OTLP)      Run lifecycle as parent-child span hierarchy
  MCP                    Supervisor-side tool dispatch (Commission.mcp_servers)
  Agent Skills           SKILL.md format + skill-source resolution
  JSON Schema 2020-12    Wire-format validation
  RFC 2119 / 8174        Normative-keyword semantics (MUST/SHOULD/MAY)
  ISO 8601 / RFC 3339    Timestamp format

  AVP-specific contributions (no upstream equivalent):
  ──────────────────────────────────────────────────────
  Trajectory contract    Agent-emitted facts are canonical; supervisor
                         observes the NDJSON stream; nothing flows back
  No mid-run reach-in    Architectural constraint declared on the wire:
                         the agent's environment is fully specified at setup
```

---

## What each spec gives us

### CloudEvents 1.0

[CNCF spec](https://cloudevents.io/) for event payloads. Defines a JSON
envelope with required fields (`specversion`, `id`, `source`, `type`) and
optional fields (`subject`, `time`, `datacontenttype`, `data`). Has bindings
for HTTP, MQTT, Kafka, AMQP, NATS — so any AVP trajectory can be transported
on standard event infrastructure without re-encoding.

**What AVP takes:** the event envelope. Every AVP event is a valid CloudEvent.
`type` is reverse-DNS (`avp.model_turn_ended`); `source` is a URI
(`avp://agent` or `avp://supervisor`); `subject` carries `run_id`; `time`
carries the timestamp; `data` carries the AVP-specific payload.

**What AVP does NOT take:** the binary mode, datacontentencoding, or any
specific transport binding. Our base transport is stdio NDJSON; HTTP/SSE is
v0.2.

### OpenTelemetry — GenAI semantic conventions

[OTel semantic conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
define standard attribute names for LLM telemetry. Adopting these means
trajectories are immediately ingestable by any OTel-aware backend
(Datadog, Honeycomb, Tempo, Langfuse, Helicone, Arize, ...) with no custom
adapter.

The conventions AVP adopts (verified against the upstream
`open-telemetry/semantic-conventions` repo):

| Attribute | What it is |
|---|---|
| `gen_ai.provider.name` | Provider id — `anthropic`, `openai`, `aws.bedrock`, `gcp.gemini`, etc. (renamed from the older `gen_ai.system`) |
| `gen_ai.operation.name` | Operation kind — `chat`, `invoke_agent`, `embeddings`, ... |
| `gen_ai.request.model` / `gen_ai.response.model` | Request / response model id |
| `gen_ai.usage.input_tokens` | Total input tokens for the call. Per the spec: "should encompass all input token types, including cached ones" — exactly AVP's convention today. |
| `gen_ai.usage.output_tokens` | Output tokens for the call |
| `gen_ai.usage.cache_read.input_tokens` | Cache-read portion of input (note dotted form, not underscore) |
| `gen_ai.usage.cache_creation.input_tokens` | Cache-creation portion of input |
| `gen_ai.usage.reasoning.output_tokens` | Reasoning-model output tokens (Claude thinking, o-series). Recommended when applicable. |
| `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments` | Tool dispatch attributes |
| `gen_ai.agent.name`, `gen_ai.agent.description` | Subagent identity attributes (used on `subagent_invoked` / `subagent_returned`); per OTel GenAI agent-spans semconv. |
| `gen_ai.response.finish_reasons` | Termination reasons array |
| `gen_ai.request.stream`, `gen_ai.response.time_to_first_chunk` | Streaming-specific attributes |

**What AVP takes:** the attribute namespace. Our token/model/tool fields
are renamed to match. AVP's run-level span uses `gen_ai.operation.name: "invoke_agent"`
(the conventions define both CLIENT and INTERNAL invoke_agent spans).
New per-event attributes that don't have a GenAI equivalent — most
notably **cost** and AVP-specific lifecycle concepts — get the `avp.*`
namespace.

**What AVP does NOT take:** experimental conventions still flagged as
unstable. The GenAI conventions overall are still under the
`gen_ai_latest_experimental` stability flag (consumers opt in via
`OTEL_SEMCONV_STABILITY_OPT_IN`); AVP `SPEC.md` pins a specific
upstream commit and only adopts attributes whose names have stabilized.

**On cost specifically:** OTel has not standardized a cost attribute as
of this writing (verified against the live spec repo). AVP keeps cost
in the `avp.*` namespace as `avp.cost_usd`. When upstream standardizes
a name (e.g., `gen_ai.usage.cost`), AVP adopts it in the next minor
version and aliases the old field for one release.

### OpenTelemetry — OTLP / spans

[OTLP](https://opentelemetry.io/docs/specs/otlp/) defines the wire format
for spans (and metrics, logs). Spans are the canonical "thing that happened
over an interval" — they have `trace_id`, `span_id`, `parent_span_id`,
`start_time`, `end_time`, `attributes`, `events`, and `status`.

**What AVP takes:** the span identification model. Every AVP event carries
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

**What AVP does NOT take:** the OTel SDK at runtime. We are a producer of
span-shaped JSON, not a span exporter. Consumers who want spans in
Datadog/etc. use their own collector. AVP introduces zero infrastructure
dependencies.

### MCP (Model Context Protocol)

[MCP](https://modelcontextprotocol.io/) is built on JSON-RPC 2.0. It
specifies how an LLM client talks to a server that exposes tools, resources,
and prompts. v0.1 of AVP uses MCP as its **only** mechanism for
supervisor-side tool dispatch.

**What AVP takes:** MCP server descriptors and the connection lifecycle.
`Commission.mcp_servers[]` declares servers (stdio or HTTP, in-process or
external) the agent connects to at startup. The agent runs MCP's
`initialize` + `tools/list`, surfaces the live tool catalog on
`mcp_server_connected.data.avp.mcp.tools[]`, and dispatches model tool
calls against the server using MCP's `tools/call`. The
`tool_invoked` / `tool_returned` AVP events tag the dispatch with
`avp.tool.dispatch_target = "mcp_server"` and `avp.mcp_server_id` so
consumers can filter.

**What AVP does NOT take:** MCP's server protocol internals. AVP doesn't
re-implement MCP; the agent uses an off-the-shelf MCP client (the
provider SDK already ships one). Supervisors that want to expose Python,
shell, or HTTP-backed tools wrap them in an MCP server — there is no
AVP-flavored RPC alternative.

### Agent Skills

[Agent Skills](https://agentskills.io/specification) defines the SKILL.md
format: YAML frontmatter (`name`, `description`) plus markdown body
describing what the skill does and how to use it. Distribution is via
filesystem paths, HTTPS URLs, or a registry scheme (e.g., `anthropic:<id>@<version>`).

**What AVP takes:** the SKILL.md format and the source-resolution scheme.
`Commission.skills[]` entries are `{name, source, config?}` where `source`
is one of: `anthropic:<id>@<version>`, an HTTPS URL, or a filesystem path.
Agents load the SKILL.md, expose it to the agent, and emit `skill_loaded`
into the trajectory. The repo's own [`SKILL.md`](./SKILL.md) is a worked
example.

**What AVP does NOT take:** skill execution semantics. AVP records that a
skill was loaded; whether and how the agent uses it is between the agent
and the skill.

### JSON Schema 2020-12

Standard schema for declarative JSON validation. Used throughout AVP for
both the wire schema bundle (`spec/v0.1/avp.schema.json`) and tool
`inputSchema` fields.

**What AVP takes:** Draft 2020-12 with `$ref` resolution. Already a
dependency.

**What AVP does NOT take:** schema dialects other than 2020-12. We require
exactly that draft.

### RFC 2119 / 8174

Normative keywords (MUST, SHOULD, MAY, MUST NOT, SHOULD NOT). Standard for
conformance language in protocol specs.

**What AVP takes:** the keyword vocabulary. Used throughout `SPEC.md` to
distinguish hard requirements from recommendations.

### ISO 8601 / RFC 3339

Standard timestamp format. UTC-suffixed (`Z`) recommended.

---

## What AVP specializes (the actual contribution)

These two concepts have no equivalent in any of the upstream specs.
They're AVP's reason for existing.

### Trajectory contract

The agent's stdout is the canonical record. Two classes of facts are
declared distinct: what the agent did, what the run cost. Supervisor
RPC replies are recorded verbatim into the same stream. Implementations
MUST NOT strip or rewrite supervisor-emitted records.

OTel has trace export pipelines but the canonicality model is different —
spans flow to a backend and are queried. AVP makes the trajectory itself
the truth, not a derived view of it.

### No mid-run reach-in

The supervisor declares the environment in a Commission sent at startup and
observes the trajectory. It does not reach in mid-run. The agent's
environment is fully specified up front.

This is an architectural constraint expressed as a wire constraint: there
is no supervisor → agent channel beyond the one-shot Commission. Tools the
agent calls dispatch through MCP (a separate protocol the agent connects
out to); the supervisor never pushes messages to the agent mid-run.
This is what makes trajectories meaningful: every fact in the record was
produced by either agent action or an MCP server the agent called, not
by a controller pushing in unilateral decisions.

---

## How the layers compose: one event walked through

A `model_turn_ended` event illustrates every layer:

```jsonc
{
  // CloudEvents 1.0 envelope
  "specversion": "1.0",
  "id": "ev-7f3a-0042",
  "source": "avp://agent",
  "type": "avp.model_turn_ended",
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

    // AVP-specific (no upstream equivalent)
    "step": 3,
    "duration_ms": 1430,
    "avp.cost_usd": 0.00098                                 // OTel GenAI hasn't standardized cost as of this writing
  }
}
```

A consumer who has never heard of AVP can still:
- Validate the envelope as a CloudEvent (any CloudEvents library)
- Reconstruct the span tree via `trace_id` / `span_id` / `parent_span_id`
- Read token usage with the same code that handles OpenAI, Gemini, Bedrock telemetry — `gen_ai.provider.name` identifies the backend, `gen_ai.usage.*` carries token counts in the upstream-standard naming
- Treat unknown `avp.*` attributes as opaque extensions (cost, AVP-specific lifecycle)

A consumer who DOES know AVP gets, on top: the no-mid-run-reach-in
promise and the trajectory's two-class structure.

---

## How `Commission` composes

A Commission sent at startup uses three of these specs:

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

  // AVP-specific Subagent primitive — model-facing surface is MCP-shaped
  // (name, description, inputSchema), so the model sees subagents the same
  // way it sees tools. The wire surfaces them as their own lifecycle
  // (subagent_invoked / subagent_returned) so nested runs observe as a
  // span tree instead of flattening into a single tool_use → tool_result.
  "subagents": [
    { "name": "summarizer",
      "description": "Compresses a passage to bullets.",
      "system_prompt": "You are a precise summarizer.",
      "model": "claude-haiku-4-5-20251001" }
  ]
}
```

A Commission validates against:
- The AVP `commission.schema.json` (whole document)
- MCP server descriptor shape (each `mcp_servers[]` entry)
- Agent Skills source-resolution scheme (each `skills[]` entry)
- AVP-specific schema for `subagents[]` (no upstream)

---

## How tool dispatch composes

v0.1 has two paths for any tool the model can call:

1. **Agent-built-in.** Compiled into the agent package; declared on the
   agent's manifest (`agent_described.data.avp.agent.built_in_tools`).
   The agent runs the implementation in-process. AVP events:
   `tool_invoked` with `avp.tool.dispatch_target = "local"` →
   `tool_returned`.

2. **MCP-server tool.** Supervisor declares an MCP server in
   `Commission.mcp_servers[]`. The agent uses an off-the-shelf MCP client
   to connect, list tools, and dispatch `tools/call`. AVP events:
   `mcp_server_connected` with the live tool catalog after handshake;
   `tool_invoked` / `tool_returned` for each model invocation, tagged
   `avp.tool.dispatch_target = "mcp_server"` and `avp.mcp_server_id`.
   `mcp_server_disconnected` on close.

There is no AVP-flavored RPC channel between supervisor and agent. The
supervisor's mid-run job is purely reading the NDJSON event stream;
anything they want the model to call is wrapped as an MCP server.

---

## The philosophy

> **Boring infrastructure where possible. Novel contracts where necessary.**

Every spec AVP adopts is one less thing the consumer has to learn, one
more set of tools that already work. CloudEvents libraries already exist
in 12 languages. OTel collectors already integrate with every observability
backend. JSON-RPC libraries are everywhere. MCP servers are proliferating.
Agent Skills has a registry.

We get all of that for free if we put our wire format on top of those
specs. The cost is one renaming pass and a few normative paragraphs in
the spec saying "every AVP event is a CloudEvent; here's the mapping."

What we don't get for free, we earn:

- Agent self-description as a first-class on-wire concept (`agent_described`
  + `Commission.allowed_tools`). The agent declares its capability surface
  upfront so the supervisor and a non-technical reviewer can both read the
  trajectory without an out-of-band manifest. **Earned.** No upstream covers
  this.
- The trajectory contract — supervisor declares environment in Commission,
  agent emits the run, agent MUST NOT strip. **Earned.** This is what lets
  a reviewer answer "did this run respect the contract?" without an LLM
  judge.
- No mid-run reach-in. **Earned.** The architectural constraint is the
  reason trajectories are meaningful.

Adopting standards isn't a humility move. It's a leverage move. The
AVP-specific concepts above are what the agent-execution case actually
needs that nothing else provides. Everything else is plumbing, and we
should use the plumbing the rest of the industry already uses.

---

## What AVP deliberately does NOT define

To make the bounded-context discipline concrete:

- **Transport beyond stdio + HTTP/SSE (v0.2).** AVP events are
  CloudEvents; use any CloudEvents binding (Kafka, NATS, AMQP, MQTT) if
  you need it. AVP doesn't constrain the transport.
- **Identity / authentication / encryption.** Deployment-layer concerns
  (per `SPEC.md` §14). The transport you pick handles these.
- **Persistence.** Events live in memory per run. If you want a
  trajectory database, build it on top — every event is already a
  CloudEvent and goes through any standard ingestion pipeline.
- **Multi-run orchestration.** AVP describes one run. A supervisor
  framework that schedules and correlates runs across time is a layer
  above AVP.
- **MCP server runtime.** AVP describes tool surfaces in MCP-compatible
  JSON. Whether your tools are backed by an MCP server, an internal
  function, or a remote HTTP service is implementation detail.
- **OTel collector / exporter.** AVP produces span-compatible JSON.
  Plug it into your existing OTel collector if you want; otherwise the
  events are still useful as-is.
- **Skill execution semantics.** AVP records `skill_loaded`. The Agent
  Skills spec defines what the skill body means.

Each of these has a mature spec or convention you can adopt
independently. AVP's job is to compose them coherently for the
agent-execution case, not to subsume them.

---

## Versioning and stability

`schema_version: "0.1"` covers the AVP-specific surface. The upstream
specs we build on have their own versions, pinned in `SPEC.md`:

- CloudEvents: 1.0
- OpenTelemetry GenAI semantic conventions: pinned to a specific upstream
  commit. The conventions are gated by `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`
  in OTel implementations and remain experimental as of v0.1; AVP adopts
  only the attributes that have stabilized (`gen_ai.provider.name`, the
  full `gen_ai.usage.*` family, `gen_ai.tool.*`, `gen_ai.request.model` /
  `gen_ai.response.model`, `gen_ai.operation.name`). When OTel marks
  these stable, AVP drops the "experimental upstream" caveat without a
  wire change.
- JSON-RPC: 2.0
- MCP: latest stable as of `SPEC.md` cut date
- Agent Skills: SKILL.md format v1
- JSON Schema: Draft 2020-12

When upstream specs evolve, AVP's bumps are minor (no wire-breaking
changes within a major version). When AVP-specific surface evolves, AVP's
own version increments. Two independent axes; neither cascades.
