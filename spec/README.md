# AVP Specifications

The **Agent Voyager Project** (AVP) is a collection of four specs that compose into a coherent wire format for the agent-execution case. Each spec is versioned and adopted independently. This directory indexes the current set; each sub-spec carries its own RFC 2119 keywords and conformance criteria.

| Sub-spec | Status | Version | Kind | What it defines |
|---|---|---|---|---|
| **AVP Trajectory** | Stable | [v0.1](./trajectory/v0.1/trajectory.md) | Data-shape | The event stream: CloudEvents envelope, OTel span/GenAI attrs, event-type catalog, ordering/pairing invariants, the agent loop algorithm |
| **AVP Agent Descriptor** | Stable | [v0.1](./agent-descriptor/v0.1/agent-descriptor.md) | Data-shape | What an agent advertises pre-flight: built-in tool/subagent/skill catalogs, capabilities, supported models |
| **AVP Commission** | Beta | [v0.1-beta](./commission/v0.1-beta/commission.md) | Data-shape | The run-config object: prompt, model, refs-only managed assets, `enabled_builtin_*` allowlist semantics |
| **AVP Resolver API** | Beta | [v0.1-beta](./resolver/v0.1-beta/resolver.md) | Protocol | JSON-RPC 2.0 methods (`avp.resolve`, `avp.spawn_subagent`) for dereferencing managed-asset refs against a supervisor-stood-up service |

The three data-shape specs are independent; each can be adopted on its own. The Resolver API is the only spec that defines wire-level request/response between two parties, and depends on Commission (the refs it dereferences live there).

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** in every spec are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

## Stability tiers

- **Stable.** Wire shape and conformance criteria are committed; breaking changes require a new minor or major version.
- **Beta.** Shape works end to end against the reference implementations but adoption is limited; breaking changes possible before promotion to Stable.

## Built on

AVP specializes (it does not reinvent) the following industry specs:

- **CloudEvents 1.0** for the event envelope (`specversion`, `id`, `source`, `type`, `subject`, `time`, `datacontenttype`, `data`).
- **OpenTelemetry GenAI semantic conventions** for token / cost / model / tool attribute names inside `data` (e.g., `gen_ai.usage.input_tokens`, `gen_ai.tool.name`).
- **OpenTelemetry span identification** (`trace_id`, `span_id`, `parent_span_id`) on every event so trajectories reconstruct as a span tree.
- **JSON-RPC 2.0** for the AVP Resolver API. Agent → resolver service calls (`avp.resolve`, `avp.spawn_subagent`) that dereference opaque refs in the Commission.
- **MCP 2025-11-25** for supervisor-side tool dispatch. Commission entries in `mcp_servers[]` are opaque refs the agent resolves into MCP connection material; the agent then runs MCP's `initialize` + `tools/list` and dispatches `tools/call` against the live server.
- **Agent Skills** (agentskills.io) for `SKILL.md` content. Commission `skills[]` entries are refs; the resolver returns SKILL.md content (or a location to fetch).
- **JSON Schema Draft 2020-12** for these specifications' machine-readable form.

AVP-specific concepts (the **no-mid-run-reach-in topology** and the **trajectory-as-source-of-truth contract**) live under the `avp.*` attribute namespace. See [`../FOUNDATIONS.md`](../FOUNDATIONS.md) for the full mapping rationale.

## Versioning policy

- Each spec versions independently. Trajectory v0.1 does not require Commission v0.1-beta, and vice versa.
- Each spec directory (`spec/<spec>/<version>/`) is immutable once published.
- Beta-tagged versions (`-beta` suffix) MAY break compatibly until promoted; Stable-tagged versions MAY add new event types, fields, or enum values in additive minor releases but MUST NOT remove or repurpose existing ones.
- Vendor-namespaced keys (`vendor.*`, `com.example.*`) inside `data` round-trip verbatim, insulating extensions from spec drift.

## Schema files

| File | Sub-spec | Purpose |
|---|---|---|
| `trajectory/v0.1/trajectory.schema.json` | Trajectory | Entry-point schema for one event in the canonical trajectory |
| `agent-descriptor/v0.1/agent-descriptor.schema.json` | Agent Descriptor | Entry-point schema for an agent's published Descriptor |
| `commission/v0.1-beta/commission.schema.json` | Commission | Entry-point schema for the supervisor → agent Commission |

JSON Schema Draft 2020-12. Tested with `python-jsonschema` ≥ 4.18 and `ajv` (with `ajv-formats`). Validators MUST resolve `$ref` against the `$id` URIs (raw GitHub paths under this repo) or use a local `$id` to file mapping when validating offline.

The Resolver API has no JSON Schema: it's an RPC protocol, not a data-shape spec.

## Examples

Worked fixtures live under each spec's directory:

- [`commission/v0.1-beta/examples/commission.json`](./commission/v0.1-beta/examples/commission.json): a worked Commission
- [`trajectory/v0.1/examples/run.ndjson`](./trajectory/v0.1/examples/run.ndjson): a worked trajectory
