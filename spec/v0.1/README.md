# AVP v0.1 Specifications

**Status:** Draft
**Umbrella version:** v0.1
**$id base:** `https://avp.dev/schema/v0.1/`

This directory is the **normative specification** for v0.1 of the Agent Voyager Project (AVP). AVP is a collection of four specs that compose into a coherent wire format for the agent-execution case:

| Sub-spec | Kind | What it defines | File |
|---|---|---|---|
| **AVP Trajectory** | Data-shape spec | The event stream: CloudEvents envelope, OTel span/GenAI attrs, event-type catalog, ordering/pairing invariants, the agent loop algorithm | [`trajectory.md`](./trajectory.md) |
| **AVP Commission** | Data-shape spec | The run-config object: prompt, model, refs-only managed assets, `enabled_builtin_*` allowlist semantics | [`commission.md`](./commission.md) |
| **AVP Agent Descriptor** | Data-shape spec | What an agent advertises pre-flight: built-in tool/subagent/skill catalogs, capabilities, supported models | [`agent-descriptor.md`](./agent-descriptor.md) |
| **AVP Resolver API** | Protocol | JSON-RPC 2.0 methods (`avp.resolve`, `avp.spawn_subagent`) for dereferencing managed-asset refs against a supervisor-stood-up service | [`resolver.md`](./resolver.md) |

The three data-shape specs are independent; each can be adopted on its own. The Resolver API is the only spec that defines wire-level request/response between two parties, and depends on Commission (the refs it dereferences live there).

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in every spec are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

---

## 0. Built on

AVP specializes (it does not reinvent) the following industry specs:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`, `source`, `type`, `subject`, `time`, `datacontenttype`, `data`).
- **OpenTelemetry GenAI semantic conventions** for token / cost / model / tool attribute names inside `data` (e.g., `gen_ai.usage.input_tokens`, `gen_ai.tool.name`).
- **OpenTelemetry span identification** (`trace_id`, `span_id`, `parent_span_id`) on every event so trajectories reconstruct as a span tree.
- **JSON-RPC 2.0** for the AVP Resolver API. Agent → resolver service calls (`avp.resolve`, `avp.spawn_subagent`) that dereference opaque refs in the Commission.
- **MCP 2025-11-25** for supervisor-side tool dispatch. Commission entries in `mcp_servers[]` are opaque refs the agent resolves into MCP connection material; the agent then runs MCP's `initialize` + `tools/list` and dispatches `tools/call` against the live server. AVP doesn't redefine the MCP wire; it just references the asset and observes the dispatch.
- **Agent Skills** (agentskills.io) for `SKILL.md` content. Commission `skills[]` entries are refs; the resolver returns SKILL.md content (or a location to fetch).
- **JSON Schema Draft 2020-12** for this specification's machine-readable form.

AVP-specific concepts (the **no-mid-run-reach-in topology** and the **trajectory-as-source-of-truth contract**) live under the `avp.*` attribute namespace. See [`../../FOUNDATIONS.md`](../../FOUNDATIONS.md) for the full mapping rationale and ATIF (Harbor) positioning.

---

## 1. The seam

AVP defines exactly one seam, between two roles, with **two unidirectional flows** crossing it, plus **one agent-initiated callback** to a supervisor-stood-up resolver service:

- **Supervisor**: declares a Commission at startup with the prompt, model, and supervisor-managed assets (`mcp_servers`, `skills`, `subagents`) as opaque refs. Once the Commission is sent, the supervisor observes the trajectory; it does not push anything else to the agent.
- **Agent**: runs inside the Commission. Calls the supervisor's resolver service (Resolver API) at startup to dereference managed refs into connection material. Emits a stream of facts (events), the trajectory, that the supervisor observes.

```
   supervisor  ──────── Commission ─────────▶  agent
                                                 │
                                                 │  resolves managed refs at
                                                 │  startup via avp.resolve
                                                 │  to a supervisor-stood-up
                                                 │  resolver service
                                                 │
                                                 │  runs the run, emits events
                                                 ▼
   supervisor  ◀──────── trajectory ─────────  agent
```

This is the v0.1 architectural choice: **the supervisor configures, the agent runs, the trajectory is the truth.** No mid-run supervisor → agent push channel. The agent's bounded context is intact because its environment was fully specified up front; runtime resolution of opaque refs is agent-initiated, scoped to startup, and recorded on the trajectory as `managed_ref_resolved` / `managed_ref_resolve_failed` events.

What an agent provides on its own (built-in tools, baked-in skills, in-process subagent definitions) is invisible to AVP and the Commission. It surfaces only on the agent's Descriptor (`agent_described.data["avp.descriptor"]`), which the supervisor and any auditor can read on the trajectory's second event.

---

## 2. Message classes

| Class | Direction | Cardinality | Sub-spec |
|---|---|---|---|
| `Commission` | supervisor → agent | exactly one, at startup | [Commission](./commission.md) |
| `Event` | agent → supervisor | streamed throughout the run | [Trajectory](./trajectory.md) |
| `avp.resolve` / `avp.spawn_subagent` (request / response) | agent ↔ resolver service | per managed ref / per managed subagent invocation | [Resolver API](./resolver.md) |

v0.1 has no supervisor → agent push channel.

---

## 3. Transport

AVP is transport-agnostic for the Commission / event pipe. The three data-shape specs (Commission, Trajectory, Agent Descriptor) describe JSON document shapes; how those bytes move between supervisor and agent is a deployment concern. Subprocess pipes, HTTP, Server-Sent Events, a message bus, an in-process callback: any of these can carry a Commission in and trajectory events out, as long as the JSON on the wire matches the spec schemas.

The Resolver API is the one exception: it IS a wire protocol (JSON-RPC 2.0 over HTTP/HTTPS/unix-socket) because it's a runtime request/response service the agent dials. See [`resolver.md`](./resolver.md) §1.

### 3.1 Reference binding: stdio

The reference implementations in this repo use stdio as their concrete transport binding. It's the simplest credible thing to ship (containerized agents, CLI tools, per-run subprocess invocations) and every supervisor that can spawn a process can speak it. Implementers using stdio SHOULD follow these rules so trajectories captured this way are interchangeable:

- The supervisor launches the agent as a subprocess.
- The supervisor writes a single `Commission` JSON document to the agent's stdin, terminated by `\n`.
- The agent reads exactly one `Commission` from stdin before emitting any events.
- After reading `Commission`, stdin is unused.
- The agent emits `Event` documents to stdout as NDJSON, one JSON object per line, no pretty-printing, terminated by `\n`. The agent flushes stdout after each line.

Implementers using any other transport (HTTP+SSE, gRPC streaming, Kafka, in-process) are not constrained by AVP beyond preserving the JSON shapes the specs define.

---

## 4. Custom event types and vendor extensions

Any `type` value not in the `avp.*` namespace is a custom event. Implementations MAY emit custom events. Consumers MUST:

- Validate them against the CloudEvents 1.0 envelope shape: `specversion`, `id`, `source`, `type`, `time`, `data` MUST be present.
- Pass them through without error if they do not recognize the `type`.

Implementers SHOULD use reverse-DNS `type` values (e.g. `com.example.deploy_completed`) to avoid future conflicts. The `avp.*` namespace is reserved.

For **non-spec fields within a known event type**: place them inside `data` under a vendor-namespaced key (e.g., `vendor.priority`, `acme.region`). The reference parser allows extra keys to round-trip through `data` verbatim, so vendor extensions don't require a separate envelope.

---

## 5. Verifiers (deferred)

v0.1 does not specify verifiers. The deterministic-checks-at-trigger-points concept was carried in early drafts and is removed here so v0.1 stays narrowly focused on observation and tool dispatch. A future revision may reintroduce verifiers (or a slimmer "pre-tool gate" surface) once the wire-level shape has settled. Until then, supervisors that want gating wire it externally by running the agent inside a constrained workspace, by exposing only safe MCP servers in the Commission, or by reviewing the trajectory after the fact.

---

## 6. Deployment scope

AVP defines the **wire format**, not the deployment topology. The following are explicitly **out of scope**, and implementations choose:

- **Workspace provisioning.** What directory the agent runs in, how files (reference data, source trees) get there, and how it's cleaned up after (git checkout, container volume mount, tmpdir, NFS share, etc).
- **Secret injection.** How API keys and credentials reach the agent process and the resolver service (env vars, secrets manager, mounted files).
- **MCP server hosting.** Where supervisor-declared MCP servers run, how they're discovered, how they're scaled. The supervisor's resolver knows where each ref points; AVP records the dispatch.
- **Resolver hosting.** Where `AVP_RESOLVER_URL` points, how it authenticates, how it scales. Same trust boundary as the agent process; the supervisor configures both.
- **Agent placement.** Local subprocess, Docker container, remote VM, serverless function, browser sandbox.
- **OS-level sandboxing.** seccomp, AppArmor, cgroups, network policies, filesystem capabilities.
- **Authentication of the supervisor↔agent channel** beyond what the chosen transport inherits from its environment.

The agent's **workspace** is conventionally the agent's current working directory (CWD). Tool inputs containing relative paths resolve there. The supervisor's deployment layer, whatever it is, is responsible for ensuring referenced files exist in that workspace before the run starts.

### 6.1 Pattern: pre-turn world refresh

A common temptation is "I want to update the agent's view of the world between turns": re-read a config file, re-fetch a dashboard, inject the current build status. This is sometimes called *re-observation*. **AVP does not provide a hook for this**, by design. Mid-run reach-in by the supervisor breaks the bounded-context guarantee that makes trajectories meaningful.

The supported pattern is to expose the world refresh as an **MCP-server tool**. The agent calls it; the supervisor's MCP server computes the current value; the agent records the MCP dispatch on the wire as `tool_invoked` / `tool_returned`. The agent decides when to refresh and which information to pull, the trajectory shows exactly what context informed each turn, and there's no asymmetry between driver-pattern and translator-pattern agents.

This section names the lines so readers don't trip on them. A complete production deployment will involve more than this spec covers; that's by design.

---

## 7. Versioning

- The specs share a single umbrella version (v0.1). They MAY decouple in a future major version.
- `Commission.schema_version` MUST equal `"0.1"`.
- `agent_started.data["avp.schema_version"]` MUST equal `"0.1"`.
- Future minor versions MAY add new event types, fields, or enum values. They MUST NOT remove or repurpose existing ones.
- Future major versions MAY introduce breaking changes. Vendor-namespaced keys (`vendor.*`, `com.example.*`) inside `data` round-trip verbatim today (per §4), insulating extensions from spec drift.

An agent that receives a `Commission` with an unsupported `schema_version` MUST emit `avp.error_occurred` with `data["avp.error.code"]: "unknown"` and a descriptive message, then emit `avp.agent_stopped` with `data["avp.reason"]: "error"`.

---

## 8. Schema files

| File | Sub-spec | Purpose |
|---|---|---|
| `trajectory.schema.json` | Trajectory | Entry-point schema for one event in the canonical trajectory |
| `commission.schema.json` | Commission | Entry-point schema for the supervisor → agent Commission |
| `agent-descriptor.schema.json` | Agent Descriptor | Entry-point schema for an agent's published Descriptor |
| `avp.schema.json` | (bundled) | Convenience bundle; all type definitions in `$defs`, top-level `oneOf` over the three above |

JSON Schema Draft 2020-12. Tested with `python-jsonschema` ≥ 4.18 and `ajv` (with `ajv-formats`). The entry-point schemas `$ref` into `avp.schema.json#/$defs/...`. Validators MUST resolve `$ref` against the `$id` URIs (or use a local `$id` to file mapping when validating offline).

Future versions live in sibling directories; published schemas are immutable.

---

## 9. Examples

[`examples/`](./examples/) contains conforming fixtures referenced by individual specs:

- `commission.json`: a worked Commission
- `run.ndjson`: a worked trajectory
