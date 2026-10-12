---
name: avp
description: |
  Use this skill for ANY work on AVP (Agent Voyager Project): agents, supervisor Commissions, conformance cases, or debugging AVP runs. AVP wires agents (drive an LLM, emit events) to supervisors (declare environment).
---

# AVP: Agent Voyager Project

AVP is an open standard for the agent-execution case, defined by three specs that compose independently:

- **Commission** ([`avp/core/spec/v0.1/commission.md`](avp/core/spec/v0.1/commission.md)): what the supervisor sends the agent at startup (model, prompt, inline managed assets, built-in allowlists).
- **Agent Descriptor** ([`avp/core/spec/v0.1/agent-descriptor.md`](avp/core/spec/v0.1/agent-descriptor.md)): what the agent advertises about itself before a run begins.
- **Trajectory** ([`avp/core/spec/v0.1/trajectory.md`](avp/core/spec/v0.1/trajectory.md)): the stream of source-tagged events the agent emits as it runs.

The shape of one run: supervisor sends a Commission; the agent reads it, connects any inline managed assets, runs, and emits the trajectory. **No supervisor to agent push channel.** Once the Commission is sent, the supervisor only observes.

**AVP is built on existing standards.** Every event is a [CloudEvents 1.0](https://cloudevents.io/) envelope carrying OTel span identification (`trace_id`, `span_id`, `parent_span_id`). The `data` payload uses AVP's own `avp.*` attribute namespace (`avp.usage`, `avp.tool.name`, ...); the [OpenTelemetry GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/) conventions are NOT on the wire, but a documented `avp.*` to `gen_ai.*` projection ships for consumers forwarding into OTel-native backends. Tool descriptors are [MCP](https://modelcontextprotocol.io/)-shaped. Skill content follows [Agent Skills](https://agentskills.io/specification). See `FOUNDATIONS.md` for the full mapping.

## Terms

The vocabulary below is the ubiquitous language of AVP. Every doc, type, and event uses these words consistently. When you generate code or prose, match them.

**Roles**

- **Agent**: the thing that runs the loop. Drives a model, executes tools, emits events. AVP adapters observe an existing runtime that owns the model/tool loop.
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

The binding ([`avp/bindings/python/`](avp/bindings/python/)) supplies wire types, sinks, and a Recorder. Adapters translate native runtime events into Recorder reports; the runtime owns execution.

Rule of thumb: a thing that owns an agent loop and emits a trajectory is an agent under `agents/<name>/<lang>/`; a thing that commissions agents and reads their trajectories is a supervisor (the local one is the `avp` CLI at `avp-cli/`).

## When to do what

AVP integrations either adapt an existing agent runtime or configure one from a supervisor.

### Task A: Adapt an agent runtime

Use this when the user wants an SDK or agent runtime to accept Commissions and
emit AVP trajectories. The runtime owns the model/tool loop.

Start with [`agents/_template/README.md`](agents/_template/README.md):

1. Scaffold a Python or Rust adapter with `make new-agent` or `make new-agent-rust`.
2. Replace the scripted harness with the runtime and map Commission fields into
   its configuration. Declare its supported capabilities and built-ins.
3. Translate native model responses, tool results, subagents, and completion into
   Recorder reports. Preserve model-response boundaries and per-response usage.
4. Use the stock `ping`, `describe`, and `run` entrypoint and shared preflight checks.
5. Validate the adapter with seam tests and the live conformance suite.

Worked adapters: [Claude Agent SDK](agents/avp-claude-agent-sdk/python/),
[Goose](agents/avp-goose/rust/), [OpenAI Agents](agents/avp-openai-agents/python/),
and [Codex](agents/avp-codex/python/). See [integration patterns](PATTERNS.md)
for Recorder responsibilities and launcher-owned context.

### Task B: Compose a supervisor Commission

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

## Using the `avp` CLI (the worked supervisor)

When the task is to RUN or EVALUATE agents (not author wire bytes), use the `avp`
CLI. It installs to `uv tool install avp-cli`; every `avp eval` / `avp run`
executes the agent in a Docker-backed sandbox (the one prerequisite is Docker).

- `avp init [benchmark]`: scaffold a `<name>.eval.json` and seed its commissions into `~/.avp/commissions/`.
- `avp eval run <config>.eval.json`: run the commissions over the dataset and print a ranked board (accuracy, pass-rate, $/run, turns/run).
- `avp cm create [id]` / `avp cm check <id|file>`: build a Commission into the library / validate a Commission (library id or JSON file).
- `avp agent install <name>` / `avp agent list` / `avp agent describe <name>`: install and inspect agents (goose, claude-code).
- `avp run --agent A --env E "<task>"`: drop an agent into a declarative environment and give it a task.

An **eval is a JSON config**, not code: `{name, agents, dataset, scorer, commissions}`.
- `dataset.source`: `inline` (items array), `file` (a `.jsonl` path + `input` template + `expected_field`), or `huggingface` (`id` + `split` + `input` + `expected_field`; needs the `huggingface` extra).
- `scorer.name`: `exact-match`, `structural-match` (fraction of expected dict keys matched), `structural-fidelity` (rapidfuzz table-content match; needs the `parsebench` extra), or `llm-judge` (needs the `llm-judge` extra + a key).
- `commissions`: ids resolved from the library; each commission carries its own `model` (no eval-level default).

Worked example: **ParseBench** (PDF table extraction): a `huggingface` dataset
(`id: "llamaindex/ParseBench"`, a `split` like `"table[:2]"`, an `input` URL
template, an `expected_field`), the `structural-fidelity` scorer, and a commission
that wires a PDF-vision MCP server (stdio `pdf-vision`) plus the `shell`/`write`/`edit`
built-in tools. See `avp-cli/src/avp_cli/catalog/` for the catalog configs.

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

1. [`avp/core/spec/v0.1/README.md`](avp/core/spec/v0.1/README.md): umbrella entry point indexing the three specs plus shared concerns (foundations, transports, deployment scope, versioning).
2. The relevant spec for your question:
   - **Event stream / loop / cost rules / event catalog** -> `avp/core/spec/v0.1/trajectory.md`
   - **Run-config / allowlists / inline assets** -> `avp/core/spec/v0.1/commission.md`
   - **Agent self-description / capabilities** -> `avp/core/spec/v0.1/agent-descriptor.md`
3. `avp/core/spec/v0.1/{trajectory,commission,agent-descriptor}.schema.json`: JSON Schemas per spec; authoritative for field-by-field shape, generated from the Pydantic models.
4. `avp/core/conformance/src/avp_conformance/cases/v0.1/`: executable test cases that pin down behavior, plus `COVERAGE.md` (what the suite covers and the deliberate gaps). Read the cases as worked examples of "what's the right answer when...".
5. `avp/bindings/python/src/avp/{commission,descriptor,trajectory}.py`: the Pydantic models that are the source of truth for the schemas, one file per spec. Do NOT inline-redefine the wire types; import them.
6. `agents/avp-goose/rust/src/runner.rs`: an adapter observing Goose’s native event stream.
7. `agents/avp-claude-agent-sdk/python/` and `agents/avp-goose/rust/`: observer-pattern agents over the Claude Agent SDK and Goose.
8. `avp-cli/`: the local CLI `avp`, a worked supervisor that scaffolds Commissions and runs setups over a dataset against the agents to rank a board.

## How to operate when the user describes a need

1. Identify which of Tasks A / B they're asking about (or which combination).
2. Read the closest match first to ground yourself in current shape: the agent packages under `agents/` for Task A, and `avp-cli/` (read the catalog configs under `src/avp_cli/catalog/`) for Task B.
3. Cross-reference with the specs: [`commission.md`](avp/core/spec/v0.1/commission.md) (allowlists, inline assets), [`trajectory.md`](avp/core/spec/v0.1/trajectory.md) (the loop, event catalog), [`agent-descriptor.md`](avp/core/spec/v0.1/agent-descriptor.md).
4. For runtime correctness questions, the conformance cases under `avp/core/conformance/src/avp_conformance/cases/v0.1/` are precedent. Find the case that matches the situation.
5. Generate code that imports from the spec-scoped modules (`avp.commission`, `avp.descriptor`, `avp.trajectory`, `avp.content`) plus `avp.sink`. Do NOT inline-redefine the wire types.
6. If asked about a behavior the spec doesn't cover, say so explicitly and propose a path that doesn't violate any of the existing conformance cases.
