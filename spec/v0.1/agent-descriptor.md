# Agent Descriptor Spec

**Status:** Draft

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they appear in all capitals, as shown here.

## 1. Overview

An Agent Descriptor is a JSON object that answers one question: **what is in the agent already?** It lists the agent's name and version, its system prompt, and the tools, skills, subagents (other agents it can hand work to during a run), and MCP servers it comes with. These are the agent's **built-in items**: everything that is consistent between runs of this version of the agent, whether it comes from the agent's harness, from the environment the agent runs in, or from code and configuration the agent's implementer added.

This spec defines the Descriptor's fields and the rules an agent follows when it produces one. [Out of scope](#5-out-of-scope) lists what it leaves to implementations.

A Descriptor describes one version of an agent, identified by `agent_name` and `agent_version`. Anything a supervisor sets for one run belongs on the [Commission](./commission.md) instead.

The [Trajectory](./trajectory.md) spec defines when an agent sends its Descriptor during a run: in `agent_described`, the second event. A Descriptor is also useful before a run. A supervisor that manages several agents can read their Descriptors to get the same summary of each one, and to write Commissions that fit them.

## 2. Example

```json
{
  "avp_version": "0.1",
  "agent_name": "acme-code-agent",
  "agent_version": "1.2.0",
  "supported_models": [
    { "provider": "anthropic", "id": "claude-*" },
    { "provider": "amazon-bedrock", "id": "*anthropic.claude-*" },
    { "provider": "openai", "id": "gpt-5*" }
  ],
  "system_prompt": "You are a careful software engineer...",
  "tools": [
    {
      "name": "read_file",
      "description": "Read a file in the workspace.",
      "inputSchema": {
        "type": "object",
        "properties": { "path": { "type": "string" } },
        "required": ["path"]
      }
    },
    {
      "name": "bash",
      "inputSchema": { "type": "object" }
    },
    {
      "name": "search_issues",
      "description": "Search the issue tracker.",
      "inputSchema": {
        "type": "object",
        "properties": { "query": { "type": "string" } }
      },
      "mcp_server_id": "issues"
    }
  ],
  "mcp_servers": [
    { "id": "issues", "name": "Issue tracker", "status": "connected" }
  ],
  "skills": [
    { "name": "code-review", "description": "Checklist for reviewing a change." }
  ],
  "subagents": [
    { "name": "researcher", "description": "Explores the codebase and reports back." }
  ]
}
```

`read_file` and `bash` run inside the agent. `search_issues` comes from the `issues` MCP server, which its `mcp_server_id` names.

## 3. Reference

### 3.1 Descriptor

| Field | Type | Required | Description |
|---|---|---|---|
| `avp_version` | string | Yes | The AVP version the Descriptor follows. `"0.1"` for this spec. |
| `agent_name` | string | Yes | The agent's name. Matches `^[a-z0-9_-]+$`. |
| `agent_version` | string | Yes | The agent's version. |
| `supported_models` | [Model pattern](#36-model-pattern)[] | No | The models the agent can run. A model is supported when it matches any pattern. Absent means the agent does not say. |
| `system_prompt` | string | No | The system prompt the agent comes with. |
| `tools` | [Tool](#32-tool)[] | No | The agent's built-in tools, including those that come from its MCP servers. |
| `mcp_servers` | [MCP server](#33-mcp-server)[] | No | The MCP servers the agent comes with. |
| `skills` | [Skill](#34-skill)[] | No | The skills the agent comes with. |
| `subagents` | [Subagent](#35-subagent)[] | No | The subagents the agent comes with. |

### 3.2 Tool

A Tool is an [MCP `Tool`](https://modelcontextprotocol.io/specification/latest/server/tools#tool) object with one added field:

| Field | Type | Required | Description |
|---|---|---|---|
| `mcp_server_id` | string | No | The `id` of the [MCP server](#33-mcp-server) the tool comes from. Absent for any tool that does not come from an MCP server. |

### 3.3 MCP server

Unlike an MCP server entry in a [Commission](./commission.md), this entry has no connection details such as a URL, command, or credentials; those stay inside the agent.

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Identifies the server. A [Tool](#32-tool)'s `mcp_server_id` refers to it. |
| `name` | string | No | A display name, when it differs from `id`. |
| `description` | string | No | What the server provides. |
| `status` | string | No | The result of the agent's attempt to connect, one of the values below. |

| `status` | Meaning |
|---|---|
| `connected` | The agent connected and listed the server's tools. |
| `failed` | The connection failed. |
| `needs-auth` | The server requires authorization the agent does not have. |
| `disabled` | The server is turned off, so the agent did not connect. |

### 3.4 Skill

A Skill is the [frontmatter](https://agentskills.io/specification#frontmatter) of the skill's `SKILL.md`, as defined by Agent Skills, with one added field:

| Field | Type | Required | Description |
|---|---|---|---|
| `source` | string | No | A `file:` URI ([RFC 8089](https://www.rfc-editor.org/rfc/rfc8089)) for the directory that contains the skill's `SKILL.md`, as the path appears inside the agent's environment. Absent when the skill is bundled in the agent with no files of its own. |

### 3.5 Subagent

A Subagent uses a subset of the [Descriptor](#31-descriptor)'s fields. It has its own prompt and items, but no `agent_name`, `agent_version`, or `avp_version`: it is part of the agent and ships with it.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Identifies the subagent. |
| `description` | string | No | What the subagent does. |
| `system_prompt` | string | No | As in [Descriptor](#31-descriptor), for the subagent. |
| `tools` | [Tool](#32-tool)[] | No | As in [Descriptor](#31-descriptor), for the subagent. |
| `mcp_servers` | [MCP server](#33-mcp-server)[] | No | As in [Descriptor](#31-descriptor), for the subagent. |
| `skills` | [Skill](#34-skill)[] | No | As in [Descriptor](#31-descriptor), for the subagent. |

A subagent does **not** inherit the agent's items: an absent field means the subagent has none of that item. A subagent that shares the agent's tools, MCP servers, or skills lists them again.

### 3.6 Model pattern

A Model pattern matches the `provider` and `id` of a Commission's [Model](./commission.md#33-model). In both fields, `*` matches any characters, so `{ "provider": "*", "id": "*" }` matches any model.

| Field | Type | Required | Description |
|---|---|---|---|
| `provider` | string | Yes | A pattern for the model's `provider`, for example `"anthropic"`. |
| `id` | string | Yes | A pattern for the model's `id`, for example `"claude-*"`. |

## 4. Rules for agents

These rules apply to the agent that produces a Descriptor, and in the same way to the lists inside each [Subagent](#35-subagent). An agent conforms to this spec if every Descriptor it produces matches the [reference](#3-reference) and follows every MUST and MUST NOT in this section. The overview and the example add no requirements.

### 4.1 Names and IDs are unique

Within one list, the agent MUST NOT repeat a Tool `name`, an MCP server `id`, a Skill `name`, or a Subagent `name`.

### 4.2 All built-in items, and only those, are listed

The agent MUST list all of its [built-in items](#1-overview), including any a Commission turns off. It MUST NOT list items that come from a single run: items a Commission adds, or items it finds in the run's workspace. The [Trajectory](./trajectory.md) records what the run actually uses when the run starts.

### 4.3 An absent list means none

For `tools`, `mcp_servers`, `skills`, and `subagents`, an absent list, a `null` list, and an empty list all mean the agent has none of that item.

### 4.4 Tools from MCP servers

A Tool that comes from an MCP server MUST have an `mcp_server_id`, and any other Tool MUST NOT. A Tool's `mcp_server_id` MUST match the `id` of an MCP server in the same Descriptor or Subagent.

Whenever the agent has connected to its MCP servers, it MUST set each server's `status` and list exactly the tools each `connected` server offered, and no tools from a server with any other `status`. In a Descriptor produced before it connects, the agent MAY leave out `status` and the servers' tools.

### 4.5 Tools match what the model sees

A Tool's `description`, `inputSchema`, and `outputSchema` SHOULD be exactly what the agent gives the model. If the agent cannot see a tool's input schema, it MUST set `inputSchema` to `{ "type": "object" }`.

### 4.6 The Descriptor is the same for every run of a version

For one `agent_name` and `agent_version`, every Descriptor the agent produces MUST have the same fields and list entries, and SHOULD keep the entries in the same order. Two things are exceptions, because they come from the MCP servers and the agent cannot control them:

- Tools that have an `mcp_server_id`.
- MCP server `status`.

These MAY differ between Descriptors, for example when a remote server adds a tool or goes offline. [Tools from MCP servers](#44-tools-from-mcp-servers) says how the agent lists them.

### 4.7 Rules in the Commission spec

How a Commission replaces `system_prompt` or turns off built-in items is defined in the [Commission](./commission.md) spec.

## 5. Out of scope

This spec does not define:

- **Getting a Descriptor before a run.** How a supervisor asks an agent for its Descriptor, for example a command or an HTTP endpoint.
- **Sending a Descriptor.** The transport, file format, or message that carries it.
- **Publishing and discovery.** Registries or catalogs that list agents and their Descriptors.
- **Negotiation.** A supervisor reads a Descriptor and decides what to do; there is no exchange with the agent about it.
- **Checking a model against `supported_models`.** A supervisor can use the list to choose an agent for a Commission's model; what happens on a mismatch is up to the supervisor.
- **Versions of individual items.** AVP has no version field for a tool, skill, subagent, or MCP server; a change to one shows up as a new `agent_version`.
