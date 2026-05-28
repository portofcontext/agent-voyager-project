---
name: avp
description: |
  Use this skill for ANY work on AVP (Agent Voyager Project): agents, supervisor Commissions, conformance cases, or debugging AVP runs. AVP wires agents (drive an LLM, emit events) to supervisors (declare environment).
---

# AVP: Agent Voyager Project

AVP is an open standard for the agent-execution case, defined by four specs that compose independently:

- **Commission** ([`avp/core/spec/v0.1/commission.md`](avp/core/spec/v0.1/commission.md)): what the supervisor sends the agent at startup (model, prompt, inline managed assets, built-in allowlists).
- **Agent Descriptor** ([`avp/core/spec/v0.1/agent-descriptor.md`](avp/core/spec/v0.1/agent-descriptor.md)): what the agent advertises about itself before a run begins.
- **Trajectory** ([`avp/core/spec/v0.1/trajectory.md`](avp/core/spec/v0.1/trajectory.md)): the stream of source-tagged events the agent emits as it runs.
- **Resolver API** ([`avp/core/spec/v0.1/resolver.md`](avp/core/spec/v0.1/resolver.md)): an optional JSON-RPC service for dereferencing opaque refs. The three data-shape specs above are the common path and do not depend on it; the in-repo agents carry inline connection material on the Commission instead of dialing a resolver.

The shape of one run: supervisor sends a Commission; the agent reads it, connects any inline managed assets, runs, and emits the trajectory. **No supervisor to agent push channel.** Once the Commission is sent, the supervisor only observes.

**AVP is built on existing standards.** Every event is a [CloudEvents 1.0](https://cloudevents.io/) envelope carrying OTel span identification (`trace_id`, `span_id`, `parent_span_id`). The `data` payload uses AVP's own `avp.*` attribute namespace (`avp.usage`, `avp.tool.name`, ...); the [OpenTelemetry GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/) conventions are NOT on the wire, but a documented `avp.*` to `gen_ai.*` projection ships for consumers forwarding into OTel-native backends. RPC payloads are [JSON-RPC 2.0](https://www.jsonrpc.org/specification). Tool descriptors are [MCP](https://modelcontextprotocol.io/)-shaped. See `FOUNDATIONS.md` for the full mapping.

## Terms

The vocabulary below is the ubiquitous language of AVP. Every doc, type, and event uses these words consistently. When you generate code or prose, match them.

**Roles**

- **Agent**: the thing that runs the loop. Drives a model, executes tools, emits events. May own the loop directly (it inlines a `while` loop over a per-turn translator) or wrap an SDK that already owns the loop (observer / translator pattern).
- **Supervisor**: the thing that issues the Commission and observes the trajectory. Never pushes mid-run messages to the agent.

**Artifacts** (the two top-level message classes)

- **Commission**: the supervisor's charter for one run. Declares what the agent should do (`prompt`, `system_prompt`, `model`) and the environment it runs in: inline supervisor-managed assets (`mcp_servers` as `McpServerHttp` / `McpServerStdio` with connection material on the wire, `skills` with inline content), plus optional `enabled_builtin_tools` / `enabled_builtin_mcp_servers` / `enabled_builtin_subagents` / `enabled_builtin_skills` allowlists over the agent's Descriptor. Sent once at startup. Type: `Commission`. Wire payload: `run_requested.data["avp.commission"]`.
- **Agent Descriptor**: the agent's self-description. Built-in tools / subagents / skills / mcp_servers, plus `agent_name`, `agent_version`, `spec_version`, `default_model`, `supported_models`, `capabilities`. Per-build, not per-run. Printed by `<agent> describe`. Type: `AgentDescriptor`. Wire payload: `agent_described.data["avp.descriptor"]`.

**Runtime concepts**

- **Run**: one execution of an agent against one Commission. Has a `run_id`. Opens with `run_requested` then `agent_described` then `agent_started`. Closes with `agent_stopped`.
- **Trajectory**: the ordered sequence of events emitted during a run. The source of truth: a non-technical reviewer reads it top-to-bottom to reconstruct what happened.
- **Event**: one CloudEvents 1.0 envelope. Ten types in v0.1, all past-tense facts under the `avp.*` namespace: `run_requested`, `agent_described`, `agent_started`, `agent_stopped`, `assistant_message`, `tool_invoked`, `tool_returned`, `subagent_invoked`, `subagent_returned`, `error_occurred`. See [`trajectory.md`](avp/core/spec/v0.1/trajectory.md) for the full catalog.
- **Turn**: one `assistant_message`, the unit of model invocation accounting. It carries the model's content (`avp.content`) plus the per-turn `avp.usage` and `avp.cost_usd`.

**Environment primitives** (declared inline in the Commission)

- **MCP server**: an inline `mcp_servers[]` entry (`McpServerHttp` with `url` or `McpServerStdio` with `command`); the agent's MCP client dials it directly and runs `tools/list` + `tools/call`. v0.1's mechanism for supervisor-side tool dispatch.
- **Skill**: an inline `skills[]` entry carrying SKILL.md content; the agent materializes it so the model can use it.
- **Built-in allowlists**: `enabled_builtin_tools` (and the `_mcp_servers` / `_subagents` / `_skills` variants) are subtractive filters over what the agent already ships in its Descriptor.

**Wire-format vocabulary**

- **The wire**: the protocol/format level. "On the wire" means "as bytes a consumer parses." Distinct from the trajectory (the logical sequence) and the audit trail (the use case).
- **Source**: the producer URI on each event. Always `avp://agent`: the agent is the sole producer on the wire. Supervisor attribution rides inside `run_requested.data` (`avp.supervisor.*` + `avp.commission`), never on the envelope's `source`.
- **Span**: OTel trace identification (`trace_id`, `span_id`, `parent_span_id`) carried on every event's `data`. Lets the trajectory reconstruct as a span tree (the harness validates that tree on every conformance run).

**Packaging (how implementations are organized in this repo)**

The protocol cares about wire shape, not packaging. But this repo packages two distinct things on top of the wire, and that distinction matters when you're answering "where does new code go" or "what does this package do":

- **Agent**: owns the agent loop, reads a Commission, emits the trajectory, advertises an Agent Descriptor, dispatches tools. An agent is what `avp/core/spec/v0.1/` certifies as conforming, and ships an `avp-conformance.json` manifest honoring `<command> run --commission <path> --out <ndjson>`. Examples: [`agents/avp-claude-agent-sdk/python/`](agents/avp-claude-agent-sdk/python/) (a complete agent built on the Claude Agent SDK, which already ships a loop) and [`agents/avp-goose/rust/`](agents/avp-goose/rust/) (an in-process observer of Block's Goose).
- **Supervisor**: commissions agents and consumes their trajectories. It builds Commissions, runs agents, and reads the events back; it does not own the agent loop. Example: the local CLI [`avp-cli/`](avp-cli/) (command `avp`), which scaffolds a Commission, runs setups (Commission variants) over a dataset against the agents, and ranks a board.

The wire-types binding ([`avp/bindings/python/`](avp/bindings/python/)) ships no agent base class or driver protocol, so each agent owns its loop and emits to an `EventSink`.

Rule of thumb: a thing that owns an agent loop and emits a trajectory is an agent under `agents/<name>/<lang>/`; a thing that commissions agents and reads their trajectories is a supervisor (the local one is the `avp` CLI at `avp-cli/`).

## When to do what

There are three tasks AVP gets used for. Match the user's intent to one of these and follow the relevant pattern.

### Task A: Build an agent (inline-loop pattern)

The user wants their code to OWN the agent loop and use AVP as the wire. Examples: wrapping the Anthropic Messages API, wrapping OpenAI, wrapping a custom LLM, building from scratch.

Use this when: the user says "I want to call Claude / GPT / Gemini and emit AVP" or "wrap my agent loop in AVP" or "build an agent."

You keep your loop and emit AVP events to an `avp.sink.EventSink` using the wire types in the `avp` binding. The binding imposes no base class or driver protocol. The pattern:

1. Read a `Commission` from input. Validate against `avp.commission.Commission`.
2. Emit the prelude: `run_requested`, `agent_described`, `agent_started` (carrying the agent's tool surface, filtered by `enabled_builtin_tools`, plus any inline `mcp_servers[]` with each dial's `status`).
3. Loop, per turn: call your model; emit one `assistant_message` with `avp.content`, `avp.usage`, and `avp.cost_usd`; dispatch the model's tool calls, emitting `tool_invoked` / `tool_returned` for each; append the assistant turn (WITH its tool_calls) and the tool results to history; repeat until the model converges.
4. Emit `agent_stopped` with a `StopReason`. Per-turn cost / token deltas live on each `assistant_message`; the consumer reduces them to compute totals (the agent publishes no cumulative totals).

Emit events to an `avp.sink.EventSink` (the built-in `stdio_sink` writes NDJSON to stdout; `jsonl_sink` writes to a file, which is what the `run --commission --out` contract uses). `agents/avp-goose/rust/src/runner.rs` is a worked agent loop that emits to a sink.

### Task B: Build an agent (observer pattern)

The user wants AVP observability over an SDK that already owns its loop. Examples: Claude Agent SDK, LangChain, AutoGen, an internal framework.

Use this when: the user says "wrap Claude Code as an agent," "make LangChain emit AVP events," or "translate my SDK's lifecycle into AVP." Anywhere they can't own the loop but can subscribe to lifecycle events.

The reference is [`agents/avp-claude-agent-sdk/python/`](agents/avp-claude-agent-sdk/python/): `AVPClaudeSDKClient` is a drop-in `ClaudeSDKClient` subclass that emits the trajectory across `query()` / `receive_response()` / `disconnect()`. The pattern:

1. Probe the SDK for its capability surface and emit the prelude (`run_requested`, `agent_described`, `agent_started`).
2. Translate the Commission into the SDK's setup parameters (e.g. the Claude Agent SDK's `tools` / `mcp_servers`).
3. Subscribe to the SDK's lifecycle (assistant messages, tool use, tool result, completion).
4. Translate each lifecycle event into the corresponding AVP event using the Pydantic models in `avp.trajectory` and `avp.content`, emitting to a sink.
5. Put per-turn cost / token deltas on each `assistant_message`; the supervisor reduces the delta stream. The agent does NOT maintain a cumulative accumulator.

The reference implementation is [`agents/avp-claude-agent-sdk/python/`](agents/avp-claude-agent-sdk/python/): `AVPClaudeSDKClient` is a drop-in `ClaudeSDKClient` subclass that emits the trajectory across `query()` / `receive_response()` / `disconnect()`. The Rust analog is [`agents/avp-goose/rust/`](agents/avp-goose/rust/), an in-process observer of Goose's event stream.

### Task C: Compose a supervisor Commission

The user wants to declare an agent environment: what the agent can do, what rules it must respect, what it should observe. This is the supervisor side.

Use this when: the user says "configure an agent," "lock down an agent," "what tools should this agent have," or describes a domain and wants to translate it into agent gates.

The pattern: build a `Commission` (`avp.commission.Commission`) with the supervisor primitives the situation calls for.

| Concern                     | Field                              | Notes                                                                                                                                   |
| --------------------------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Inline MCP servers          | `mcp_servers`                      | A list of `McpServerHttp` / `McpServerStdio`; connection material is on the wire and the agent dials it. Surfaced on `agent_started.avp.mcp_servers` with each dial's `status`. |
| Inline skills               | `skills`                           | Each carries SKILL.md content the agent materializes.                                                                                    |
| Built-in tool allowlist     | `enabled_builtin_tools`            | Optional list of names. Absent means all built-ins exposed; `[]` means none; a subset means only those names. Validated against the agent's Descriptor at startup (fails with `commission_collision` on unknown names). |
| Built-in MCP / subagent / skill allowlists | `enabled_builtin_{mcp_servers,subagents,skills}` | Same subtractive-filter semantics over the corresponding Descriptor entries. |
| What it produces            | `output_schema`                    | JSON schema.                                                                                                                            |
| What it runs                | `prompt`, `system_prompt`, `model` | Standard agent-plane fields.                                                                                                             |

See `avp/core/spec/v0.1/examples/commission.json` for a wire-format equivalent and `avp-cli/` (the `avp` CLI) for a worked supervisor that composes Commissions from setups and ranks a board.

## Two classes of trajectory facts

Whatever you build, the trajectory carries two distinct kinds of facts. Surface them separately to consumers; don't conflate.

| Class              | Where it lives                                                                  | Semantics                         |
| ------------------ | ------------------------------------------------------------------------------- | --------------------------------- |
| What the agent did | `assistant_message.avp.content`, `tool_invoked`, `tool_returned`, `subagent_invoked`, `subagent_returned` | Mechanical actions                |
| What the run cost  | `assistant_message.avp.usage`, `assistant_message.avp.cost_usd`                 | Resource accounting (per-turn deltas; the consumer reduces them, since `agent_stopped` carries no totals) |

## Workspace and deployment scope

The agent's workspace is the **agent's current working directory**. Tool inputs containing relative paths resolve there. The supervisor's deployment layer (whatever stages the agent: git checkout, container, tmpdir) is responsible for making referenced files exist in that directory before the run starts.

Workspace provisioning, secret injection, agent placement, and OS-level sandboxing are all **outside AVP's scope**. See [`avp/core/spec/v0.1/README.md`](avp/core/spec/v0.1/README.md). AVP defines the wire, not the deployment topology. If a user asks about any of these and treats AVP as the answer, redirect them to the deployment layer instead. (For how the conformance harness sandboxes agent subprocesses locally, see `avp/core/conformance/`.)

## What the supervisor is NOT allowed to do

Common temptations to push back on:

- **No mid-run push to the agent.** Once the Commission is sent, the supervisor only observes the trajectory. If the user needs runtime gating, build it as a managed MCP server (the agent calls it; the supervisor's MCP server decides). The rule lives in the Commission, not in a callback.
- **No supervisor-emitted runtime events.** The agent emits everything (`source=avp://agent` on every event). Supervisor attribution rides inside `run_requested.data` as `avp.supervisor.*` plus the full `avp.commission` snapshot, not on the envelope's `source`.

## When in doubt, read these (in this order)

1. [`avp/core/spec/v0.1/README.md`](avp/core/spec/v0.1/README.md): umbrella entry point indexing the four specs plus shared concerns (foundations, transports, deployment scope, versioning).
2. The relevant spec for your question:
   - **Event stream / loop / cost rules / event catalog** -> `avp/core/spec/v0.1/trajectory.md`
   - **Run-config / allowlists / inline assets** -> `avp/core/spec/v0.1/commission.md`
   - **Agent self-description / capabilities** -> `avp/core/spec/v0.1/agent-descriptor.md`
   - **JSON-RPC methods, bootstrap, error handling** -> `avp/core/spec/v0.1/resolver.md`
3. `avp/core/spec/v0.1/{trajectory,commission,agent-descriptor}.schema.json`: JSON Schemas per spec; authoritative for field-by-field shape, generated from the Pydantic models.
4. `avp/core/conformance/src/avp_conformance/cases/v0.1/`: executable test cases that pin down behavior, plus `COVERAGE.md` (what the suite covers and the deliberate gaps). Read the cases as worked examples of "what's the right answer when...".
5. `avp/bindings/python/src/avp/{commission,descriptor,trajectory}.py`: the Pydantic models that are the source of truth for the schemas, one file per spec. Do NOT inline-redefine the wire types; import them.
6. `agents/avp-goose/rust/src/runner.rs`: a worked agent loop that emits a trajectory to a sink.
7. `agents/avp-claude-agent-sdk/python/` and `agents/avp-goose/rust/`: observer-pattern agents over the Claude Agent SDK and Goose.
8. `avp-cli/`: the local CLI `avp`, a worked supervisor that scaffolds Commissions and runs setups over a dataset against the agents to rank a board.

## How to operate when the user describes a need

1. Identify which of Tasks A / B / C they're asking about (or which combination).
2. Read the closest match first to ground yourself in current shape: the agent packages under `agents/` for Tasks A/B, and `avp-cli/` (run `avp eval demo`, read the catalog configs under `src/avp_cli/catalog/`) for Task C.
3. Cross-reference with the specs: [`commission.md`](avp/core/spec/v0.1/commission.md) (allowlists, inline assets), [`trajectory.md`](avp/core/spec/v0.1/trajectory.md) (the loop, event catalog), [`agent-descriptor.md`](avp/core/spec/v0.1/agent-descriptor.md).
4. For runtime correctness questions, the conformance cases under `avp/core/conformance/src/avp_conformance/cases/v0.1/` are precedent. Find the case that matches the situation.
5. Generate code that imports from the spec-scoped modules (`avp.commission`, `avp.descriptor`, `avp.trajectory`, `avp.content`) plus `avp.sink`. Do NOT inline-redefine the wire types.
6. If asked about a behavior the spec doesn't cover, say so explicitly and propose a path that doesn't violate any of the existing conformance cases.
