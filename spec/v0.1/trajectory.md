# Trajectory Spec

**Status:** Draft

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they appear in all capitals, as shown here.

## 1. Overview

A Trajectory is the record of one run. It answers one question: **what did the agent do?** It is a list of events in the order the agent sent them. The agent sends each event as it happens, so the supervisor can follow a run live or read the whole record afterward.

The events record:

- How the run started: the [Commission](./commission.md) the agent received, the agent's [Agent Descriptor](./agent-descriptor.md), and the prompt, model, and items the run actually uses.
- Each model response, with its content, token counts, and cost.
- Each tool call and its result, and each run of a [subagent](./agent-descriptor.md#35-subagent).
- Errors, and how the run ended.

The agent produces a Trajectory, and the supervisor reads it. Here the supervisor is any tool that reads the record of a run: the one that sent the Commission, a scorer, a dashboard, or a pipeline that turns runs into training data. A run doesn't need a Commission, so a developer who starts the agent from their own code can use the Trajectory just for observability. From the events, the supervisor can rebuild the conversation the model saw, add up the run's cost, and see what each tool call and subagent did.

Each event is a JSON object. Events link to each other through IDs: for example, a tool call's `tool_call_id` matches the `tool_use` block in the model response that asked for it.

This spec defines the events, their fields, and the rules for the agents that produce them and the supervisors that read them. [Out of scope](#6-out-of-scope) lists what it leaves to implementations.

## 2. Example

```text
run_requested        Commission for run fix-login-bug-0412
agent_described      Descriptor for acme-code-agent 1.2.0
agent_started        model anthropic/claude-sonnet-4-6; tools read_file, search_issues, ...
  assistant_message  text, and a call to search_issues        ┐ loop: repeats
    tool_invoked     search_issues {"query": "#212"}          │ once per model
      tool_returned  issue #212: login times out after 30 s   │ response
  assistant_message  a call to read_file                      │
    tool_invoked     read_file {"path": "src/auth/login.py"}  │
      tool_returned  the file's contents                      │
  assistant_message  the final answer, with no tool calls     ┘
  agent_stopped      converged
```

This is the run from the [Commission example](./commission.md#2-example), one event per line. Indentation shows which event led to which: each line comes from the closest line above it with less indentation. The [reference](#3-reference) gives each event in full.

## 3. Reference

A Trajectory is a list of [Events](#31-event). Every event has the same top-level fields; its `data` holds the fields of its [event type](#32-event-types).

### 3.1 Event

An Event is AVP's own object.

| Field | Type | Required | Description |
|---|---|---|---|
| `avp_version` | string | Yes | The AVP version the event follows. `"0.1"` for this spec. |
| `id` | string | Yes | Identifies the event. |
| `type` | string | Yes | The name of an [event type](#32-event-types), such as `tool_invoked`. |
| `time` | string | Yes | When the event happened, as an [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339) timestamp. |
| `run_id` | string | Yes | The run's ID, the same on every event of the run: the Commission's `run_id`, or an ID the agent chooses when it has no Commission. |
| `meta` | map<string, any> | No | The agent's own annotations. AVP gives them no meaning. |
| `data` | object | Yes | The fields of the event's [type](#32-event-types). |

```json
{
  "avp_version": "0.1",
  "id": "5f0c6a52-8a4e-4c1b-9d0e-2b7f3e1c9a10",
  "type": "tool_invoked",
  "time": "2026-10-28T14:03:12.481Z",
  "run_id": "fix-login-bug-0412",
  "data": {
    "tool_call_id": "toolu_01",
    "tool_name": "search_issues",
    "tool_input": { "query": "#212" },
    "mcp_server_id": "issues"
  }
}
```

### 3.2 Event types

Every event type is AVP's own.

| `type` | Records |
|---|---|
| [`run_requested`](#33-run_requested) | The start of the run, with the Commission the agent received. |
| [`agent_described`](#34-agent_described) | The agent's Agent Descriptor. |
| [`agent_started`](#35-agent_started) | What the run uses: its prompt, its model, and its items after the Commission's limits and additions. |
| [`assistant_message`](#36-assistant_message) | One model response, with its content, token counts, and cost. |
| [`tool_invoked`](#37-tool_invoked) | A tool call. |
| [`tool_returned`](#38-tool_returned) | The result of a tool call. |
| [`subagent_invoked`](#39-subagent_invoked) | The start of a subagent's run. |
| [`subagent_returned`](#310-subagent_returned) | The end of a subagent's run, with its result. |
| [`error_occurred`](#311-error_occurred) | An error. |
| [`agent_stopped`](#312-agent_stopped) | The end of the run, and why it ended. |

The [rules for agents](#4-rules-for-agents) say when the agent sends each event.

### 3.3 `run_requested`

| Field | Type | Required | Description |
|---|---|---|---|
| `commission` | [Commission](./commission.md#31-commission) | No | The Commission the agent received. Absent when the run has [no Commission](#1-overview). |

```json
{
  "avp_version": "0.1",
  "id": "0b8e3f6c-2d47-4a59-8c1e-7f9a0d3b5e21",
  "type": "run_requested",
  "time": "2026-10-28T14:03:09.002Z",
  "run_id": "fix-login-bug-0412",
  "data": {
    "commission": { "avp_version": "0.1", "run_id": "fix-login-bug-0412", "...": "..." }
  }
}
```

`commission` holds the whole [Commission example](./commission.md#2-example), shortened here.

### 3.4 `agent_described`

| Field | Type | Required | Description |
|---|---|---|---|
| `descriptor` | [Agent Descriptor](./agent-descriptor.md#31-descriptor) | Yes | The agent's Descriptor. |

```json
{
  "avp_version": "0.1",
  "id": "7c41d9e2-5b38-4f06-a1d7-3e8c2b9f0a64",
  "type": "agent_described",
  "time": "2026-10-28T14:03:09.004Z",
  "run_id": "fix-login-bug-0412",
  "data": {
    "descriptor": { "avp_version": "0.1", "agent_name": "acme-code-agent", "agent_version": "1.2.0", "...": "..." }
  }
}
```

`descriptor` holds the whole [Descriptor example](./agent-descriptor.md#2-example), shortened here.

### 3.5 `agent_started`

`agent_started` uses a subset of the [Descriptor](./agent-descriptor.md#31-descriptor)'s fields, plus `prompt` and `model`. Their values are what the run uses: the agent's Descriptor combined with the [Commission](./commission.md), which [limits the built-in items](./commission.md#52-agent-settings-limit-the-built-in-items), [adds its own](./commission.md#54-added-items-are-used-or-the-run-stops), and [replaces the system prompt](./commission.md#55-system_prompt-replaces-the-agents-own). Without a Commission, they hold what the agent was started with.

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt` | string | Yes | The prompt the run starts with. |
| `system_prompt` | string | No | As in [Descriptor](./agent-descriptor.md#31-descriptor), for the run. |
| `model` | [Model](./commission.md#33-model) | Yes | The model the run uses, without `credential`. |
| `tools` | [Tool](./agent-descriptor.md#32-tool)[] | No | As in [Descriptor](./agent-descriptor.md#31-descriptor), for the run. |
| `mcp_servers` | [MCP server](./agent-descriptor.md#33-mcp-server)[] | No | As in [Descriptor](./agent-descriptor.md#31-descriptor), for the run. |
| `skills` | [Skill](./agent-descriptor.md#34-skill)[] | No | As in [Descriptor](./agent-descriptor.md#31-descriptor), for the run. |
| `subagents` | [Subagent](./agent-descriptor.md#35-subagent)[] | No | As in [Descriptor](./agent-descriptor.md#31-descriptor), for the run. |

```json
{
  "avp_version": "0.1",
  "id": "2e9a7c15-4d83-4b6f-9a02-8c5d1f3e7b46",
  "type": "agent_started",
  "time": "2026-10-28T14:03:10.317Z",
  "run_id": "fix-login-bug-0412",
  "data": {
    "prompt": "Fix the login timeout bug described in issue #212.",
    "system_prompt": "You are a careful software engineer. Do not push changes.",
    "model": { "provider": "anthropic", "id": "claude-sonnet-4-6" },
    "tools": [
      {
        "name": "read_file",
        "description": "Read a file in the workspace.",
        "inputSchema": { "type": "object", "properties": { "path": { "type": "string" } }, "required": ["path"] }
      },
      {
        "name": "search_issues",
        "description": "Search the issue tracker.",
        "inputSchema": { "type": "object", "properties": { "query": { "type": "string" } } },
        "mcp_server_id": "issues"
      },
      {
        "name": "search_docs",
        "inputSchema": { "type": "object", "properties": { "query": { "type": "string" } } },
        "mcp_server_id": "docs"
      },
      {
        "name": "run_query",
        "inputSchema": { "type": "object", "properties": { "sql": { "type": "string" } } },
        "mcp_server_id": "db"
      }
    ],
    "mcp_servers": [
      { "id": "issues", "name": "Issue tracker", "status": "connected" },
      { "id": "docs", "name": "Team docs", "status": "connected" },
      { "id": "db", "name": "Test database", "status": "connected" }
    ],
    "skills": [
      { "name": "code-review", "description": "Checklist for reviewing a change." },
      {
        "name": "release-notes",
        "description": "How to write a release note for a fix.",
        "source": "file:///workspace/.avp/skills/release-notes"
      }
    ]
  }
}
```

### 3.6 `assistant_message`

| Field | Type | Required | Description |
|---|---|---|---|
| `content` | [Content block](#313-content-blocks)[] | Yes | What the model produced: text, reasoning, tool calls, and other blocks. |
| `model` | object | Yes | The model the agent asked for this response, as in [`agent_started`](#35-agent_started). |
| `response_model` | string | No | The model ID the service says produced the response, at the same `provider`, when it differs from `model.id` (for example a dated version). |
| `finish_reasons` | string[] | No | Why the model stopped, exactly as the service reported it. |
| `duration_ms` | integer | Yes | How long the response took, in milliseconds, ending at the event's `time`. |
| `usage` | [Usage](#361-usage) | Yes | The response's token counts and cost. |
| `subagent_invocation_id` | string | No | When a subagent made the response, the `invocation_id` of its [`subagent_invoked`](#39-subagent_invoked). Absent for the main agent's responses. |

```json
{
  "avp_version": "0.1",
  "id": "9d2f6b80-3c1e-4e7a-b5f4-61a8c0d29e37",
  "type": "assistant_message",
  "time": "2026-10-28T14:03:12.470Z",
  "run_id": "fix-login-bug-0412",
  "data": {
    "content": [
      { "type": "text", "text": "I'll start by reading issue #212." },
      { "type": "tool_use", "id": "toolu_01", "name": "search_issues", "input": { "query": "#212" } }
    ],
    "model": { "provider": "anthropic", "id": "claude-sonnet-4-6" },
    "response_model": "claude-sonnet-4-6-20260214",
    "finish_reasons": ["tool_use"],
    "duration_ms": 2140,
    "usage": {
      "input_tokens": 4210,
      "output_tokens": 58,
      "cache_read_input_tokens": 3900,
      "cache_creation_input_tokens": 0,
      "cost_usd": 0.00297,
      "cost_source": "computed"
    }
  }
}
```

#### 3.6.1 Usage

Token counts and cost for one model response.

| Field | Type | Required | Description |
|---|---|---|---|
| `input_tokens` | integer | Yes | All input tokens, including those read from and written to the cache. |
| `output_tokens` | integer | Yes | All output tokens, including reasoning tokens. |
| `cache_read_input_tokens` | integer | No | The input tokens read from the cache. Included in `input_tokens`. |
| `cache_creation_input_tokens` | integer | No | The input tokens written to the cache. Included in `input_tokens`. |
| `reasoning_output_tokens` | integer | No | The output tokens the model spent on reasoning. Included in `output_tokens`. |
| `cost_usd` | number | Yes | The cost in US dollars, after any cache discount. |
| `cost_source` | string | Yes | Where `cost_usd` comes from, one of the values below. |

| `cost_source` | Meaning |
|---|---|
| `computed` | The agent computed the cost from the token counts and the [models.dev](https://models.dev) prices for the model at its provider. |
| `reported` | The service or the agent's runtime reported the cost. |
| `unknown` | The cost could not be found. |

### 3.7 `tool_invoked`

| Field | Type | Required | Description |
|---|---|---|---|
| `tool_call_id` | string | Yes | Identifies the call: the `id` of its `tool_use` [content block](#313-content-blocks). |
| `tool_name` | string | Yes | The name the agent called the tool by. |
| `tool_input` | map<string, any> | Yes | The arguments, as in the `tool_use` block's `input`. |
| `mcp_server_id` | string | No | The `id` of the MCP server that runs the tool, as in [`agent_started`](#35-agent_started)'s `mcp_servers`. Absent for a tool that doesn't come from an MCP server. |
| `subagent_invocation_id` | string | No | When a subagent made the call, the `invocation_id` of its [`subagent_invoked`](#39-subagent_invoked). Absent when the main agent made the call. |

The [Event](#31-event) example is a `tool_invoked` event.

### 3.8 `tool_returned`

| Field | Type | Required | Description |
|---|---|---|---|
| `tool_call_id` | string | Yes | As in the matching [`tool_invoked`](#37-tool_invoked). |
| `tool_name` | string | Yes | As in the matching `tool_invoked`. |
| `duration_ms` | integer | Yes | How long the tool took, in milliseconds, ending at the event's `time`. |
| `tool_result` | `tool_result` [content block](#313-content-blocks) | Yes | The result, as the model receives it. |
| `subagent_invocation_id` | string | No | As in the matching `tool_invoked`. |

```json
{
  "avp_version": "0.1",
  "id": "e6a1b4f3-9c27-4d58-8f0e-2a7c5d913b84",
  "type": "tool_returned",
  "time": "2026-10-28T14:03:12.903Z",
  "run_id": "fix-login-bug-0412",
  "data": {
    "tool_call_id": "toolu_01",
    "tool_name": "search_issues",
    "duration_ms": 412,
    "tool_result": {
      "type": "tool_result",
      "tool_use_id": "toolu_01",
      "content": "#212 Login times out after 30 s when SSO is slow. Reported in auth/login.py."
    }
  }
}
```

### 3.9 `subagent_invoked`

| Field | Type | Required | Description |
|---|---|---|---|
| `subagent_name` | string | Yes | The subagent's `name`, as in [`agent_started`](#35-agent_started)'s `subagents`. |
| `invocation_id` | string | Yes | Identifies this run of the subagent. When a tool call started it, the call's `tool_call_id`. |
| `subagent_invocation_id` | string | No | When another subagent started this one, the `invocation_id` of its `subagent_invoked`. Absent when the main agent started it. |
| `subagent_input` | map<string, any> | Yes | The input the subagent was given. |

The examples in this section and the next come from a run whose Commission allows the `researcher` subagent.

```json
{
  "avp_version": "0.1",
  "id": "4a8c2e71-6f0b-4d93-a5e8-1c7b3f9d2e60",
  "type": "subagent_invoked",
  "time": "2026-10-28T15:21:04.118Z",
  "run_id": "explore-auth-0413",
  "data": {
    "subagent_name": "researcher",
    "invocation_id": "toolu_07",
    "subagent_input": { "prompt": "Find every place the login timeout is set." }
  }
}
```

### 3.10 `subagent_returned`

| Field | Type | Required | Description |
|---|---|---|---|
| `subagent_name` | string | Yes | As in the matching [`subagent_invoked`](#39-subagent_invoked). |
| `invocation_id` | string | Yes | As in the matching `subagent_invoked`. |
| `subagent_invocation_id` | string | No | As in the matching `subagent_invoked`. |
| `duration_ms` | integer | Yes | How long the subagent ran, in milliseconds, ending at the event's `time`. |
| `subagent_reason` | string | Yes | Why the subagent stopped, one of the [stop reasons](#3121-stop-reasons). |
| `subagent_result_text` | string | Yes | The subagent's final text, or the error message when `subagent_reason` is `error`. |
| `subagent_usage` | [Subagent usage](#3101-subagent-usage) | No | The subagent's totals, when the agent can't record its responses as events of their own. |

```json
{
  "avp_version": "0.1",
  "id": "b19e5d37-0a6c-4f82-9d41-7e3a8c2f6b05",
  "type": "subagent_returned",
  "time": "2026-10-28T15:21:51.640Z",
  "run_id": "explore-auth-0413",
  "data": {
    "subagent_name": "researcher",
    "invocation_id": "toolu_07",
    "duration_ms": 47522,
    "subagent_reason": "converged",
    "subagent_result_text": "The timeout is set in auth/login.py:42 and config/sso.yaml:9.",
    "subagent_usage": { "input_tokens": 18200, "output_tokens": 1240, "responses": 6 }
  }
}
```

#### 3.10.1 Subagent usage

Subagent usage has the fields of [Usage](#361-usage), all optional, totaled over the subagent's run, plus the field below. A field is absent when the agent couldn't measure it.

| Field | Type | Required | Description |
|---|---|---|---|
| `responses` | integer | No | How many model responses the subagent made. |

### 3.11 `error_occurred`

| Field | Type | Required | Description |
|---|---|---|---|
| `error_code` | string | Yes | What kind of error, one of the [error codes](#3111-error-codes). |
| `error_message` | string | Yes | What went wrong, for a person to read. |
| `subagent_invocation_id` | string | No | When the error happened in a subagent, the `invocation_id` of its [`subagent_invoked`](#39-subagent_invoked). Absent for the main agent's errors. |

The example below comes from a run like the [Commission example](./commission.md#2-example)'s, in which the `db` MCP server couldn't connect, so the run ended before `agent_started`.

```json
{
  "avp_version": "0.1",
  "id": "c62f8e14-3b7a-4d05-9e81-5a0d2c6f4b93",
  "type": "error_occurred",
  "time": "2026-10-28T16:40:05.772Z",
  "run_id": "fix-login-bug-0415",
  "data": {
    "error_code": "mcp_connect_failed",
    "error_message": "MCP server db: connection refused at https://db.internal.example/mcp"
  }
}
```

#### 3.11.1 Error codes

| Code | Meaning |
|---|---|
| `invalid_commission` | The agent refused the Commission, as the Commission spec's [rules for agents](./commission.md#51-the-agent-checks-the-commission-before-the-run-starts) require. The message says which rule. |
| `mcp_connect_failed` | An MCP server the Commission added didn't connect, so the run [didn't start](./commission.md#54-added-items-are-used-or-the-run-stops). The message names the server. |
| `auth_error` | The model service rejected the agent's credentials. |
| `rate_limit` | The model service refused a request because of a rate or usage limit. |
| `context_limit` | A request was longer than the model's context window. |
| `output_invalid` | The final output didn't match the Commission's `output_schema`, as the Commission spec's [rule on final output](./commission.md#57-the-agent-checks-its-final-output-against-output_schema) describes. The output is in `agent_stopped`'s `output`. |
| `agent_crash` | The agent failed, or the model service failed. Also used when someone stops the run from outside before `agent_started`. |
| `unknown` | Any other error. |

### 3.12 `agent_stopped`

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | Yes | Why the run stopped, one of the [stop reasons](#3121-stop-reasons). |
| `output` | any | No | The run's result as the agent reports it: a string, or an object when the run has structured output. With `reason` `error`, it can be output that didn't match `output_schema`. Absent when the agent reports none. |

```json
{
  "avp_version": "0.1",
  "id": "e3a71c9b-5d28-4f60-b0e4-8c2d6a1f7b39",
  "type": "agent_stopped",
  "time": "2026-10-28T14:03:21.356Z",
  "run_id": "fix-login-bug-0412",
  "data": {
    "reason": "converged",
    "output": "Issue #212 comes from the 30 s SSO timeout in src/auth/login.py. Raising it to 60 s fixes the login timeouts."
  }
}
```

#### 3.12.1 Stop reasons

The same values say why a subagent stopped, in [`subagent_returned`](#310-subagent_returned).

| Reason | Meaning |
|---|---|
| `converged` | The model gave its final answer. |
| `refused` | The model declined the task. |
| `error` | The run failed. |
| `interrupted` | Someone stopped the run from outside, for example with SIGINT or SIGTERM. |
| `abandoned` | The run ended while a subagent it started was still running, so the run has no complete answer. For a subagent: the run ended while the subagent was still running. |

### 3.13 Content blocks

`assistant_message`'s `content` and `tool_returned`'s `tool_result` hold content blocks. A content block is a JSON object whose `type` says which kind it is. The kinds follow the content blocks of [Anthropic's Messages API](https://docs.anthropic.com/en/api/messages), and cover the messages of OpenAI, Google Gemini, AWS Bedrock, Cohere, and Mistral too.

| `type` | Fields | Holds |
|---|---|---|
| `text` | `text` (string, required), `citations` ([Citation](#3131-citation)[], optional) | Text from the model. |
| `thinking` | `thinking` (string, required), `signature` (string, optional), `redacted` (boolean, optional) | The model's reasoning. `signature` is the service's token for passing the reasoning back to it. When `redacted` is true, `thinking` holds the service's encrypted reasoning, not text to show. |
| `image` | `source` ([Source](#3132-source), required) | An image. |
| `tool_use` | `id` (string, required), `name` (string, required), `input` (map<string, any>, required) | A call to a tool the agent runs. |
| `tool_result` | `tool_use_id` (string, required), `content` (string, or `text` and `image` blocks, required), `structured_content` (map<string, any>, optional), `is_error` (boolean, optional) | The result of a `tool_use` call, matched by `tool_use_id`. `structured_content` is a result meant for programs, such as MCP's `structuredContent`, given beside `content`. |
| `server_tool_use` | `id` (string, required), `name` (string, required), `input` (map<string, any>, required) | A call to a tool the model service runs itself, such as web search. The agent doesn't run it, so it has no `tool_invoked` event. |
| `server_tool_result` | `tool_use_id` (string, required), `name` (string, required), `content` (any, required), `is_error` (boolean, optional) | The result of a `server_tool_use` call, in the same `assistant_message`. |
| `refusal` | `refusal` (string, required) | The model's text when it declined. |

A block can also hold fields the model service added that AVP doesn't list, such as Gemini's `thought_signature`, so the agent can pass them back to the service.

#### 3.13.1 Citation

A source the model cited for a text block.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | The kind of citation, as the model service names it, such as `url_citation`. |
| `cited_text` | string | No | The text cited. |
| `start_index` | integer | No | Where the cited part of the block's `text` starts. |
| `end_index` | integer | No | Where it ends. |
| `source_id` | string | No | The service's ID for the source. |
| `source_url` | string | No | The source's URL. |
| `source_title` | string | No | The source's title. |

#### 3.13.2 Source

Where an image's data is. In v0.1 the data is always inline.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | `base64`. |
| `media_type` | string | Yes | The image's media type, such as `image/png`. |
| `data` | string | Yes | The image, base64-encoded. |

## 4. Rules for agents

These rules apply to the agent that produces a Trajectory. An agent conforms to this spec if every event it sends matches the [reference](#3-reference) and it follows every MUST and MUST NOT in this section. The overview and the examples add no requirements.

### 4.1 Events come in a fixed order

Every run starts with `run_requested`, then `agent_described`. After that, the run either:

- starts: `agent_started`, then the run's other events, and `agent_stopped` last; or
- ends before it starts: `error_occurred` last, with no `agent_started` or `agent_stopped`.

The agent MUST send events in this order and MUST NOT send any event after the last one. It MUST NOT send `agent_stopped` without `agent_started`. An `error_occurred` after `agent_started` doesn't end the run; only `agent_stopped` does.

Each `assistant_message` comes before the events it led to, such as its tool calls. A `tool_invoked` comes before its `tool_returned`, and a `subagent_invoked` before its `subagent_returned`.

The agent MUST NOT give two events in a Trajectory the same `id`.

### 4.2 The first events record the run's inputs

When the run has a Commission, `run_requested`'s `commission` MUST be the Commission exactly as the agent received it. When it has none, `commission` MUST be absent.

`agent_described`'s `descriptor` MUST be the agent's [Agent Descriptor](./agent-descriptor.md).

`agent_started` MUST list what the run can use: the built-in items the Commission doesn't turn off, and the items it adds. `mcp_servers` lists every server the agent tried to connect to, and its servers and tools follow the Descriptor's [rules for MCP servers](./agent-descriptor.md#44-tools-from-mcp-servers).

### 4.3 One `assistant_message` per model response

The agent MUST send one `assistant_message` for each model response that produced content, and no others. A message its runtime repeats or wraps, with no new model call behind it, is not a response.

`content` MUST hold every block the model produced, in order. The supervisor can then rebuild the conversation sent to the model from each `assistant_message`'s `content` and each `tool_returned`'s `tool_result`.

### 4.4 Usage is per response

Each `assistant_message`'s `usage` MUST count only that response. The agent MUST NOT send totals for the run. When its runtime reports running totals, the agent subtracts the previous total to get each response's counts.

All token counts and `cost_usd` are 0 or more. `cache_read_input_tokens` plus `cache_creation_input_tokens` MUST NOT exceed `input_tokens`. When the service or the agent's runtime reports a response's cost, the agent MUST use it, with `cost_source` `reported`. Otherwise it prices the response from the models.dev entry for `model.provider` and `response_model`, or `model.id` when models.dev doesn't list `response_model`, with `cost_source` `computed`, so a supervisor with the same prices gets the same cost. When models.dev lists neither, `cost_source` is `unknown` and `cost_usd` MUST be `0`.

### 4.5 Every tool call has a result

For every `tool_use` block in an `assistant_message`, the agent MUST send a `tool_invoked`, then a `tool_returned` with the same `tool_call_id`. `tool_result.is_error` MUST be `true` when the call failed, including a call the agent refused to run, such as a call to an item the Commission [turned off](./commission.md#53-turned-off-items-are-hidden-and-blocked).

A `server_tool_use` block has no `tool_invoked` or `tool_returned`: the model service runs the tool, and its result is a `server_tool_result` block in the same `content`.

### 4.6 Subagents

Every `subagent_invoked` MUST be followed by a `subagent_returned` with the same `invocation_id`, before `agent_stopped`.

When a tool call started the subagent, `invocation_id` MUST be that call's `tool_call_id`, and the call's `tool_returned` MUST have `is_error` set to `true` exactly when `subagent_reason` isn't `converged`.

If the run ends while a subagent is still running, the agent MUST send its `subagent_returned` with `subagent_reason` set to `abandoned`. `agent_stopped`'s `reason` MUST then not be `converged`; it SHOULD be `abandoned`, unless the run ended as `error`, `refused`, or `interrupted`. A subagent that returns a receipt and reports later is still running until it reports.

The agent SHOULD report the subagent's own model responses and tool calls as events, as they happen:

- Each `assistant_message`, `tool_invoked`, `tool_returned`, `subagent_invoked`, `subagent_returned`, and `error_occurred` the agent reports for a subagent MUST have `subagent_invocation_id` set to that subagent's `invocation_id`.
- When the agent reports the subagent's model responses, it MUST NOT set `subagent_usage`, so the supervisor doesn't count them twice. When it doesn't, it SHOULD set `subagent_usage`.

### 4.7 Errors and stops

When the run fails, the agent MUST send an `error_occurred` that says why, then `agent_stopped` with `reason` set to `error`. Before `agent_started`, it sends only the `error_occurred`.

When someone stops the run from outside, for example with SIGINT or SIGTERM, the agent MUST stop its runtime and end the Trajectory before it exits. After `agent_started`, it closes any running subagent as [abandoned](#46-subagents) and sends `agent_stopped` with `reason` set to `interrupted`. Before `agent_started`, it sends `error_occurred` with the code `agent_crash`.

## 5. Rules for supervisors

These rules apply to the supervisor that reads a Trajectory. A supervisor conforms to this spec if it follows every MUST and MUST NOT in this section.

### 5.1 Unknown values are read safely

The supervisor MUST treat an error code it doesn't know as `unknown`, and MUST skip an event whose `type` it doesn't know. Later versions of AVP can then add codes and event types without breaking supervisors.

### 5.2 Totals come from the events

The agent sends no totals, so the supervisor adds them up:

- **Tokens and cost:** the sum of `usage` over every `assistant_message`, the subagents' included, plus the `subagent_usage` of each `subagent_returned` that has one. `cache_read_input_tokens` and `cache_creation_input_tokens` are already in `input_tokens`, and `reasoning_output_tokens` is already in `output_tokens`; the supervisor MUST NOT add them again.
- **Unknown cost:** when any response has `cost_source` set to `unknown`, or a `subagent_usage` has no `cost_usd`, the run's cost is at least the sum, not exactly it. The supervisor MUST NOT report such a response or subagent as free.
- **Duration:** `agent_stopped`'s `time` minus `agent_started`'s `time`.

### 5.3 A Trajectory without its last event is incomplete

A Trajectory is complete when it ends with `agent_stopped`, or with `error_occurred` before `agent_started`. If it ends any other way, the agent stopped without closing it, for example because it was killed. The supervisor MUST NOT treat an incomplete Trajectory as a run that converged.

## 6. Out of scope

This spec does not define:

- **Sending a Trajectory:** how events reach the supervisor, for example as a file of JSON lines, over stdout, or over a network connection.
- **Storing Trajectories:** where they are kept, for how long, and how runs are found later.
- **Runs together:** scheduling runs, or comparing and linking them; each Trajectory is one run.
- **How a subagent is started:** the agent decides when and how to run one; the Trajectory records what happened.
- **Converting a Trajectory:** to [OpenTelemetry](https://opentelemetry.io/docs/specs/otel/trace/api/) spans, [CloudEvents](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md), or training-data formats such as [ATIF](https://github.com/harbor-framework/harbor).
- **Judging a run:** scores, policy checks, and other conclusions the supervisor draws from the events.
