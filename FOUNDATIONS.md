# Foundations: what AVP is built on

> **Thesis.** AVP (Agent Voyager **Project**) does not reinvent telemetry,
> RPC, schemas, or skill formats. It specializes existing industry-standard
> wire formats for the agent-execution case. The way MCP specialized
> JSON-RPC for LLM tools, AVP specializes the broader telemetry-and-RPC
> stack for runs.

AVP is a **collection of specs**, not a single protocol. There are
three data-shape specs (Trajectory, Commission, Agent Descriptor) and one
wire-level protocol (Resolver). Each is implementable independently and
references how it composes with the others; this document describes the
upstream specs they build on and the AVP-specific contributions that sit
on top.

The unique work AVP does is small and focused: **the no-mid-run-reach-in
topology, the trajectory-as-source-of-truth contract, and a minimal
agent-initiated Resolver API that lets the supervisor manage opaque
asset refs without leaking material onto the wire.** Everything else
(event envelopes, token/cost telemetry, run spans, JSON-RPC framing,
tool descriptors, skill loading) comes from existing specs that already
have ecosystems, tooling, and documentation.

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
  JSON-RPC 2.0           Resolver protocol (avp.resolve, avp.spawn_subagent)
  MCP                    Supervisor-side tool dispatch (resolved from refs)
  Agent Skills           SKILL.md format (content resolved from refs)
  JSON Schema 2020-12    Wire-format validation
  RFC 2119 / 8174        Normative-keyword semantics (MUST/SHOULD/MAY)
  ISO 8601 / RFC 3339    Timestamp format

  AVP-specific contributions (no upstream equivalent):
  ──────────────────────────────────────────────────────
  Trajectory contract    Agent-emitted facts are canonical; supervisor
                         observes the NDJSON stream; no push channel back
  No mid-run reach-in    Architectural constraint declared on the wire:
                         the Commission specifies the full environment at
                         setup. Runtime resolution of opaque refs is
                         agent-initiated and recorded on the trajectory.
  Resolver protocol      Agent calls avp.resolve / avp.spawn_subagent
                         against a supervisor-stood-up service to
                         dereference Commission asset refs without leaking
                         connection material onto the wire.
```

---

## What each spec gives us

### CloudEvents 1.0

[CNCF spec](https://cloudevents.io/) for event payloads. Defines a JSON
envelope with required fields (`specversion`, `id`, `source`, `type`) and
optional fields (`subject`, `time`, `datacontenttype`, `data`). Has bindings
for HTTP, MQTT, Kafka, AMQP, NATS, so any AVP trajectory can be transported
on standard event infrastructure without re-encoding.

**What AVP takes:** the event envelope. Every AVP event is a valid CloudEvent.
`type` is reverse-DNS (`avp.model_turn_ended`); `source` is a URI
(`avp://agent` or `avp://supervisor`); `subject` carries `run_id`; `time`
carries the timestamp; `data` carries the AVP-specific payload.

**What AVP does NOT take:** the binary mode, datacontentencoding, or any
specific transport binding. Our base transport is stdio NDJSON; HTTP/SSE is
v0.2.

### OpenTelemetry: GenAI semantic conventions

[OTel semantic conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
define standard attribute names for LLM telemetry. Adopting these means
trajectories are immediately ingestable by any OTel-aware backend
(Datadog, Honeycomb, Tempo, Langfuse, Helicone, Arize, ...) with no custom
adapter.

The conventions AVP adopts (verified against the upstream
`open-telemetry/semantic-conventions` repo):

| Attribute | What it is |
|---|---|
| `gen_ai.provider.name` | Provider id: `anthropic`, `openai`, `aws.bedrock`, `gcp.gemini`, etc. (renamed from the older `gen_ai.system`) |
| `gen_ai.operation.name` | Operation kind: `chat`, `invoke_agent`, `embeddings`, ... |
| `gen_ai.request.model` / `gen_ai.response.model` | Request / response model id |
| `gen_ai.usage.input_tokens` | Total input tokens for the call. Per the spec: "should encompass all input token types, including cached ones", exactly AVP's convention today. |
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
New per-event attributes that don't have a GenAI equivalent (most
notably **cost** and AVP-specific lifecycle concepts) get the `avp.*`
namespace.

**What AVP does NOT take:** experimental conventions still flagged as
unstable. The GenAI conventions overall are still under the
`gen_ai_latest_experimental` stability flag (consumers opt in via
`OTEL_SEMCONV_STABILITY_OPT_IN`); the AVP specs pin a specific
upstream commit and only adopt attributes whose names have stabilized.

**On cost specifically:** OTel has not standardized a cost attribute as
of this writing (verified against the live spec repo). AVP keeps cost
in the `avp.*` namespace as `avp.cost_usd`. When upstream standardizes
a name (e.g., `gen_ai.usage.cost`), AVP adopts it in the next minor
version and aliases the old field for one release.

### OpenTelemetry: OTLP / spans

[OTLP](https://opentelemetry.io/docs/specs/otlp/) defines the wire format
for spans (and metrics, logs). Spans are the canonical "thing that happened
over an interval"; they have `trace_id`, `span_id`, `parent_span_id`,
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

The wire stays flat NDJSON (events stream one per line), but the IDs let
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

**What AVP takes:** the connection lifecycle. `Commission.mcp_servers[]`
declares servers as opaque `{id, ref}` pairs; the agent calls
`avp.resolve` (the AVP Resolver API, see below) at startup to get
back the connection material the supervisor wants the agent to use. The
agent then runs MCP's `initialize` + `tools/list` against the resolved
endpoint, surfaces the live tool catalog on
`mcp_server_connected.data.avp.mcp.tools[]`, and dispatches model tool
calls using MCP's `tools/call`. The `tool_invoked` / `tool_returned` AVP
events tag the dispatch with `avp.tool.dispatch_target = "mcp_server"`
and `avp.mcp_server_id` so consumers can filter.

**What AVP does NOT take:** MCP's server protocol internals. AVP doesn't
re-implement MCP; the agent uses an off-the-shelf MCP client (the
provider SDK already ships one). Supervisors that want to expose Python,
shell, or HTTP-backed tools wrap them in an MCP server, register the
server with their resolver under whatever opaque ref shape they prefer,
and let the agent dereference at startup.

### JSON-RPC 2.0 (the AVP Resolver API)

[JSON-RPC 2.0](https://www.jsonrpc.org/specification) is a lightweight
remote-procedure-call envelope (`id`, `method`, `params`, `result` /
`error`). MCP itself is built on it; AVP reuses the same envelope for one
small purpose of its own.

**What AVP takes:** the envelope and method-call shape, for two methods
the agent calls against a supervisor-stood-up resolver service:

- `avp.resolve`: startup-only. Dereferences each opaque ref in
  `Commission.{mcp_servers,skills,subagents}[]` into the connection
  material / content / metadata the agent actually uses.
- `avp.spawn_subagent`: on-demand. Invokes a supervisor-managed
  subagent at the moment the parent's model picks it; returns the child
  run's `run_id` plus an inline result summary.

The agent learns the resolver's location from the `AVP_RESOLVER_URL`
environment variable; auth/transport are deployment-layer choices outside
the protocol. The agent → resolver direction is the only point where AVP
crosses the supervisor↔agent trust boundary at runtime, and it is always
agent-initiated. There is no resolver → agent push.

**What AVP does NOT take:** JSON-RPC's batch mode, named parameters as a
distinguishing feature (positional and named are both legal per spec,
AVP uses an object-shaped `params` consistently), or RPC-level error
classification (the resolver returns whatever JSON-RPC error code makes
sense; the agent fails the run with `managed_ref_resolve_failed` for any
non-success).

### Agent Skills

[Agent Skills](https://agentskills.io/specification) defines the SKILL.md
format: YAML frontmatter (`name`, `description`) plus markdown body
describing what the skill does and how to use it.

**What AVP takes:** the SKILL.md format. `Commission.skills[]` entries
are opaque `{id, ref}` pairs the agent dereferences via the resolver
protocol; the resolver returns SKILL.md content (or a location the agent
fetches), and the agent loads it into the model's context per
agentskills.io semantics. The agent emits `skill_loaded` into the
trajectory. The repo's own [`SKILL.md`](./SKILL.md) is a worked example.

**What AVP does NOT take:** source-resolution schemes. agentskills.io
describes filesystem / HTTPS / registry distribution; AVP stays
deliberately one level up. The supervisor's resolver knows where each
ref points, and the agent doesn't need to.

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

**What AVP takes:** the keyword vocabulary. Used throughout the specs
(`spec/v0.1/{trajectory,commission,agent-descriptor,resolver}.md`) to
distinguish hard requirements from recommendations.

### ISO 8601 / RFC 3339

Standard timestamp format. UTC-suffixed (`Z`) recommended.

---

## What AVP specializes (the actual contribution)

These two concepts have no equivalent in any of the upstream specs.
They're AVP's reason for existing.

### Trajectory contract

The agent's stdout is the canonical record. Two classes of facts are
declared distinct: what the agent did, what the run cost. Implementations
MUST NOT strip or rewrite events; consumers reading the NDJSON stream see
exactly what the agent emitted.

OTel has trace export pipelines but the canonicality model is different:
spans flow to a backend and are queried. AVP makes the trajectory itself
the truth, not a derived view of it.

### No mid-run reach-in

The supervisor declares the environment in a Commission sent at startup and
observes the trajectory. It does not push anything else to the agent
mid-run. The agent's environment is fully specified up front, even when
some of it is opaque-ref-shaped: the agent dereferences refs at startup
via the resolver, recording each round-trip as a `managed_ref_resolved`
event before any model turn.

This is an architectural constraint expressed as a wire constraint:
there is no supervisor → agent push channel. Runtime asset resolution
crosses the trust boundary in the agent → supervisor-service direction
only, which AVP records on the trajectory. Tools the agent calls
dispatch through MCP (a separate protocol the agent connects out to,
against an endpoint resolved from the Commission). This is what makes
trajectories meaningful: every fact in the record was produced by agent
action (a model turn, a tool call, a resolver call, or a self-described
lifecycle event), not by a controller pushing in unilateral decisions.

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
    // OTel span identification: lets a collector rebuild the tree
    "trace_id": "5b8efff798038103d269b633813fc60c",
    "span_id": "eee19b7ec3c1b173",
    "parent_span_id": "0000000000000001",          // top-level run span

    // OTel GenAI semantic conventions, recognizable to any GenAI backend
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
- Validate the envelope as a CloudEvent (any CloudEvents library).
- Reconstruct the span tree via `trace_id` / `span_id` / `parent_span_id`.
- Read token usage with the same code that handles OpenAI, Gemini, Bedrock telemetry. `gen_ai.provider.name` identifies the backend, `gen_ai.usage.*` carries token counts in the upstream-standard naming.
- Treat unknown `avp.*` attributes as opaque extensions (cost, AVP-specific lifecycle).

A consumer who DOES know AVP gets, on top: the no-mid-run-reach-in
promise and the trajectory's two-class structure.

---

## How `Commission` composes

A Commission sent at startup is small and uniform. Every supervisor-managed
asset is an opaque `{id, ref}` pair. The supervisor's resolver knows what
each ref means; the agent does not. AVP doesn't constrain the shape of
`ref` (it's `JsonValue`); each supervisor picks whatever its resolver
understands.

```jsonc
{
  "schema_version": "0.1",
  "run_id": "...",
  "model": "claude-sonnet-4-6",
  "prompt": "Refactor the auth module to use JWT.",

  // Each entry is an opaque handle the agent dereferences via avp.resolve.
  // Shape of `ref` is whatever the supervisor's resolver understands.
  "mcp_servers": [
    { "id": "github", "ref": { "vault": "prod", "key": "gh-mcp-v2" } }
  ],

  "skills": [
    { "id": "xlsx", "ref": { "type": "anthropic", "skill_id": "xlsx" } },
    { "id": "ours", "ref": "sha256:abc..." }                  // string ref
  ],

  "subagents": [
    { "id": "researcher", "ref": "sk_subagent_abc123" }       // string ref
  ]
}
```

A Commission validates against `commission.schema.json` (whole document).
The per-`kind` *result* schemas (what `avp.resolve` returns for an MCP
server vs a skill vs a subagent) are described in
[`spec/v0.1/resolver.md`](spec/v0.1/resolver.md) §3.2 and are where the
upstream specs (MCP for connection material, agentskills.io for skill
content) actually surface. The Commission itself stays
implementation-neutral.

---

## How tool dispatch composes

v0.1 has two paths for any tool the model can call:

1. **Agent-built-in.** Compiled into the agent package; declared on the
   agent's Descriptor (`agent_described.data.avp.descriptor.built_in_tools`).
   The agent runs the implementation in-process. AVP events:
   `tool_invoked` with `avp.tool.dispatch_target = "local"` →
   `tool_returned`.

2. **MCP-server tool.** Supervisor declares an MCP server in
   `Commission.mcp_servers[]` as `{id, ref}`. At startup the agent calls
   `avp.resolve` to dereference the ref into connection material, then
   uses an off-the-shelf MCP client to connect, list tools, and dispatch
   `tools/call`. AVP events: `managed_ref_resolved` for the resolution
   round-trip, `mcp_server_connected` with the live tool catalog after
   the MCP handshake, `tool_invoked` / `tool_returned` for each model
   invocation tagged `avp.tool.dispatch_target = "mcp_server"` and
   `avp.mcp_server_id`, `mcp_server_disconnected` on close.

There is no AVP-flavored RPC channel between supervisor and agent for
mid-run state. The supervisor's mid-run job is purely reading the NDJSON
event stream; anything they want the model to call is wrapped as an MCP
server and pointed at by a Commission ref.

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
  with `avp.descriptor`). The agent declares its capability surface upfront,
  including whether it speaks the Resolver API, so the supervisor
  and a non-technical reviewer can both read the trajectory without an
  out-of-band Descriptor. **Earned.** No upstream covers this.
- The trajectory contract: supervisor declares environment in Commission,
  agent emits the run, agent MUST NOT strip. **Earned.** This is what lets
  a reviewer answer "did this run respect the contract?" without an LLM
  judge.
- No mid-run supervisor → agent push. **Earned.** The architectural
  constraint is the reason trajectories are meaningful.
- Opaque managed-asset refs plus a tiny Resolver API. **Earned.** The
  Commission stays material-free (auditable without secret redaction)
  while still letting a supervisor platform manage MCP servers, skills,
  and subagents centrally.

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
  (per [`spec/v0.1/README.md`](spec/v0.1/README.md) §6). The transport you pick handles these. The resolver
  service the agent dials is configured by the supervisor through the
  `AVP_RESOLVER_URL` env var (and any auth env vars the supervisor sets);
  AVP doesn't constrain its auth model.
- **Persistence.** Events live in memory per run. If you want a
  trajectory database, build it on top; every event is already a
  CloudEvent and goes through any standard ingestion pipeline.
- **Multi-run orchestration.** AVP describes one run. A supervisor
  framework that schedules and correlates runs across time is a layer
  above AVP. (Supervisor-managed subagents are an exception: the parent's
  `subagent_invoked.data["avp.subagent.run_id"]` references a child run
  the supervisor commissions independently. Consumers correlate the two
  trajectories via that field.)
- **Resolver hosting.** Where `AVP_RESOLVER_URL` points, how the
  resolver authenticates, how it scales. Same trust boundary as the
  agent process; the supervisor stands both up and configures their
  connection.
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

## Adjacent prior art: ATIF (Harbor's trajectory format)

The [Harbor framework](https://github.com/harbor-framework/harbor) ships
the **Agent Trajectory Interchange Format (ATIF)**, a JSON document
format for logging the complete interaction history of autonomous LLM
agents, designed for SFT/RL training pipelines, replay, and debugging.
ATIF and AVP Trajectory share the word "trajectory" but solve different
problems:

| | Harbor ATIF | AVP Trajectory |
|---|---|---|
| **Unit** | One JSON document per run | A stream of events during a run |
| **Lifecycle** | Post-hoc artifact (written after the run completes) | Live (emitted as the run executes) |
| **Primary consumer** | SFT/RL training pipelines, replay, debugging | Supervisors observing/auditing runs in real time |
| **Step granularity** | One step per LLM call (user/system/agent turn) | Multiple events per turn (`model_turn_started`, `text_emitted`, `tool_invoked/returned`, `cost_recorded`, `model_turn_ended`) |
| **Time model** | Optional ISO timestamps per step | Strict event ordering, CloudEvents `time` per event |
| **Identifiers** | `session_id` (run) + `trajectory_id` (document) | OTel `trace_id` / `span_id` / `parent_span_id` |
| **Cost** | Absolute per step, totals in `final_metrics` | Monotonic-cumulative on each `cost_recorded` |
| **Subagents** | Inline-embed full child trajectories or external file ref | Correlate by `avp.subagent.run_id` (child has its own event stream) |
| **Standards anchoring** | Bespoke schema | CloudEvents 1.0 + OTel GenAI + OTel spans |
| **RL/SFT extras** | Logprobs, token IDs, `reasoning_effort` | Out of scope |

ATIF and AVP Trajectory are **complementary**. ATIF is a great format
for downstream training-data needs; AVP Trajectory is a great format for
live observation that piggybacks on the OpenTelemetry / CloudEvents
ecosystem (any OTel collector or CloudEvents broker already understands
the wire). A future minor revision could spec an AVP→ATIF conversion for
producing training corpora from captured AVP event streams; that's not
v0.1 scope.

---

## Versioning and stability

`schema_version: "0.1"` covers the AVP-specific surface. The upstream
specs we build on have their own versions, pinned in the specs and
the umbrella [`spec/v0.1/README.md`](spec/v0.1/README.md):

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
- MCP: latest stable as of v0.1 cut date
- Agent Skills: SKILL.md format v1
- JSON Schema: Draft 2020-12

When upstream specs evolve, AVP's bumps are minor (no wire-breaking
changes within a major version). When AVP-specific surface evolves, AVP's
own version increments. Two independent axes; neither cascades.
