# AVP v0.1 Specifications

**Status:** Draft

AVP (Agent Voyager Project) is a set of specs for starting an AI agent on a task and recording what it did. A supervisor, such as a CLI, an evaluation harness, or a hosted platform, sends the agent a Commission describing the task. The agent does the work with its own runtime and reports each step as a trajectory: a list of events covering every model response, tool call, and result.

Every agent that follows AVP accepts the same Commission and produces the same trajectory format. That lets you run different agents on the same task and compare them, rebuild the conversation from a past run, or review a run afterward in a consistent format.

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

The supervisor sends one Commission at the start and nothing after it. The agent emits trajectory events as they happen, from the start of the run to its end, so the supervisor can follow a run live or read it afterward.

The agent may also come with its own tools, skills, and subagents. These are listed in its Agent Descriptor, which the trajectory carries as its second event. A Commission can switch any of these built-in items off; the MCP servers and skills it brings are added alongside them.

## The three specs

| Spec | Defines | How it's used | Schema |
|---|---|---|---|
| [Commission](./commission.md) | The task the supervisor sends: prompt, model, MCP servers, skills, and which built-in items to switch off. | Written by a person or a tool. The supervisor fills in per-run details such as the run ID and sends it to the agent to start a run. The first trajectory event records a copy. | [`commission.schema.json`](./commission.schema.json) |
| [Agent Descriptor](./agent-descriptor.md) | What an agent comes with: its tools, skills, subagents, MCP servers, and supported models. | Read before a run to choose an agent and write a valid Commission. The second trajectory event records a copy. | [`agent-descriptor.schema.json`](./agent-descriptor.schema.json) |
| [Trajectory](./trajectory.md) | The events an agent emits during a run, their order, and how to rebuild the conversation from them. | The supervisor or any later reader uses it to follow a run, total its cost, score it, or rebuild the conversation. | [`trajectory.schema.json`](./trajectory.schema.json) |

All definitions are also bundled in [`avp.schema.json`](./avp.schema.json), with `$id` base `https://avp.dev/schema/v0.1/`. Worked examples are in [`examples/`](./examples/).

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are used as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

## Built on

AVP reuses existing specs wherever one already fits:

- **CloudEvents 1.0**: the envelope for every trajectory event, so standard event tooling can route and store them.
- **OpenTelemetry**: span IDs on every event, so a trajectory loads into tracing backends as a span tree.
- **MCP**: how a Commission names external tool servers, and the shape of tool definitions. The agent's own MCP client talks to those servers.
- **Agent Skills**: the format of skills shipped in a Commission.
- **JSON Schema 2020-12**: the machine-readable form of all three AVP specs.

## Out of scope

AVP defines the shape of the Commission, the Descriptor, and trajectory events. Everything else about running an agent is up to the deployment:

- **Transport.** How the Commission reaches the agent and how events come back: a file, a pipe, HTTP, a message queue, or an in-process call.
- **Workspace.** Which directory the agent works in and how files get there. By convention it is the agent's current working directory, and relative paths in tool inputs resolve against it.
- **Credentials.** How API keys and secrets reach the agent and its MCP servers.
- **MCP server hosting.** Where the servers named in a Commission run.
- **Placement and isolation.** Where the agent runs (subprocess, container, VM) and how it is sandboxed.
- **Orchestration and storage.** Running many agents, and keeping trajectories after a run.

## Versioning

The three specs share one version, v0.1. A Commission declares it in `schema_version` and a Descriptor in `spec_version`; both MUST be `"0.1"`.

While v0.1 is a draft, it may change in incompatible ways. After it is final:

- A minor version may add event types, fields, or enum values, but MUST NOT remove or change existing ones.
- A major version may make breaking changes. It is published in a new sibling directory, and earlier published schemas stay unchanged.
