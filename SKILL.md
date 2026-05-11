---
name: avp
description: |
  Use this skill for ANY work on AVP (Agent Voyager Project): agents, supervisor Commissions, conformance cases, or debugging AVP runs. AVP wires agents (drive an LLM, emit events) to supervisors (declare environment).
---

# AVP: Agent Voyager Project

AVP is an open standard for the agent-execution case, defined by four specs that compose independently:

- **Commission** ([`spec/v0.1/commission.md`](spec/v0.1/commission.md)): what the supervisor sends the agent at startup (model, prompt, allowlists, opaque refs to managed assets).
- **Agent Descriptor** ([`spec/v0.1/agent-descriptor.md`](spec/v0.1/agent-descriptor.md)): what the agent advertises about itself before a run begins.
- **Trajectory** ([`spec/v0.1/trajectory.md`](spec/v0.1/trajectory.md)): the stream of source-tagged events the agent emits as it runs.
- **Resolver API** ([`spec/v0.1/resolver.md`](spec/v0.1/resolver.md)): the JSON-RPC service the agent dials at startup to dereference managed-asset refs. The one runtime crossing of the supervisor↔agent boundary; agent-initiated, scoped to startup (`avp.resolve`) plus on-demand managed-subagent dispatch (`avp.spawn_subagent`).

The shape of one run: supervisor sends a Commission; agent reads it, dials the resolver for any managed-asset refs, runs, emits the trajectory. **No supervisor → agent push channel.** Once the Commission is sent, the supervisor only observes.

**AVP is built on existing standards.** Every event is a [CloudEvents 1.0](https://cloudevents.io/) envelope; the `data` payload uses [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) (`gen_ai.usage.input_tokens`, `gen_ai.tool.name`, …) and OTel span identification (`trace_id`, `span_id`, `parent_span_id`). RPC payloads are [JSON-RPC 2.0](https://www.jsonrpc.org/specification). Tool descriptors are [MCP](https://modelcontextprotocol.io/)-shaped. AVP-specific concepts live under the `avp.*` namespace. See `FOUNDATIONS.md` for the full mapping.

## Terms

The vocabulary below is the ubiquitous language of AVP. Every doc, type, and event uses these words consistently. When you generate code or prose, match them.

**Roles**

- **Agent**: the thing that runs the loop. Drives a model, executes tools, emits events. May own the loop directly (driver pattern) or wrap an SDK that owns the loop (observer / translator pattern).
- **Supervisor**: the thing that issues the Commission and observes the trajectory. Stands up the resolver service for managed-asset dereferencing. Never pushes mid-run messages to the agent.

**Artifacts** (the two top-level message classes)

- **Commission**: the supervisor's charter for one run. Declares what the agent should do (`prompt`, `system_prompt`, `model`) and the environment it runs in: supervisor-managed assets (`mcp_servers`, `skills`, `subagents`) as opaque `{id, ref}` pairs, optional `enabled_builtin_tools` / `enabled_builtin_subagents` / `enabled_builtin_skills` allowlists over the agent's Descriptor. Sent once at startup. Type: `Commission`. Wire payload: `run_requested.data["avp.commission"]`.
- **Agent Descriptor**: the agent's self-description. Built-in tools / subagents / skills, plus `agent_name`, `agent_version`, `avp_spec_version`, `supported_models`, `capabilities`. Per-build, not per-run. Printed by `<agent> describe`. Type: `AgentDescriptor`. Wire payload: `agent_described.data["avp.descriptor"]`.

**Runtime concepts**

- **Run**: one execution of an agent against one Commission. Has a `run_id`. Opens with `run_requested` → `agent_described` → `agent_started`. Closes with `agent_stopped`.
- **Trajectory**: the ordered sequence of events emitted during a run. The source of truth: a non-technical reviewer reads it top-to-bottom to reconstruct what happened.
- **Event**: one CloudEvents 1.0 envelope. 22 types in v0.1, all past-tense facts (`tool_invoked`, `model_turn_ended`, `managed_ref_resolved`, `agent_stopped`, …) under the `avp.*` namespace. See [`spec/v0.1/trajectory.md`](spec/v0.1/trajectory.md) §7 for the full catalog.
- **Turn**: one `model_turn_started` / `model_turn_ended` pair where the model produced new output. The unit of model invocation accounting.

**Resolver API** (see [`spec/v0.1/resolver.md`](spec/v0.1/resolver.md))

- **Ref**: an opaque JSON value the supervisor put in `Commission.{mcp_servers,skills,subagents}[].ref`. AVP doesn't constrain its shape: string, object, hash, ARN, whatever the supervisor's resolver understands.
- **Resolver service**: supervisor-stood-up JSON-RPC endpoint. The agent reads its location from `AVP_RESOLVER_URL` and calls `avp.resolve` (startup, once per ref) and `avp.spawn_subagent` (on-demand, when the model invokes a managed subagent).
- **`HttpResolver`**: the v0.1 reference `ResolverDriver` implementation. Lives at `avp.agent.HttpResolver`; the helper `http_resolver_from_env()` builds one from `AVP_RESOLVER_URL` and optional `AVP_RESOLVER_TOKEN`. Returns `None` when the env var is unset, signaling a no-managed-assets run.

**Environment primitives** (declared in Commission as `{id, ref}` pairs)

- **Subagent ref**: points the resolver at a managed subagent. The resolver returns metadata at startup (`name`, `description`, `inputSchema`) and is called again via `avp.spawn_subagent` when the model invokes it; the parent records the child run's `run_id` on `subagent_invoked.data["avp.subagent.run_id"]`.
- **Skill ref**: points the resolver at SKILL.md content. The resolver returns `{content, description?}`; the agent injects content into the model's context at startup and emits `skill_loaded`.
- **MCP server ref**: points the resolver at MCP connection material. The resolver returns transport/url/auth; the agent's MCP client dials and runs `tools/list` + `tools/call`. v0.1's only mechanism for supervisor-side tool dispatch.

**Wire-format vocabulary**

- **The wire**: the protocol/format level. "On the wire" means "as bytes a consumer parses." Distinct from the trajectory (the logical sequence) and the audit trail (the use case).
- **Source**: the producer URI on each event. Either `avp://agent` (most events) or `avp://supervisor` (only on the agent-relayed `run_requested`).
- **Span**: OTel trace identification (`trace_id`, `span_id`, `parent_span_id`) carried on every event's `data`. Lets the trajectory reconstruct as a span tree.

**Packaging (how implementations are organized in this repo)**

The protocol cares about wire shape, not packaging. But this repo packages two distinct things on top of the wire, and that distinction matters when you're answering "where does new code go" or "what does this package do":

- **Agent**: owns the agent loop, reads a Commission, emits the trajectory, advertises an Agent Descriptor, dispatches tools, calls the resolver. An agent is what `spec/v0.1/` certifies as conforming. Examples: `python/agents/avp-claude-agent/` (a complete agent built on the Claude Agent SDK, which already ships a loop), and the reference agent at `python/supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py` (built on the `avp-anthropic` SDK adapter plus `AVPAgent`).
- **SDK adapter**: translates one raw API / client surface to AVP. Ships a `ModelDriver` (turn-by-turn translation that plugs into `AVPAgent`), a `TracedClient` (drop-in observability over an existing SDK loop), and Commission-to-API translators. Ships NO agent loop and NO built-in tools, because the upstream API doesn't have them. Agents wrap the adapter. Example: `python/sdks/avp-anthropic/` for the Anthropic Messages API.

Rule of thumb: if the upstream SDK ships its own agent loop and tools, package the integration as a complete agent under `python/agents/`. If the upstream is a raw HTTP client, package it as an SDK adapter under `python/sdks/` and let a separate agent (in examples or a downstream package) wrap it.

## When to do what

There are three tasks AVP gets used for. Match the user's intent to one of these and follow the relevant pattern.

### Task A: Build an agent (driver pattern)

The user wants their code to OWN the agent loop and use AVP as the wire. Examples: wrapping the Anthropic Messages API, wrapping OpenAI, wrapping a custom LLM, building from scratch.

Use this when: the user says "I want to call Claude / GPT / Gemini and emit AVP" or "wrap my agent loop in AVP" or "build an agent."

The reference is `python/avp/src/avp/agent/agent.py` (the canonical loop) plus `python/sdks/avp-anthropic/` (the SDK adapter for the raw Anthropic Messages API: it ships a `ModelDriver` but no loop or built-in tools, since the API itself ships neither) and `python/supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py` (a reference agent that wires the driver to `AVPAgent` with a local `ShellTools`). The pattern:

1. Read a `Commission` from input. Validate against `avp.types.Commission`.
2. Construct an `AVPAgent` with `model: ModelDriver`, `tools: ToolDriver`, `supervisor: SupervisorDriver`, and (when the Commission may carry managed assets) `resolver=http_resolver_from_env()`.
3. The agent emits the full lifecycle: `run_requested`, `agent_described`, `agent_started`, `managed_ref_resolved` (per asset), `mcp_server_connected` (per resolved MCP), `skill_loaded` (per resolved skill), `model_turn_started/ended`, `tool_invoked/returned`, `cost_recorded`, `agent_stopped`. Every event is a CloudEvents 1.0 envelope.
4. The driver's only jobs are translating one model turn (`ModelDriver.step(history) -> ModelResponse`) and, optionally, implementing `set_resolved_assets(...)` so the agent can stage resolved MCP connection material into provider-side API params.

See `python/supervisors/simple-supervisor-example/examples/01_anthropic_cost_bounded.py` for a minimal end-to-end run, `05_anthropic_subagent_delegation.py` for managed-subagent delegation through the resolver, or `06_anthropic_traced_client.py` if the user already has an Anthropic SDK loop and wants drop-in instrumentation. See `python/sdks/avp-anthropic/src/avp_anthropic/driver.py` for the complete driver.

### Task B: Build an agent (observer pattern)

The user wants AVP observability over an SDK that already owns its loop. Examples: Claude Agent SDK, LangChain, AutoGen, an internal framework.

Use this when: the user says "wrap Claude Code as an agent," "make LangChain emit AVP events," or "translate my SDK's lifecycle into AVP." Anywhere they can't own the loop but can subscribe to lifecycle events.

The reference is `python/agents/avp-claude-agent/src/avp_claude_agent/translator.py`. The pattern:

1. Accept the Commission and an optional `resolver: ResolverDriver`. Run the resolver gate (fail-fast with `resolver_not_configured` if the Commission carries managed assets but no resolver is wired); resolve all refs; emit `managed_ref_resolved` per success.
2. Translate resolved material into the SDK's setup parameters (e.g. Claude Agent SDK's `mcp_servers` / `agents`).
3. Subscribe to the SDK's lifecycle (turn-start, turn-end, tool-use, tool-result, completion).
4. Translate each lifecycle event into the corresponding AVP event using `avp.types.*` Pydantic models.
5. Maintain a local `RunStateSnapshot` for cost/token accounting per `spec/v0.1/trajectory.md` §3.3.

See `python/supervisors/simple-supervisor-example/examples/03_claude_code_audited.py` (audited Claude Code session) and `07_claude_agent_traced_client.py` (drop-in instrumentation over an existing `ClaudeSDKClient`).

### Task C: Compose a supervisor Commission

The user wants to declare an agent environment: what the agent can do, what rules it must respect, what it should observe. This is the supervisor side.

Use this when: the user says "configure an agent," "lock down an agent," "what tools should this agent have," or describes a domain and wants to translate it into agent gates.

The pattern: build a `Commission` (`avp.types.Commission`) with the supervisor primitives the situation calls for.

| Concern | Field | Notes |
|---|---|---|
| Managed MCP servers | `mcp_servers: list[McpServerRef]` | Each entry is `{id, ref}`; the supervisor's resolver returns connection material at startup. Tagged on the wire with `avp.tool.dispatch_target=mcp_server` and `avp.mcp_server_id`. |
| Managed skills | `skills: list[SkillRef]` | Each entry is `{id, ref}`; the resolver returns SKILL.md content. Surfaced on `skill_loaded` after resolution. |
| Managed subagents | `subagents: list[SubagentRef]` | Each entry is `{id, ref}`; the resolver returns model-facing metadata at startup; `avp.spawn_subagent` runs the sub-loop on demand. The parent records the child run's id on `subagent_invoked.data["avp.subagent.run_id"]`. |
| Built-in tool allowlist | `enabled_builtin_tools` | Optional list of names. Absent → all built-ins exposed; `[]` → none; subset → only those names. Validated against the agent's Descriptor at startup (fails with `commission_collision` on unknown names). |
| Built-in subagent allowlist | `enabled_builtin_subagents` | Same semantics for built-in subagents. |
| Built-in skill allowlist | `enabled_builtin_skills` | Same semantics for built-in skills. |
| What it produces | `output_schema` | JSON schema. |
| What it runs | `prompt`, `system_prompt`, `model` | Standard agent-plane fields. |

See `spec/v0.1/examples/commission.json` for a wire-format equivalent and `python/supervisors/simple-supervisor-example/examples/05_anthropic_subagent_delegation.py` for managed subagents.

## Two classes of trajectory facts

Whatever you build, the trajectory carries two distinct kinds of facts. Surface them separately to consumers; don't conflate.

| Class | Event types | Semantics |
|---|---|---|
| What the agent did | `model_turn_*`, `tool_invoked`, `tool_returned`, `tool_failed`, `subagent_*`, `managed_ref_resolved`, `managed_ref_resolve_failed`, `text_emitted` | Mechanical actions |
| What the run cost | `cost_recorded`, `model_turn_ended.data["gen_ai.usage.*"]` | Resource accounting (OTel-shaped) |

## Workspace and deployment scope

The agent's workspace is the **agent's current working directory**. Tool inputs containing relative paths resolve there. The supervisor's deployment layer (whatever stages the agent: git checkout, container, tmpdir) is responsible for making referenced files exist in that directory before the run starts.

Workspace provisioning, secret injection, resolver hosting, agent placement, and OS-level sandboxing are all **outside AVP's scope**. See [`spec/v0.1/README.md`](spec/v0.1/README.md) §6 (deployment scope). AVP defines the wire, not the deployment topology. If a user asks about any of these and treats AVP as the answer, redirect them to the deployment layer instead.

## What the supervisor is NOT allowed to do

Common temptations to push back on:

- **No mid-run push to the agent.** Once the Commission is sent, the supervisor only observes the trajectory. If the user needs runtime gating, build it as a managed MCP server (the agent calls it; the supervisor's MCP server decides). The rule lives in Commission, not in a callback.
- **No supervisor-emitted runtime events.** The agent emits everything. The supervisor's only on-wire fact is the agent-relayed `run_requested` (the agent stamps `source: avp://supervisor` to attribute the run).

## When in doubt, read these (in this order)

1. `spec/v0.1/README.md`: umbrella entry point indexing the four specs (trajectory, commission, agent-descriptor, resolver) plus shared concerns (foundations, transports, deployment scope, versioning).
2. The relevant spec for your question:
   - **Event stream / loop / cost rules / event catalog** → `spec/v0.1/trajectory.md`
   - **Run-config / allowlists / refs-only assets** → `spec/v0.1/commission.md`
   - **Agent self-description / capabilities** → `spec/v0.1/agent-descriptor.md`
   - **JSON-RPC methods, bootstrap, error handling** → `spec/v0.1/resolver.md`
3. `spec/v0.1/{trajectory,commission,agent-descriptor}.schema.json`: JSON Schemas per spec; authoritative for field-by-field shape. `spec/v0.1/avp.schema.json` is the bundled `oneOf`.
4. `conformance/v0.1/cases/`: executable test cases that pin down behavior. Read these as worked examples of "what's the right answer when...".
5. `python/avp/src/avp/types.py`: Pydantic models that mirror the schemas. Authoritative Python surface. Scoped re-exports: `avp.trajectory`, `avp.commission`, `avp.descriptor`, `avp.resolver`.
6. `python/avp/src/avp/agent/agent.py`: the canonical agent loop in working code.
7. `python/sdks/avp-anthropic/`: SDK adapter for the raw Anthropic Messages API. Ships a `ModelDriver`, a `TracedClient`, and Commission-to-API translators; the agent loop and tool catalog live in agents that wrap it. See `python/supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py` for a reference agent built on top.
8. `python/agents/avp-claude-agent/`: observer-pattern agent over the Claude Agent SDK.

## How to operate when the user describes a need

1. Identify which of Tasks A / B / C they're asking about (or which combination).
2. Read the closest match in `python/supervisors/simple-supervisor-example/examples/` (numbered 01–07, narrative format) first to ground yourself in current shape.
3. Cross-reference with the specs: [`resolver.md`](spec/v0.1/resolver.md) (Resolver API), [`commission.md`](spec/v0.1/commission.md) §4 (built-in allowlists), [`trajectory.md`](spec/v0.1/trajectory.md) §3 (the loop) and §4 (tool dispatch).
4. For runtime correctness questions, the conformance cases under `conformance/v0.1/cases/` are precedent. Find the case that matches the situation.
5. Generate code that imports from `avp.types`, `avp.agent`, `avp.io`. Do NOT inline-redefine the wire types.
6. If asked about a behavior the spec doesn't cover, say so explicitly and propose a path that doesn't violate any of the existing conformance cases.
