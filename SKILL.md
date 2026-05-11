---
name: avp
description: |
  Use this skill for ANY work on AVP (Agent Voyage Protocol) — agents, supervisor Commissions, conformance cases, or debugging AVP runs. AVP wires agents (drive an LLM, emit events) to supervisors (declare environment).
---

# AVP — Agent Voyage Protocol

AVP is a wire format between two roles, with two unidirectional flows plus one agent-initiated callback:

The supervisor declares a complete environment in a Commission. The agent runs the agent inside it. The agent emits a stream of source-tagged events. **No supervisor → agent push channel.**

The one runtime crossing of the supervisor↔agent boundary is the **AVP resolver protocol** (SPEC §6): the supervisor stands up a resolver service; the agent dials it via JSON-RPC over HTTP to dereference opaque refs in the Commission. Agent-initiated, scoped to startup, recorded on the trajectory as `managed_ref_resolved` / `managed_ref_resolve_failed` events.

**AVP is built on existing standards.** Every event is a [CloudEvents 1.0](https://cloudevents.io/) envelope; the `data` payload uses [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) (`gen_ai.usage.input_tokens`, `gen_ai.tool.name`, …) and OTel span identification (`trace_id`, `span_id`, `parent_span_id`). RPC payloads are [JSON-RPC 2.0](https://www.jsonrpc.org/specification). Tool descriptors are [MCP](https://modelcontextprotocol.io/)-shaped. AVP-specific concepts live under the `avp.*` namespace. See `FOUNDATIONS.md` for the full mapping.

## Terms

The vocabulary below is the ubiquitous language of AVP. Every doc, type, and event uses these words consistently — when you generate code or prose, match them.

**Roles**

- **Agent** — the thing that runs the loop. Drives a model, executes tools, emits events. May own the loop directly (driver pattern) or wrap an SDK that owns the loop (observer / translator pattern).
- **Supervisor** — the thing that issues the Commission and observes the trajectory. Stands up the resolver service for managed-asset dereferencing. Never pushes mid-run messages to the agent.

**Artifacts** (the two top-level message classes)

- **Commission** — the supervisor's charter for one run. Declares what the agent should do (`prompt`, `system_prompt`, `model`) and the environment it runs in: supervisor-managed assets (`mcp_servers`, `skills`, `subagents`) as opaque `{id, ref}` pairs, optional `enabled_builtin_tools` / `enabled_builtin_subagents` / `enabled_builtin_skills` allowlists over the agent's manifest. Sent once at startup. Type: `Commission`. Wire payload: `run_requested.data["avp.commission"]`.
- **Manifest** — the agent's self-description. Built-in tools / subagents / skills, plus `agent_name`, `agent_version`, `avp_spec_version`, `supported_models`, `capabilities`. Per-build, not per-run. Printed by `<agent> describe`. Type: `AgentManifest`. Wire payload: `agent_described.data["avp.manifest"]`.

**Runtime concepts**

- **Run** — one execution of an agent against one Commission. Has a `run_id`. Opens with `run_requested` → `agent_described` → `agent_started`. Closes with `agent_stopped`.
- **Trajectory** — the ordered sequence of events emitted during a run. The source of truth: a non-technical reviewer reads it top-to-bottom to reconstruct what happened.
- **Event** — one CloudEvents 1.0 envelope. 22 types in v0.1, all past-tense facts (`tool_invoked`, `model_turn_ended`, `managed_ref_resolved`, `agent_stopped`, …) under the `avp.*` namespace. See §12 of `SPEC.md`.
- **Turn** — one `model_turn_started` / `model_turn_ended` pair where the model produced new output. The unit of model invocation accounting.

**Resolver protocol** (SPEC §6)

- **Ref** — an opaque JSON value the supervisor put in `Commission.{mcp_servers,skills,subagents}[].ref`. AVP doesn't constrain its shape — string, object, hash, ARN, whatever the supervisor's resolver understands.
- **Resolver service** — supervisor-stood-up JSON-RPC endpoint. The agent reads its location from `AVP_RESOLVER_URL` and calls `avp.resolve` (startup, once per ref) and `avp.spawn_subagent` (on-demand, when the model invokes a managed subagent).
- **`HttpResolver`** — the v0.1 reference `ResolverDriver` implementation. Lives at `avp.agent.HttpResolver`; the helper `http_resolver_from_env()` builds one from `AVP_RESOLVER_URL` + optional `AVP_RESOLVER_TOKEN`. Returns `None` when the env var is unset (Profile A — no managed assets).

**Environment primitives** (declared in Commission as `{id, ref}` pairs)

- **Subagent ref** — points the resolver at a managed subagent. The resolver returns metadata at startup (`name`, `description`, `inputSchema`) and is called again via `avp.spawn_subagent` when the model invokes it; the parent records the child run's `run_id` on `subagent_invoked.data["avp.subagent.run_id"]`.
- **Skill ref** — points the resolver at SKILL.md content. The resolver returns `{content, description?}`; the agent injects content into the model's context at startup and emits `skill_loaded`.
- **MCP server ref** — points the resolver at MCP connection material. The resolver returns transport/url/auth; the agent's MCP client dials and runs `tools/list` + `tools/call`. v0.1's only mechanism for supervisor-side tool dispatch.

**Wire-format vocabulary**

- **The wire** — the protocol/format level. "On the wire" means "as bytes a consumer parses." Distinct from the trajectory (the logical sequence) and the audit trail (the use case).
- **Source** — the producer URI on each event. Either `avp://agent` (most events) or `avp://supervisor` (only on the agent-relayed `run_requested`).
- **Span** — OTel trace identification (`trace_id` + `span_id` + `parent_span_id`) carried on every event's `data`. Lets the trajectory reconstruct as a span tree.

## When to do what

There are three tasks AVP gets used for. Match the user's intent to one of these and follow the relevant pattern.

### Task A — Build an agent (driver pattern)

The user wants their code to OWN the agent loop and use AVP as the wire. Examples: wrapping the Anthropic Messages API, wrapping OpenAI, wrapping a custom LLM, building from scratch.

Use this when: the user says "I want to call Claude / GPT / Gemini and emit AVP" or "wrap my agent loop in AVP" or "build an agent."

The reference is `python/avp/src/avp/agent/agent.py` (the canonical loop) plus `python/agents/avp-anthropic/` (a complete real-LLM driver). The pattern:

1. Read a `Commission` from input. Validate against `avp.types.Commission`.
2. Construct an `AVPAgent` with `model: ModelDriver`, `tools: ToolDriver`, `supervisor: SupervisorDriver`, and (when the Commission may carry managed assets) `resolver=http_resolver_from_env()`.
3. The agent emits the full lifecycle: `run_requested`, `agent_described`, `agent_started`, `managed_ref_resolved` (per asset), `mcp_server_connected` (per resolved MCP), `skill_loaded` (per resolved skill), `model_turn_started/ended`, `tool_invoked/returned`, `cost_recorded`, `agent_stopped`. Every event is a CloudEvents 1.0 envelope.
4. The driver's only jobs are translating one model turn (`ModelDriver.step(history) -> ModelResponse`) and, optionally, implementing `set_resolved_assets(...)` so the agent can stage resolved MCP connection material into provider-side API params.

See `python/supervisors/simple-supervisor-example/examples/01_anthropic_cost_bounded.py` for a minimal end-to-end run, `05_anthropic_subagent_delegation.py` for managed-subagent delegation through the resolver, or `06_anthropic_traced_client.py` if the user already has an Anthropic SDK loop and wants drop-in instrumentation. See `python/agents/avp-anthropic/src/avp_anthropic/driver.py` for the complete driver.

### Task B — Build an agent (observer pattern)

The user wants AVP observability over an SDK that already owns its loop. Examples: Claude Agent SDK, LangChain, AutoGen, an internal framework.

Use this when: the user says "wrap Claude Code as an agent," "make LangChain emit AVP events," "translate my SDK's lifecycle into AVP" — anywhere they can't own the loop but can subscribe to lifecycle events.

The reference is `python/agents/avp-claude-agent/src/avp_claude_agent/translator.py`. The pattern:

1. Accept the Commission + an optional `resolver: ResolverDriver`. Run the resolver gate (fail-fast with `resolver_not_configured` if the Commission carries managed assets but no resolver is wired); resolve all refs; emit `managed_ref_resolved` per success.
2. Translate resolved material into the SDK's setup parameters (e.g. Claude Agent SDK's `mcp_servers` / `agents`).
3. Subscribe to the SDK's lifecycle (turn-start, turn-end, tool-use, tool-result, completion).
4. Translate each lifecycle event into the corresponding AVP event using `avp.types.*` Pydantic models.
5. Maintain a local `RunStateSnapshot` for cost/token accounting per AVP §10.3.

See `python/supervisors/simple-supervisor-example/examples/03_claude_code_audited.py` (audited Claude Code session) and `07_claude_agent_traced_client.py` (drop-in instrumentation over an existing `ClaudeSDKClient`).

### Task C — Compose a supervisor Commission

The user wants to declare an agent environment — what the agent can do, what rules it must respect, what it should observe. This is the supervisor side.

Use this when: the user says "configure an agent," "lock down an agent," "what tools should this agent have," or describes a domain and wants to translate it into agent gates.

The pattern: build a `Commission` (`avp.types.Commission`) with the supervisor primitives the situation calls for.

| Concern | Field | Notes |
|---|---|---|
| Managed MCP servers | `mcp_servers: list[McpServerRef]` | Each entry is `{id, ref}`; the supervisor's resolver returns connection material at startup. Tagged on the wire with `avp.tool.dispatch_target=mcp_server` + `avp.mcp_server_id`. |
| Managed skills | `skills: list[SkillRef]` | Each entry is `{id, ref}`; the resolver returns SKILL.md content. Surfaced on `skill_loaded` after resolution. |
| Managed subagents | `subagents: list[SubagentRef]` | Each entry is `{id, ref}`; the resolver returns model-facing metadata at startup; `avp.spawn_subagent` runs the sub-loop on demand. The parent records the child run's id on `subagent_invoked.data["avp.subagent.run_id"]`. |
| Built-in tool allowlist | `enabled_builtin_tools` | Optional list of names. Absent → all built-ins exposed; `[]` → none; subset → only those names. Validated against the agent's manifest at startup (fails with `commission_collision` on unknown names). |
| Built-in subagent allowlist | `enabled_builtin_subagents` | Same semantics for built-in subagents. |
| Built-in skill allowlist | `enabled_builtin_skills` | Same semantics for built-in skills. |
| What it produces | `output_schema` | JSON schema. |
| What it runs | `prompt`, `system_prompt`, `model` | Standard agent-plane fields. |

See `spec/v0.1/examples/commission.json` for a wire-format equivalent and `python/supervisors/simple-supervisor-example/examples/05_anthropic_subagent_delegation.py` for managed subagents.

## Two classes of trajectory facts

Whatever you build, the trajectory carries two distinct kinds of facts. Surface them separately to consumers — don't conflate.

| Class | Event types | Semantics |
|---|---|---|
| What the agent did | `model_turn_*`, `tool_invoked`, `tool_returned`, `tool_failed`, `subagent_*`, `managed_ref_resolved`, `managed_ref_resolve_failed`, `text_emitted` | Mechanical actions |
| What the run cost | `cost_recorded`, `model_turn_ended.data["gen_ai.usage.*"]` | Resource accounting (OTel-shaped) |

## Workspace and deployment scope

The agent's workspace is the **agent's current working directory**. Tool inputs containing relative paths resolve there. The supervisor's deployment layer (whatever stages the agent — git checkout, container, tmpdir) is responsible for making referenced files exist in that directory before the run starts.

Workspace provisioning, secret injection, resolver hosting, agent placement, and OS-level sandboxing are all **outside AVP's scope** — see `spec/v0.1/SPEC.md` §15. AVP defines the wire, not the deployment topology. If a user asks about any of these and treats AVP as the answer, redirect them to the deployment layer instead.

## What the supervisor is NOT allowed to do

Common temptations to push back on:

- **No mid-run push to the agent.** Once the Commission is sent, the supervisor only observes the trajectory. If the user needs runtime gating, build it as a managed MCP server (the agent calls it; the supervisor's MCP server decides). The rule lives in Commission, not in a callback.
- **No supervisor-emitted runtime events.** The agent emits everything. The supervisor's only on-wire fact is the agent-relayed `run_requested` (the agent stamps `source: avp://supervisor` to attribute the run).

## When in doubt, read these — in this order

1. `spec/v0.1/SPEC.md` — normative spec, RFC 2119 keywords, reference algorithm. The source of truth for any wire-format question.
2. `spec/v0.1/avp.schema.json` — JSON Schema bundle. Authoritative for field-by-field shape.
3. `conformance/v0.1/cases/` — executable test cases that pin down behavior. Read these as worked examples of "what's the right answer when...".
4. `python/avp/src/avp/types.py` — Pydantic models that mirror the schema. Authoritative Python surface.
5. `python/avp/src/avp/agent/agent.py` — the canonical agent loop in working code.
6. `python/agents/avp-anthropic/` — complete real-LLM driver agent.
7. `python/agents/avp-claude-agent/` — observer-pattern agent over the Claude Agent SDK.

## Common mistakes to catch

When reviewing AVP code or generating it, watch for:

- Emitting `avp.agent_started` with `source: "avp://supervisor"`. **Wrong** — agent emits, source MUST be `avp://agent`.
- Using `Commission.exposed` or `Commission.tools` or `Commission.allowed_tools`. **All gone in v0.1.** The supervisor-managed surface is the three `*Ref` lists; built-in gating uses `enabled_builtin_*`.
- Constructing `Subagent(name=..., description=..., system_prompt=...)` or `McpServer(transport=..., url=..., auth=...)` or `Skill(name=..., avp_source=...)` directly in a Commission. **Wrong** — those rich types are gone. Commission entries are `SubagentRef`/`SkillRef`/`McpServerRef` with `{id, ref}` only; metadata comes from the resolver.
- Reaching for an `AnthropicSubagentDriver` or `SubagentDriver` Protocol. **Removed.** In-process subagent dispatch is gone; managed subagents spawn via `ResolverDriver.spawn_subagent`.
- Tagging `avp.tool.dispatch_target="hosted"` or stamping `avp.tool.subtype`. **Both gone.** Hosted tools (Anthropic `web_search`, `code_execution`) are first-class agent built-ins with `dispatch_target=local`; gate via `enabled_builtin_tools`.
- Subtracting cache-read tokens from `gen_ai.usage.input_tokens`. **Wrong** — per §10.3, cache reads ARE input tokens.
- Computing `total_cost_usd` from `tokens * rate` without accounting for cache discounts. **Wrong** — `avp.cost_usd` per turn is the BILLABLE cost (post-cache-discount); `state.total_cost_usd` is the sum of those.

## How to operate when the user describes a need

1. Identify which of Tasks A / B / C they're asking about (or which combination).
2. Read the closest match in `python/supervisors/simple-supervisor-example/examples/` (numbered 01–07, narrative format) first to ground yourself in current shape.
3. Cross-reference with `spec/v0.1/SPEC.md` §6 (resolver protocol), §9 (tools / built-in allowlists), §10 (the loop).
4. For runtime correctness questions, the conformance cases under `conformance/v0.1/cases/` are precedent — find the case that matches the situation.
5. Generate code that imports from `avp.types`, `avp.agent`, `avp.io`. Do NOT inline-redefine the wire types.
6. If asked about a behavior the spec doesn't cover, say so explicitly and propose a path that doesn't violate any of the existing conformance cases.
