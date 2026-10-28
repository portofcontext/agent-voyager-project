# AVP v0.1 Specifications

**Status:** Draft

AVP (Agent Voyager Project) is a set of specs for starting an AI agent on a task and recording what it did. A supervisor, such as a CLI, an evaluation tool, or a hosted platform, sends the agent a Commission describing the task. The agent does the work with its own harness (e.g. Claude Agent SDK or Goose) and reports each step as a Trajectory: a list of events covering every model response, tool call, and result.

Every agent that follows AVP accepts the same Commission and produces the same Trajectory format. That lets you run different agents on the same task and compare them, rebuild the conversation from a past run, or review a run afterward in a consistent format.

## Run overview

```
supervisor                             agent
    │                                    │
    │─────────── Commission ────────────▶│
    │◀────────── run_requested ──────────│
    │◀───────── agent_described ─────────│
    │                                    │  connects to MCP servers,
    │                                    │  loads skills
    │◀────────── agent_started ──────────│
    │◀──────── assistant_message ────────│  model responds
    │◀────────── tool_invoked ───────────│  handles a tool call
    │◀────────── tool_returned ──────────│
    │                ...                 │
    │◀────────── agent_stopped ──────────│  run ends
```

The supervisor sends one Commission at the start and nothing after it. The agent emits Trajectory events as they happen, from the start of the run to its end, so the supervisor can follow a run live or read it afterward. The diagram shows a sample; the Trajectory spec defines every event type and the required order.

The agent may also come with its own tools, skills, and subagents (other agents it can hand work to). These are listed in its Agent Descriptor, which the Trajectory carries as its second event. A Commission can switch any of these built-in items off; the MCP servers and skills it brings are added alongside them.

## The three specs

| Spec | Defines | How it's used | Schema |
|---|---|---|---|
| [Commission](./commission.md) | The task the supervisor sends: prompt, model, MCP servers, skills, and which built-in items to switch off. | Written by a person or a tool. The supervisor fills in per-run details such as the run ID and sends it to the agent to start a run. The first Trajectory event records a copy. | [`commission.schema.json`](./commission.schema.json) |
| [Agent Descriptor](./agent-descriptor.md) | What an agent comes with: its tools, skills, subagents, MCP servers, and supported models. | Read before a run to choose an agent and write a valid Commission. The second Trajectory event records a copy. | [`agent-descriptor.schema.json`](./agent-descriptor.schema.json) |
| [Trajectory](./trajectory.md) | The events an agent emits during a run, their order, and how to rebuild the conversation from them. | The supervisor or any later reader uses it to follow a run, total its cost, score it, or rebuild the conversation. | [`trajectory.schema.json`](./trajectory.schema.json) |

All definitions are also bundled in [`avp.schema.json`](./avp.schema.json), with `$id` base `https://www.agentvoyagerproject.com/schema/v0.1/`. Worked examples are in [`examples/`](./examples/).

This document is an overview. The requirements are in the three specs above.

## Built on

AVP reuses existing specs wherever one already fits:

- **[MCP](https://modelcontextprotocol.io/specification)**: how a Commission names external tool servers, and the shape of tool definitions. The agent's own MCP client talks to those servers.
- **[Agent Skills](https://agentskills.io/specification)**: the format of skills shipped in a Commission.
- **[models.dev](https://models.dev)**: the `origin/model` names for models, and the prices AVP uses to compute each response's cost.
- **[JSON Schema 2020-12](https://json-schema.org/draft/2020-12)**: the machine-readable form of all three AVP specs.

Trajectory events are not [CloudEvents](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md), and no spec relies on CloudEvents. Each event converts to one, with `run_id` as the `subject`, so a supervisor can forward a Trajectory to event infrastructure that routes CloudEvents.

Trajectory events hold no [OpenTelemetry](https://opentelemetry.io/docs/specs/otel/trace/api/) span IDs either. A Trajectory converts to OpenTelemetry spans: the run, each model response, and each tool call or subagent become spans, linked through the events' IDs.

## Out of scope

AVP defines the shape of the Commission, the Agent Descriptor, and Trajectory events. Everything else about running an agent is up to the deployment:

- **Transport.** How the Commission reaches the agent and how events come back: a file, a pipe, HTTP, a message queue, or an in-process call.
- **Workspace.** Which folder the agent works in, what files are in it before the run, and how it is cleaned up afterward.
- **Credentials.** How API keys and secrets reach the agent and its MCP servers.
- **MCP server hosting.** Where the servers named in a Commission run.
- **Placement and isolation.** Where the agent runs (subprocess, container, VM) and how it is sandboxed.
- **Orchestration and storage.** Running many agents, and keeping Trajectories after a run.

## Versioning

The three specs share one version, v0.1. The Commission and the Agent Descriptor both declare it in `avp_version`.

While v0.1 is a draft, it may change in incompatible ways. After it is final:

- A minor version will only add event types, fields, or enum values. It will not remove or change existing ones.
- A major version may make breaking changes. It is published in a new sibling directory, and earlier published schemas stay unchanged.
