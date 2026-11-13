# AVP v0.1 Specifications

**Status:** Draft

AVP (Agent Voyager Project) is a set of specs for starting an AI agent on a task and recording what it did. A supervisor, such as a CLI, an evaluation tool, or a hosted platform, sends the agent a Commission describing the task. The agent does the work with its own harness (e.g. Claude Agent SDK or OpenCode) and reports each step as a Trajectory: an ATIF-v1.8 document covering model responses, tool calls, and results.

Every agent that follows AVP accepts the same Commission and produces the same Trajectory format. That lets you run different agents on the same task and compare them, rebuild the conversation from a past run, or review a run afterward in a consistent format.

## Run overview

The supervisor sends one Commission at the start and nothing after it. The
runtime owns model calls, tools, and its loop. Its adapter records native reports
into ATIF and publishes document snapshots, so readers can follow the run or
inspect it afterward.

The Descriptor lists built-in tools, skills, and subagents before the run. The
Commission selects and configures them. Agent Start records the complete resolved
configuration, including full tool definitions and skill contents. The ATIF
trajectory records what the run actually did.

## Contracts

| Spec | Defines | How it's used |
|---|---|---|
| [Commission](./commission.md) | The task the supervisor sends: prompt, model, MCP servers, skills, and which built-in items to switch off. | Written by a person or a tool. The supervisor fills in per-run details such as the run ID and sends it to the agent to start a run. |
| [Agent Descriptor](./agent-descriptor.md) | What an agent comes with: its tools, skills, subagents, MCP servers, and supported models. | Read before a run to choose an agent and write a valid Commission. |
| [Agent Start](./agent-start.md) | The resolved prompts, model, tools, MCP servers, skills with contents, and subagents. | Saved once at start for evaluation and comparison with the requested configuration. |
| [Trajectory](./trajectory.md) | Native ATIF steps, observations, metrics, and operational extensions. | The supervisor uses it to follow a run, total its cost, score it, or rebuild the conversation. |

This document is an overview. The requirements are in the specs above.

## Secrets

A Commission uses references instead of secret values. Each secret is a [Secret reference](./commission.md#34-secret-reference) that says where the value is:

| Reference | The value is in | Allowed in |
|---|---|---|
| `{ "proxy": "anthropic-key" }` | A proxy outside the agent, which adds it to requests as they leave | A Model's `credential`, an HTTP MCP server's `headers` |
| `{ "env": "TEST_DB_PASSWORD" }` | A variable in the agent's environment | Those two, and a stdio MCP server's `env` |

Prefer `proxy`: the agent can use the secret but never read it, so it can't leak it. Use `env` for secrets a proxy can't add, such as a database password.

In the [Commission example](./commission.md#2-example), run with OpenSandbox's [Credential Vault](https://github.com/opensandbox-group/OpenSandbox/blob/main/docs/guides/credential-vault.md) as the proxy:

1. Before the run, the proxy gets `anthropic-key` and `docs-token`, and the agent's environment gets `TEST_DB_PASSWORD`.
2. The agent calls Anthropic with a stand-in key, and the docs server with no token. The proxy adds the real ones.
3. The agent starts the database server with `DB_PASSWORD` set to its own `TEST_DB_PASSWORD`.

**Step 1 is outside AVP**: the supervisor decides which proxy to use, where the values come from, and how the environment is set up. AVP defines only the references and the agent's [rules for using them](./commission.md#59-secrets-come-from-the-proxy-or-the-environment).

## Built on

AVP reuses existing specs wherever one already fits:

- **[ATIF](https://harborframework.com/docs/agents/atif)**: the trajectory format, shared with existing viewers and trace pipelines.
- **[MCP](https://modelcontextprotocol.io/specification)**: how a Commission names external tool servers, and the shape of tool definitions. The agent's own MCP client talks to those servers.
- **[Agent Skills](https://agentskills.io/specification)**: the format of skills shipped in a Commission.
- **[models.dev](https://models.dev)**: the provider and model IDs that name a model, and the prices AVP uses to compute each response's cost.
- **[JSON Schema 2020-12](https://json-schema.org/draft/2020-12)**: the machine-readable form of AVP wire contracts.

## Out of scope

AVP defines the shape of the Commission, the Agent Descriptor, Agent Start, and its ATIF profile. Everything else about running an agent is up to the deployment:

- **Transport.** How the Commission reaches the agent and how trajectory updates come back: a file, a pipe, HTTP, a message queue, or an in-process call.
- **Workspace.** Which folder the agent works in, what files are in it before the run, and how it is cleaned up afterward.
- **Credentials.** Setting up the credential proxy and putting variables in the agent's environment. [Secrets](#secrets) covers what AVP does define.
- **MCP server hosting.** Where the servers named in a Commission run. For a stdio server, the supervisor makes its `command` runnable where the agent runs: the program is installed, and any network it needs is reachable.
- **Placement and isolation.** Where the agent runs (subprocess, container, VM) and how it is sandboxed.
- **Orchestration and storage.** Running many agents, and keeping Trajectories after a run.

## Versioning

The AVP contracts share version v0.1. The Commission, Agent Descriptor, and
Agent Start declare it in `avp_version`; ATIF retains its upstream
`schema_version`.

While v0.1 is a draft, it may change in incompatible ways. After it is final:

- A minor version will only add fields or enum values. It will not remove or change existing ones.
- A major version may make breaking changes. It is published in a new sibling directory, and earlier published schemas stay unchanged.
