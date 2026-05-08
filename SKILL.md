---
name: avp
description: |
  Use this skill for ANY work on AVP (Agent Voyage Protocol) — agents, supervisor Configs, conformance cases, or debugging AVP runs. AVP wires agents (drive an LLM, emit events) to supervisors (declare environment).
---

# AVP — Agent Voyage Protocol

AVP is a wire format between two roles, with two unidirectional flows:

```
                                      agent's environment
                       (tools, mcp_servers, subagents, skills, prompt)
                                              │
                                              ▼
   supervisor ──── Commission (one-time, setup) ──▶ agent
                                              │
                                              ▼
                                        runs the agent
                                              │
                                              ▼
   supervisor ◀────────── events (continuous, run-end) ────── agent
```

The supervisor declares a complete environment in a Commission. The agent runs the agent inside it. The agent emits a stream of source-tagged events. **No mid-run reach-in.** The agent's bounded context is intact because its environment was fully specified at setup.

The one runtime exception is **environmental services**: if a Commission-declared tool's implementation is out-of-process, the agent issues an RPC (`avp.tool_exec_request`) and the supervisor's service replies (`avp.tool_exec_resolved`). This is an agent-initiated call into a service the supervisor stood up at Commission time — not a supervisor decision made during the run.

**AVP is built on existing standards** Every event is a [CloudEvents 1.0](https://cloudevents.io/) envelope; the `data` payload uses [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) (`gen_ai.usage.input_tokens`, `gen_ai.tool.name`, …) and OTel span identification (`trace_id`, `span_id`, `parent_span_id`). RPC payloads are [JSON-RPC 2.0](https://www.jsonrpc.org/specification). Tool descriptors are [MCP](https://modelcontextprotocol.io/)-shaped. AVP-specific concepts live under the `avp.*` namespace. See `FOUNDATIONS.md` for the full mapping.

## When to do what

There are three tasks AVP gets used for. Match the user's intent to one of these and follow the relevant pattern.

### Task A — Build a agent (driver pattern)

The user wants their code to OWN the agent loop and use AVP as the wire. Examples: wrapping the Anthropic Messages API, wrapping OpenAI, wrapping a custom LLM, building from scratch.

Use this when: the user says "I want to call Claude / GPT / Gemini and emit AVP" or "wrap my agent loop in AVP" or "build a agent."

The reference is `python/avp/src/avp/agent/agent.py` (the canonical loop) plus `python/agents/avp-anthropic/` (a complete real-LLM driver). The pattern:

1. Read a `Commission` from input. Validate against `avp.types.Commission`.
2. Construct an `AVPAgent` with `model: ModelDriver`, `tools: ToolDriver`, `supervisor: SupervisorDriver`.
3. The agent emits the full lifecycle: `avp.agent_described`, `avp.agent_started`, `avp.model_turn_started/ended`, `avp.tool_invoked/returned`, `avp.cost_recorded`, `avp.agent_stopped`. Every event is a CloudEvents 1.0 envelope.
4. The driver's only job is translating one model turn — implement `ModelDriver.step(history) -> ModelResponse`.

See `python/supervisors/simple-supervisor-example/examples/01_anthropic_cost_bounded.py` for a minimal end-to-end run, or `06_anthropic_traced_client.py` if the user already has an Anthropic SDK loop and wants drop-in instrumentation. See `python/agents/avp-anthropic/src/avp_anthropic/driver.py` for the complete driver: cache-token math, cost computation, refusal/reasoning/MCP/hosted-tool block parsing, tool-call translation.

### Task B — Build a agent (observer pattern)

The user wants AVP observability over an SDK that already owns its loop. Examples: Claude Agent SDK, LangChain, AutoGen, an internal framework.

Use this when: the user says "wrap Claude Code as a agent," "make LangChain emit AVP events," "translate my SDK's lifecycle into AVP" — anywhere they can't own the loop but can subscribe to lifecycle events.

The reference is `python/agents/avp-claude-agent/src/avp_claude_agent/translator.py`. The pattern:

1. Subscribe to the SDK's lifecycle (turn-start, turn-end, tool-use, tool-result, completion).
2. Translate each lifecycle event into the corresponding AVP event using `avp.types.*` Pydantic models.
3. Emit via `avp.io.write_event` (NDJSON to stdout) or a callback.
4. Maintain a local `RunStateSnapshot` for cost/token accounting per AVP §10.4.

See `python/supervisors/simple-supervisor-example/examples/03_claude_code_audited.py` (audited Claude Code session) and `07_claude_agent_traced_client.py` (drop-in instrumentation over an existing `ClaudeSDKClient`). The translator at `python/agents/avp-claude-agent/src/avp_claude_agent/translator.py` is the worked-out reference; the tricky parts (cost accounting via per-turn deltas + ResultMessage reconciliation, `source` discipline, tool-call translation through SDK hooks) are documented inline.

### Task C — Compose a supervisor Commission

The user wants to declare an agent environment — what the agent can do, what rules it must respect, what it should observe, and how much it can spend. This is the supervisor side.

Use this when: the user says "configure an agent," "lock down an agent," "what tools should this agent have," "I want my agent to halt if X," "DDD agent supervisor," or describes a domain (DDD aggregates, bounded contexts, invariants) and wants to translate it into agent gates.

The pattern: build a `Commission` (`avp.types.Commission`) with the supervisor primitives the situation calls for.

| Concern | Field | Notes |
|---|---|---|
| What the agent can do | `tools` | Each `Tool` has `name`, `description`, `inputSchema` (camelCase per MCP). RPC-impl tools route through the `avp.tool_exec_*` lifecycle (the agent emits requests; the supervisor's service replies with JSON-RPC 2.0 payloads). Local-impl tools the agent has built in are NOT declared here. |
| External MCP servers | `mcp_servers` | Optional list of MCP server endpoints (HTTP or stdio). The agent connects at startup, emits `avp.mcp_server_connected` lifecycle events, and routes tool calls for MCP-hosted tools through them with `tool_exec_resolved.source = avp://mcp/<server_id>`. |
| Which tools to expose | `allowed_tools` | Optional allowlist of names exposed to the model. When present, both agent built-ins AND `Commission.tools` entries are filtered through it; every `Commission.tools` name MUST appear in `allowed_tools` or the agent errors at startup. When absent, the agent exposes its full default set. Use this to compose category-based profiles ("DDD-strict", "Compliance") without enumerating agent internals. |
| What it produces | `output_schema` | JSON schema validated against `agent_stopped.output`. |
| What it runs | `prompt`, `system_prompt`, `model`, `skills` | Standard agent-plane fields. |

See `python/supervisors/simple-supervisor-example/examples/05_anthropic_subagent_delegation.py` for subagents. See `spec/v0.1/examples/commission.json` for a wire-format equivalent.

## Three classes of trajectory facts

Whatever you build, the trajectory carries three distinct kinds of facts. Surface them separately to consumers — don't conflate.

| Class | Event types | Semantics |
|---|---|---|
| What the agent did | `avp.model_turn_*`, `avp.tool_invoked`, `avp.tool_returned`, `avp.tool_failed`, `avp.text_emitted` | Mechanical actions |
| What the run cost | `avp.cost_recorded`, `avp.model_turn_ended.data.gen_ai.usage.*` | Resource accounting (OTel-shaped) |

## Workspace and deployment scope

The agent's workspace is the **agent's current working directory**. Tool inputs containing relative paths resolve there. The supervisor's deployment layer (whatever stages the agent — git checkout, container, tmpdir) is responsible for making referenced files exist in that directory before the run starts.

Workspace provisioning, secret injection, RPC-service hosting, agent placement, and OS-level sandboxing are all **outside AVP's scope** — see `spec/v0.1/SPEC.md` §14. AVP defines the wire, not the deployment topology. If a user asks about any of these and treats AVP as the answer, redirect them to the deployment layer instead.

## What the supervisor is NOT allowed to do

Common temptations to push back on:

- **No mid-run hooks.** The supervisor cannot pause the agent and decide based on what just happened. If the user needs runtime gating, build it as an environmental service the agent calls (RPC tool / MCP server). The rule lives in Commission, not in a callback.
- **No supervisor-emitted runtime events** other than `avp.tool_exec_resolved` RPC replies. Domain interpretations / annotations are post-hoc, not on the runtime wire.

## When in doubt, read these — in this order

1. `spec/v0.1/SPEC.md` — normative spec, RFC 2119 keywords, reference algorithm. The source of truth for any wire-format question.
2. `spec/v0.1/avp.schema.json` — JSON Schema bundle. Authoritative for field-by-field shape.
3. `conformance/v0.1/cases/` — executable test cases that pin down behavior. Read these as worked examples of "what's the right answer when...".
4. `python/avp/src/avp/types.py` — Pydantic models that mirror the schema. Authoritative Python surface.
5. `python/avp/src/avp/agent/agent.py` — the canonical agent loop in working code.
6. `python/agents/avp-anthropic/` — complete real-LLM driver agent.
7. `python/agents/avp-claude-agent/` — observer-pattern agent skeleton.

## Common mistakes to catch

When reviewing AVP code or generating it, watch for:

- Emitting `avp.agent_started` with `source: "avp://supervisor"`. **Wrong** — agent emits, source MUST be `avp://agent`.
- Emitting `avp.tool_exec_resolved` with `source: "avp://agent"`. **Wrong** — that event is the supervisor's reply; source MUST be `avp://supervisor` or `avp://mcp/<server_id>`.
- Subtracting cache-read tokens from `gen_ai.usage.input_tokens`. **Wrong** — per §9.4, cache reads ARE input tokens.
- Computing `total_cost_usd` from `tokens * rate` without accounting for cache discounts. **Wrong** — `avp.cost_usd` per turn is the BILLABLE cost (post-cache-discount); `state.total_cost_usd` is the sum of those.
- Adding a `supervisor_event` type to record domain interpretations. **Wrong** — that's a removed concept; domain annotation is post-hoc, not on the runtime wire.
- Reaching the spec via the `agent-execution-protocol` repo's `python/agent-execution-protocol/` — that path doesn't exist. The Python reference is at `python/avp/`.

## How to operate when the user describes a need

1. Identify which of Tasks A / B / C they're asking about (or which combination).
2. Read the closest match in `python/supervisors/simple-supervisor-example/examples/` (numbered 01–07, narrative format) first to ground yourself in current shape.
3. Cross-reference with `spec/v0.1/SPEC.md` §6 (interactions), §8 (tools), §9 (the loop).
4. For runtime correctness questions, the conformance cases under `conformance/v0.1/cases/` are precedent — find the case that matches the situation.
5. Generate code that imports from `avp.types`, `avp.agent`, `avp.io`. Do NOT inline-redefine the wire types.
6. If asked about a behavior the spec doesn't cover, say so explicitly and propose a path that doesn't violate any of the existing conformance cases.
