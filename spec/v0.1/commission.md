# Commission Spec

**Status:** Draft

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they appear in all capitals, as shown here.

## 1. Overview

A Commission is a JSON object that answers one question: **what should this run do?** It holds the task the agent works on and the settings for one run: the prompt, the model, and optionally a system prompt, the MCP servers and skills to add, and which of the agent's [built-in items](./agent-descriptor.md#1-overview) the run may use.

A supervisor (the system that starts the run, such as a CLI or an evaluation tool) writes the Commission and sends it to the agent at the start of the run. It sends nothing after that: everything the agent needs from the supervisor is in the Commission. Credentials are never in it. It names each one instead: either a credential that a proxy outside the agent holds and adds to the agent's requests, or a variable in the agent's environment.

This spec defines the Commission's fields, the rules a supervisor follows when it writes one, and the rules an agent follows when it runs one. [Out of scope](#6-out-of-scope) lists what it leaves to implementations.

The [Agent Descriptor](./agent-descriptor.md) lists what the agent has before any Commission. For one run, a Commission can add items, replace the system prompt, and limit which built-in items are used; the Descriptor itself stays the same. The [Trajectory](./trajectory.md) spec records a copy of the Commission in [`run_requested`](./trajectory.md#33-run_requested), the first event, and records what the run actually uses in [`agent_started`](./trajectory.md#35-agent_started).

## 2. Example

```json
{
  "avp_version": "0.1",
  "run_id": "fix-login-bug-0412",
  "supervisor": { "name": "acme-ci", "version": "3.1.0" },
  "prompt": "Fix the login timeout bug described in issue #212.",
  "system_prompt": "You are a careful software engineer. Do not push changes.",
  "model": {
    "provider": "anthropic",
    "id": "claude-sonnet-4-6",
    "credential": { "proxy": "anthropic-key" }
  },
  "mcp_servers": [
    {
      "id": "docs",
      "name": "Team docs",
      "type": "http",
      "url": "https://mcp.example.com/docs",
      "headers": { "Authorization": { "proxy": "docs-token" } }
    },
    {
      "id": "db",
      "name": "Test database",
      "type": "stdio",
      "command": ["npx", "-y", "@example/db-mcp", "--read-only"],
      "env": { "DB_PASSWORD": { "env": "TEST_DB_PASSWORD" } }
    }
  ],
  "skills": [
    {
      "name": "release-notes",
      "files": {
        "SKILL.md": "---\nname: release-notes\ndescription: How to write a release note for a fix.\n---\n..."
      }
    }
  ],
  "agents": {
    "acme-code-agent": {
      "version": "1.2.0",
      "enabled_tools": ["read_file"],
      "enabled_subagents": []
    }
  },
  "tags": ["bugfix"],
  "meta": { "ticket": "ENG-212" }
}
```

The `acme-code-agent` key refers to the agent in the [Descriptor example](./agent-descriptor.md#2-example). With these lists, the run can use `read_file` but not `bash` or the `researcher` subagent. The entry has no `enabled_mcp_servers` list, so the `issues` server and its `search_issues` tool stay available: an [absent list limits nothing](#52-agent-settings-limit-the-built-in-items). The `db` server's `DB_PASSWORD` gets the value of the agent's own `TEST_DB_PASSWORD` variable; the README's [Secrets](./README.md#secrets) section walks through how each secret in this example reaches its service.

## 3. Reference

### 3.1 Commission

| Field | Type | Required | Description |
|---|---|---|---|
| `avp_version` | string | Yes | The AVP version the Commission follows. `"0.1"` for this spec. |
| `run_id` | string | Yes | The run's ID, chosen by the supervisor. Every [Trajectory event](./trajectory.md#31-event) carries it as `run_id`. |
| `model` | [Model](#33-model) | Yes | The model to run, and the service that runs it. |
| `prompt` | string | Yes | The first user message of the run. |
| `supervisor` | [Supervisor](#32-supervisor) | No | The supervisor that wrote the Commission. |
| `system_prompt` | string | No | The system prompt for the run. It [replaces the agent's own](#55-system_prompt-replaces-the-agents-own). |
| `mcp_servers` | [MCP server](#35-mcp-server)[] | No | MCP servers to add for the run. |
| `skills` | [Skill](#36-skill)[] | No | Skills to add for the run. |
| `agents` | map<string, [Agent settings](#37-agent-settings)> | No | Settings for specific agents. Each key is an agent's `agent_name` from its [Descriptor](./agent-descriptor.md#31-descriptor). |
| `output_schema` | [JSON Schema](https://json-schema.org/draft/2020-12) | No | The shape of the agent's final output. |
| `thread_id` | string | No | An ID that groups related runs, such as the turns of one conversation. |
| `tags` | string[] | No | Labels for the run. |
| `meta` | map<string, any> | No | Key-value data for the supervisor's own use. |

### 3.2 Supervisor

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | The supervisor's name, for example `"avp-cli"`. |
| `version` | string | No | The supervisor's version. |

### 3.3 Model

A Model names a model as one service offers it, using the provider and model IDs from [models.dev](https://models.dev). The same model has a different `id` at each service: Claude Sonnet 4.6 is `claude-sonnet-4-6` at `anthropic` and `us.anthropic.claude-sonnet-4-6` at `amazon-bedrock`.

| Field | Type | Required | Description |
|---|---|---|---|
| `provider` | string | Yes | The service that runs the model, for example `"anthropic"`, `"amazon-bedrock"`, or `"openrouter"`. It decides which API the agent calls and how it authenticates. Matches `^[a-z0-9._-]+$`. |
| `id` | string | Yes | The model's ID at that service, as the agent sends it, for example `"claude-sonnet-4-6"` or `"anthropic/claude-sonnet-4.6"` at OpenRouter. |
| `base_url` | string | No | The URL of the service's API, for example a region's endpoint or a self-hosted server. Absent means the service's default: models.dev's `api` for the provider, or the URL the agent's client for that service uses. |
| `credential` | [Secret reference](#34-secret-reference) | No | The API key for the service. Absent means the Commission names none, and the agent uses whatever credential its environment has for the service. |

### 3.4 Secret reference

A Secret reference names a secret without containing it. It has exactly one of the fields below.

| Field | Type | Required | Description |
|---|---|---|---|
| `proxy` | string | One of | The name of a credential that a proxy outside the agent holds, for example a credential in an [OpenSandbox Credential Vault](https://github.com/opensandbox-group/OpenSandbox/blob/main/docs/guides/credential-vault.md). The proxy adds it to the agent's matching requests, so the agent never receives its value. Matches `^[a-z0-9_-]+$`. |
| `env` | string | One of | The name of a variable in the agent's environment that holds the secret, for example `"TEST_DB_PASSWORD"`. Matches `^[A-Za-z_][A-Za-z0-9_]*$`. |

A proxy can only add a secret to a request that leaves the agent, so `proxy` is allowed only in a Model's `credential` and an HTTP server's `headers`. `env` is allowed in all three places that take a Secret reference.

### 3.5 MCP server

An MCP server entry tells the agent how to connect to one MCP server. Its `id`, `name`, and `description` mean the same as in a [Descriptor's MCP server](./agent-descriptor.md#33-mcp-server). The other fields depend on `type`, which names the [MCP transport](https://modelcontextprotocol.io/specification/latest/basic/transports).

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Identifies the server. Matches `^[a-z0-9_-]+$`. |
| `name` | string | No | A display name, when it differs from `id`. |
| `description` | string | No | What the server provides. |
| `type` | string | Yes | `"http"` for [HTTP](#351-http) or `"stdio"` for [stdio](#352-stdio). |

#### 3.5.1 HTTP

A server the agent connects to over MCP's Streamable HTTP transport.

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | Yes | The server's URL. |
| `headers` | map<string, string \| [Secret reference](#34-secret-reference)> | No | HTTP headers to send with each request. Each key is a header name. A value is a string, or a Secret reference whose secret is the header's entire value: with `"Authorization": { "env": "DOCS_AUTH" }`, `DOCS_AUTH` holds `Bearer <token>`, not the token alone. |

#### 3.5.2 stdio

A server the agent starts as a local program and talks to over its standard input and output.

| Field | Type | Required | Description |
|---|---|---|---|
| `command` | string[] | Yes | The program and its arguments, for example `["npx", "-y", "@example/db-mcp"]`. At least one item. |
| `env` | map<string, string \| [Secret reference](#34-secret-reference)> | No | Environment variables to set for the program, on top of those the agent's MCP client gives it. Each key is a variable name. A value is a string, or a Secret reference with `env`, which takes the value from a variable in the agent's own environment: with `"DB_PASSWORD": { "env": "TEST_DB_PASSWORD" }`, the program's `DB_PASSWORD` is set to the value of the agent's `TEST_DB_PASSWORD`. |

### 3.6 Skill

A Skill carries a skill directory, as defined by [Agent Skills](https://agentskills.io/specification), inside the Commission. The skill's `name` and `description` are in the frontmatter of its `SKILL.md`. The Skill's `name` field stands in for the skill's directory name, which Agent Skills requires to equal the frontmatter `name`.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | The skill's name. Equals the `name` in the frontmatter of its `SKILL.md`, and follows the [Agent Skills naming rules](https://agentskills.io/specification#name-field). |
| `files` | map<string, string> | Yes | The skill's files. Each key is a path relative to the skill directory, and each value is the file's UTF-8 content. Includes `"SKILL.md"`. |

### 3.7 Agent settings

Agent settings apply to the agent whose `agent_name` is their key in [`agents`](#31-commission). Each list names built-in items from that agent's [Descriptor](./agent-descriptor.md#31-descriptor). [Agent settings limit the built-in items](#52-agent-settings-limit-the-built-in-items) says what an absent or empty list means.

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | string | No | The `agent_version` the Commission was written for. |
| `enabled_tools` | string[] | No | The built-in tools the run may use, by their `name` in the Descriptor's `tools`. Covers only tools without an `mcp_server_id`; `enabled_mcp_servers` covers the rest. |
| `enabled_subagents` | string[] | No | The built-in subagents the run may use, by their `name` in the Descriptor's `subagents`. |
| `enabled_skills` | string[] | No | The built-in skills the run may use, by their `name` in the Descriptor's `skills`. |
| `enabled_mcp_servers` | string[] | No | The built-in MCP servers the run may use, by their `id` in the Descriptor's `mcp_servers`. |

## 4. Rules for supervisors

These rules apply to the supervisor that writes a Commission. A supervisor conforms to this spec if every Commission it writes matches the [reference](#3-reference) and follows every MUST and MUST NOT in this section. The overview and the example add no requirements.

### 4.1 Each run has its own `run_id`

The supervisor MUST give every Commission it sends a `run_id` it has not used before.

### 4.2 IDs are unique

Within one Commission, the supervisor MUST NOT repeat an MCP server `id` or a skill `name`. Within one HTTP server's `headers`, it MUST NOT repeat a header name, ignoring case.

### 4.3 Secrets are only in Secret references

The supervisor MUST NOT write a secret value anywhere in a Commission, including `url`, `meta`, and the string values in `headers` and `env`. It MUST name each secret with a [Secret reference](#34-secret-reference) instead.

### 4.4 `model` uses models.dev names

`model.id` MUST be the ID the service takes for the model. When models.dev lists the service, `model.provider` SHOULD be its models.dev provider ID, and `model.id` SHOULD be one of that provider's model IDs, so prices and model details can be looked up.

### 4.5 Agent settings name real built-in items

Before it sends a Commission, the supervisor SHOULD check each entry in `agents` against that agent's Descriptor: `version` matches its `agent_version`, and every name in an `enabled_*` list is in the matching Descriptor list.

### 4.6 Secrets stay out of the agent's reach

The supervisor SHOULD use `proxy` wherever a proxy can add the secret, and `env` only where none can, such as a database with no proxy that logs in for the client. An agent that holds a secret can leak it, for example after a prompt injection or through code it runs; a secret held by a proxy outside the agent can only be used, never read. OpenSandbox's [Credential Vault](https://github.com/opensandbox-group/OpenSandbox/blob/main/docs/guides/credential-vault.md) is one such proxy.

## 5. Rules for agents

These rules apply to the agent that runs a Commission. An agent conforms to this spec if it follows every MUST and MUST NOT in this section. The overview and the example add no requirements.

### 5.1 The agent checks the Commission before the run starts

Before its first model call, the agent MUST refuse the Commission in each case below marked MUST, and SHOULD refuse it in each case marked SHOULD. To refuse, it ends the run with an [`error_occurred`](./trajectory.md#311-error_occurred) event with the code `invalid_commission` and a message that says which case applies. The run never starts, so there is no `agent_started` or `agent_stopped`.

| Case | Level |
|---|---|
| `agents` is present and has no entry for the agent's `agent_name`. | MUST |
| The agent's entry has a `version` that differs from the agent's `agent_version`. | MUST |
| An `enabled_*` list in the agent's entry names an item that is not in the matching list of the agent's Descriptor. For `enabled_tools`, only tools without an `mcp_server_id` count. | MUST |
| A skill's `name` differs from the `name` in the frontmatter of its `SKILL.md`. | MUST |
| The Commission adds an MCP server whose `id` matches the `id` of an MCP server in the agent's Descriptor, or a skill whose name matches the `name` of a skill there. | SHOULD |
| The agent cannot call `model.provider`, or `model.base_url` when it is present. | MUST |
| The agent knows the service doesn't offer `model.id`. | SHOULD |

### 5.2 Agent settings limit the built-in items

Each `enabled_*` list in the agent's [Agent settings](#37-agent-settings) controls one kind of built-in item:

- If the list is absent, the run may use every built-in item of that kind. This includes a Commission with no `agents`.
- If the list is present, the run may use only the items it names, matched exactly. An empty list means none.

A tool from a built-in MCP server the run may not use is not available either.

### 5.3 Turned-off items are hidden and blocked

The agent SHOULD NOT offer a built-in item the run may not use to the model. If the model calls one anyway, the agent MUST NOT run it, and MUST record the call as failed: its [`tool_returned`](./trajectory.md#38-tool_returned) event has `is_error` set to `true`.

### 5.4 Added items are used, or the run stops

Before its first model call, the agent MUST connect to every MCP server and load every skill in the Commission. [Agent settings](#37-agent-settings) do not apply to them.

If an MCP server in the Commission does not reach `connected` status, the agent MUST NOT start the run. It ends the run with an [`error_occurred`](./trajectory.md#311-error_occurred) event with the code `mcp_connect_failed` and a message that names the server, and sends no `agent_started` or `agent_stopped`.

### 5.5 `system_prompt` replaces the agent's own

When a Commission has `system_prompt`, the agent MUST use it instead of its own system prompt, and MUST NOT add its own to it.

### 5.6 The run uses `model`

The agent MUST send its own model calls for `model.id` to the service `model.provider` names, at `model.base_url` when it is present, and MUST NOT use a different model or service for them. This rule does not cover the models that subagents or the agent's runtime choose for their own calls. If the agent cannot call the service, it [refuses the Commission](#51-the-agent-checks-the-commission-before-the-run-starts).

### 5.7 The agent checks its final output against `output_schema`

When a Commission has `output_schema` and the model gives its final answer, the agent MUST check the final output against it. How the agent gets output that matches, for example with retries or an output tool, is up to the agent. If the output doesn't match, the agent MUST send an [`error_occurred`](./trajectory.md#311-error_occurred) with the code `output_invalid`, then `agent_stopped` with `reason` set to `error` and the output in `output`. So with `output_schema`, the `output` of an `agent_stopped` with `reason` `converged` always matches it.

### 5.8 Secrets stay out of the Trajectory

The agent MUST NOT write a secret value it receives into any Trajectory event.

### 5.9 Secrets come from the proxy or the environment

For a `proxy` reference, the agent MUST send the requests that need the credential to the URL in the Commission, unchanged, so the proxy can add it. The agent MUST NOT need the credential's value. For a header, the agent MAY leave the header out. When its runtime requires a value, for example an SDK that won't start without an API key, the agent MAY use any stand-in; the proxy replaces it.

For an `env` reference, the agent MUST use the value of the named variable in its own environment wherever the secret goes: as the model's API key, as an HTTP server's header value, or as a stdio server's variable.

## 6. Out of scope

- **Sending a Commission:** how it reaches the agent, for example as a file, over stdin, or over HTTP.
- **Changing a run after it starts:** the supervisor sends nothing after the Commission.
- **Choosing an agent:** finding one, or one that can run a given model.
- **Providing secrets:** setting up the proxy and its credentials, and setting the variables in the agent's environment.
- **The run's environment:** the workspace, files, sandbox, and network access.
- **`thread_id`, `tags`, and `meta`:** AVP gives them no meaning beyond their descriptions in the [Commission](#31-commission) reference.
- **Tool name clashes:** two MCP servers that offer tools with the same name. The agent's MCP client handles them as it normally does.
