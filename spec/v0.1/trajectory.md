# Trajectory Spec

**Status:** Draft

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they appear in all capitals, as shown here.

## 1. Overview

A Trajectory is a JSON document that answers one question: **what happened in this run?** It records the prompts, each model response, the tool calls and their results, the subagents the run started, token usage and cost, and why the run stopped.

A Trajectory is an [ATIF v1.8](https://github.com/harbor-framework/harbor/blob/9c7a39b991d7e2205019f6be0598cbd22d84bfc3/rfcs/0001-trajectory-format.md) (Agent Trajectory Interchange Format) document, with a [JSON Schema](trajectory.schema.json). AVP uses ATIF's standard fields as ATIF defines them, and puts its additions in ATIF's `extra` objects under `avp`, so any ATIF reader can read the conversation.

This spec defines the `extra.avp` fields, the rules an agent follows when it writes a Trajectory, and the rules a reader follows. [Out of scope](#6-out-of-scope) lists what it leaves to implementations.

A Trajectory records what one run did, not what the [Commission](./commission.md) asked for or the [Agent Descriptor](./agent-descriptor.md) offered.

## 2. Example

```json
{
  "schema_version": "ATIF-v1.8",
  "session_id": "fix-login-bug-0412",
  "agent": {
    "name": "acme-code-agent",
    "version": "1.2.0",
    "model_name": "claude-sonnet-4-6",
    "tool_definitions": [
      {
        "type": "function",
        "function": {
          "name": "read_file",
          "description": "Read a file in the workspace.",
          "parameters": {
            "type": "object",
            "properties": {
              "path": {
                "type": "string"
              }
            },
            "required": [
              "path"
            ]
          }
        }
      }
    ]
  },
  "steps": [
    {
      "step_id": 1,
      "timestamp": "2026-01-01T00:00:00Z",
      "source": "user",
      "message": "Fix the login timeout bug described in issue #212."
    },
    {
      "step_id": 2,
      "timestamp": "2026-01-01T00:00:01Z",
      "source": "agent",
      "model_name": "claude-sonnet-4-6",
      "message": "I'll read the login handler first.",
      "tool_calls": [
        {
          "tool_call_id": "call-1",
          "function_name": "read_file",
          "arguments": {
            "path": "src/login.py"
          }
        }
      ],
      "observation": {
        "results": [
          {
            "source_call_id": "call-1",
            "content": "def login(): ..."
          }
        ]
      },
      "metrics": {
        "prompt_tokens": 1200,
        "completion_tokens": 40,
        "cost_usd": 0.0042
      },
      "llm_call_count": 1
    },
    {
      "step_id": 3,
      "timestamp": "2026-01-01T00:00:02Z",
      "source": "agent",
      "model_name": "claude-sonnet-4-6",
      "message": "Fixed: the timeout now reads from settings.",
      "metrics": {
        "prompt_tokens": 1300,
        "completion_tokens": 12
      },
      "llm_call_count": 1
    }
  ],
  "final_metrics": {
    "total_prompt_tokens": 2500,
    "total_completion_tokens": 52,
    "total_steps": 3
  }
}
```

The run's `session_id` is the Commission's `run_id`. The second response has no `cost_usd`, so its cost is unknown, and `final_metrics` leaves the total cost out.

## 3. Reference

The [ATIF RFC](https://github.com/harbor-framework/harbor/blob/9c7a39b991d7e2205019f6be0598cbd22d84bfc3/rfcs/0001-trajectory-format.md) define every standard field. This section defines only the `extra.avp` objects AVP adds. Each one sits at `extra.avp` on the ATIF object its section names.

Every field in an `extra.avp` object is optional unless its table says otherwise; an agent leaves a field out when it does not know the value. [Readers accept unknown keys](#52-unknown-values-are-read-safely).

### 3.1 Trajectory

At the trajectory's top-level `extra.avp`, and on each embedded subagent trajectory.

| Field | Type | Required | Description |
|---|---|---|---|
| `avp_version` | string | Yes | The AVP version the Trajectory follows. `"0.1"` for this spec. |
| `commission` | [Commission](./commission.md#31-commission), or any | Yes, when the run has a Commission | The Commission exactly as the agent received it, including one it then refuses. When what it received doesn't match the Commission spec, the JSON value it received, or the text when it isn't JSON. Absent when the run has no Commission. |
| `started_at` | string | Yes, unless the run was [refused](#412-a-refused-run-has-no-model-responses) | When the run started, as an [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339) timestamp. It can be earlier than the first step, since the agent can do work before it records one. |
| `stopped_at` | string | Yes | When the run stopped, as an RFC 3339 timestamp. |
| `stop_reason` | [Stop reason](#311-stop-reason) | Yes | Why the run stopped. |
| `output` | any | No | The run's result, when it differs from the last agent message or has a different JSON type, for example structured output. `null` means the run returned no result. Absent means the result is the last agent message. |

#### 3.1.1 Stop reason

| Value | Meaning |
|---|---|
| `converged` | The model gave its final answer. |
| `refused` | The model declined the task. |
| `error` | The run failed. A `system` step with an `error_code` says why. |
| `interrupted` | Someone stopped the run from outside, for example with SIGINT or SIGTERM. |
| `abandoned` | The run ended while a subagent it started was still running, so the run has no complete answer. On a subagent trajectory: the run ended while the subagent was still running. |

### 3.2 Agent

At `agent.extra.avp`. An embedded subagent trajectory has its own. The values are what the run used: the agent's [Descriptor](./agent-descriptor.md) combined with the [Commission](./commission.md), which [limits the built-in items](./commission.md#52-agent-settings-limit-the-built-in-items), [adds its own](./commission.md#54-added-items-are-used-or-the-run-stops), and [replaces the system prompt](./commission.md#55-system_prompt-replaces-the-agents-own). The prompt, system prompt, model ID, and each tool's name, description, and input schema are in standard ATIF fields, so they are not repeated here.

| Field | Type | Required | Description |
|---|---|---|---|
| `descriptor` | [Agent Descriptor](./agent-descriptor.md#31-descriptor) | Yes, on the root trajectory | The agent's Descriptor, unchanged. Absent on subagent trajectories. |
| `model` | [Model](#321-model) | Yes, unless the run was [refused](#412-a-refused-run-has-no-model-responses) | The service that runs the model in `agent.model_name`. |
| `tools` | map<string, [Tool](#322-tool)> | No | For each tool in `agent.tool_definitions`, keyed by its name, the fields ATIF's tool definition can't hold. |
| `mcp_servers` | [MCP server](./agent-descriptor.md#33-mcp-server)[] | No | The MCP servers the run used, with their `status`. |
| `skills` | [Skill](./agent-descriptor.md#34-skill)[] | No | The skills the run used. `source` points to the saved skill directory. |
| `subagents` | [Subagent](./agent-descriptor.md#35-subagent)[] | No | The subagents available to the run. |

For `tools`, `mcp_servers`, `skills`, and `subagents`, an absent list means the run has none of that item.

#### 3.2.1 Model

A [Commission Model](./commission.md#33-model) without `id` or `credential`.

| Field | Type | Required | Description |
|---|---|---|---|
| `provider` | string | Yes | The service that runs the model. |
| `base_url` | string | No | The URL of the service's API. Absent means the service's default. |

#### 3.2.2 Tool

The [Tool](./agent-descriptor.md#32-tool) fields that ATIF's OpenAI-style tool definition can't hold. Absent fields mean the tool has none.

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | No | The tool's display name. |
| `outputSchema` | [JSON Schema](https://json-schema.org/draft/2020-12) | No | The shape of the tool's structured result. |
| `annotations` | map<string, any> | No | The tool's [MCP annotations](https://modelcontextprotocol.io/specification/latest/server/tools#tool). |
| `mcp_server_id` | string | No | The `id` of the MCP server in `mcp_servers` the tool comes from. Absent for any tool that does not come from an MCP server. |

### 3.3 Step

At `steps[].extra.avp`. The step's `model_name` is the model that produced the response; when absent, it is `agent.model_name`.

| Field | Type | Required | Description |
|---|---|---|---|
| `duration_ms` | integer | Yes, on agent steps | How long the model response took, in milliseconds, ending at the step's `timestamp`. 0 or more. |
| `finish_reasons` | string[] | No | On agent steps, why the model stopped, exactly as the service reported it, for example `"end_turn"` or `"length"`. |
| `message_metadata` | [Content metadata](#38-content-metadata)[] | No | On agent steps, data for parts of `message`. |
| `reasoning_metadata` | [Reasoning metadata](#39-reasoning-metadata)[] | No | On agent steps, data for blocks of the model's reasoning. |
| `error_code` | [Error code](#331-error-code) | Yes, on system steps that record an error | What kind of error. The step's `message` says what happened. |

#### 3.3.1 Error code

| Code | Meaning |
|---|---|
| `invalid_commission` | The agent refused the Commission, as the Commission spec's [rules for agents](./commission.md#51-the-agent-checks-the-commission-before-the-run-starts) require. The message says which rule. |
| `mcp_connect_failed` | An MCP server the Commission added didn't connect, so the run [didn't start](./commission.md#54-added-items-are-used-or-the-run-stops). The message names the server. |
| `auth_error` | The model service rejected the agent's credentials. |
| `rate_limit` | The model service refused a request because of a rate or usage limit. |
| `context_limit` | A request was longer than the model's context window. |
| `output_invalid` | The final output didn't match the Commission's `output_schema`. The output is in the trajectory's `extra.avp.output`. |
| `agent_crash` | The agent failed, or the model service failed. Also used when someone stops the run from outside before it starts. |
| `unknown` | Any other error. |

### 3.4 Tool call

At `steps[].tool_calls[].extra.avp`. A call's MCP server is in `agent.extra.avp.tools`, under the call's `function_name`.

| Field | Type | Required | Description |
|---|---|---|---|
| `server_side` | boolean | No | `true` when the model service ran the tool, for example web search, not the agent. |

### 3.5 Observation result

At `steps[].observation.results[].extra.avp`.

| Field | Type | Required | Description |
|---|---|---|---|
| `duration_ms` | integer | Yes, for tools the agent ran | How long the tool took, in milliseconds, ending at `finished_at`. 0 or more. |
| `finished_at` | string | Yes, for tools the agent ran | When the result arrived, as an [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339) timestamp. |
| `is_error` | boolean | No | `true` when the call failed. |
| `structured_content` | any | No | A result meant for programs, such as MCP's `structuredContent`, given beside `content`. For a tool the model service ran, a result that isn't text. |
| `content_metadata` | [Content metadata](#38-content-metadata)[] | No | Data for parts of `content`. |

### 3.6 Metrics

At `steps[].metrics.extra.avp`. A step's `metrics` are the usage of that one model response.

| Field | Type | Required | Description |
|---|---|---|---|
| `cache_creation_input_tokens` | integer | No | The input tokens written to the cache. Included in `prompt_tokens`. |
| `reasoning_output_tokens` | integer | No | The output tokens the model spent on reasoning. Included in `completion_tokens`. |
| `cost_source` | string | Yes, when `cost_usd` is present | Where `cost_usd` comes from: `reported` by the service or the agent's runtime, or `computed` from the token counts and [models.dev](https://models.dev) prices. |

### 3.7 Final metrics

At `final_metrics.extra.avp`, on the root trajectory and on each subagent trajectory. Totals count the trajectory and every subagent trajectory inside it, each once. `subagent_trajectory_ref` has no AVP fields.

| Field | Type | Required | Description |
|---|---|---|---|
| `total_cache_creation_input_tokens` | integer | No | The total of [`cache_creation_input_tokens`](#36-metrics). |
| `total_reasoning_output_tokens` | integer | No | The total of [`reasoning_output_tokens`](#36-metrics). |
| `total_responses` | integer | No | How many model responses were made. Differs from `total_steps`, which also counts system and user steps. |
| `cost_complete` | boolean | No | `false` when `total_cost_usd` leaves out responses whose cost is unknown, so the real cost is higher. Absent means the total is complete. |

### 3.8 Content metadata

ATIF content parts can't hold extra fields, so data for one part of a step's `message` or a result's `content` is kept beside it, in `steps[].extra.avp.message_metadata` or `observation.results[].extra.avp.content_metadata`. Each is a list with an entry for each part that has such data. Entries can hold fields the model service added, such as Gemini's `thought_signature`, so the agent can pass them back to the service.

| Field | Type | Required | Description |
|---|---|---|---|
| `part_index` | integer | Yes | The position of the part in `message` or `content`, from 0. `0` when the value is a string. |
| `citations` | [Citation](#381-citation)[] | No | Sources the model cited in the part. |
| `refusal` | boolean | No | `true` when the part is the model's text declining the task. |

ATIF keeps a response's text, reasoning, and tool calls in separate fields, so their order within one response is not recorded.

#### 3.8.1 Citation

A source the model cited. Can hold fields the service added, such as Anthropic's `document_index`.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Yes | The kind of citation, as the model service names it, such as `url_citation`. |
| `cited_text` | string | No | The text cited. |
| `start_index` | integer | No | Where the cited part of the text starts. 0 or more. |
| `end_index` | integer | No | Where it ends. 0 or more. |
| `source_id` | string | No | The service's ID for the source. |
| `source_url` | string | No | The source's URL. |
| `source_title` | string | No | The source's title. |

### 3.9 Reasoning metadata

At `steps[].extra.avp.reasoning_metadata`, a list with an entry for each block of the model's reasoning. ATIF's `reasoning_content` holds the readable text of all blocks. Entries can hold fields the model service added.

| Field | Type | Required | Description |
|---|---|---|---|
| `start` | integer | No | Where the block's text starts in `reasoning_content`. |
| `end` | integer | No | Where it ends. When `start` and `end` are absent, the block is all of `reasoning_content`. |
| `signature` | string | No | The service's token for passing the reasoning back to it. |
| `encrypted_content` | string | No | The service's encrypted reasoning, when it returned the block encrypted. It is not readable, so it is never copied into `reasoning_content`. |

## 4. Rules for agents

An agent conforms to this spec if every Trajectory it writes is valid ATIF v1.8, matches the [reference](#3-reference), and follows every MUST and MUST NOT in this section. The overview and the example add no requirements.

### 4.1 Rules for AVP extras

#### 4.1.1 Every error is a system step with an error code

The agent MUST record each error as a `system` step with an [`error_code`](#331-error-code). When the error ends the run, `stop_reason` MUST be `error`.

#### 4.1.2 A refused run has no model responses

When the agent [refuses the Commission](./commission.md#51-the-agent-checks-the-commission-before-the-run-starts), the Trajectory MUST have one `system` step with the error code, `stop_reason` `error`, no `started_at`, and no agent steps.

#### 4.1.3 The agent lists what the run can use

In [`agent.extra.avp`](#32-agent), the agent MUST list the built-in items the Commission doesn't turn off and the items the Commission adds. `mcp_servers` MUST list every server the agent tried to connect to.

#### 4.1.4 Cost says where it came from

When the model service or the runtime reports a response's cost, the agent MUST use it and set `cost_source` to `reported`. Otherwise, the agent MUST compute the cost from the [models.dev](https://models.dev) prices for the step's model and set `cost_source` to `computed`, or leave `cost_usd` out when models.dev doesn't list the model.

#### 4.1.5 A subagent still running at the end is abandoned

If the run ends while a subagent is running, the subagent's `stop_reason` MUST be `abandoned`, and the run's `stop_reason` MUST NOT be `converged`.

#### 4.1.6 Structured output keeps its type

When the run's result is not the last agent message as a string, the agent MUST put it in `extra.avp.output` with its JSON type.

### 4.2 Rules for ATIF fields

These rules narrow choices that ATIF leaves open.

#### 4.2.1 The prompts come first

The prompt MUST be the first `user` step. When the agent knows the system prompt, it MUST be the first step, as a `system` step without an `error_code`. An empty `message` means the Commission set an empty system prompt.

#### 4.2.2 One agent step per model response

The agent MUST record each model response as one `agent` step with `llm_call_count` `1`. The step holds the response's text, reasoning, and tool calls. An interrupted response keeps what arrived. The agent MUST NOT record responses its runtime does not show it.

#### 4.2.3 Usage is per response

A step's `metrics` MUST be that response's own usage, not a running total. Usage or cost the agent doesn't know MUST be left out, not set to zero. `final_metrics` MUST count each subagent trajectory once.

#### 4.2.4 Every tool call gets a result

Each tool call MUST have an observation result on the same step, with `source_call_id` set to the call's `tool_call_id`. A call still running when the run ends MUST get a result with `is_error` set to `true`.

#### 4.2.5 Each subagent has its own trajectory

Each subagent the run starts MUST have its own trajectory in `subagent_trajectories`, referenced by the result of the call that started it. That result MUST have `is_error` set to `true` exactly when the subagent's `stop_reason` isn't `converged`.

## 5. Rules for readers

A reader, such as a supervisor, conforms to this spec if it follows every MUST and MUST NOT in this section.

### 5.1 AVP Trajectories are checked, plain ATIF is accepted

A Trajectory with `extra.avp.avp_version` is an AVP Trajectory. A reader MAY reject an AVP Trajectory that is missing a required `extra` field. A reader MUST accept a Trajectory without `extra.avp` as plain ATIF.

### 5.2 Unknown values are read safely

A reader MUST accept keys it does not know in `extra` and `extra.avp`, and MUST treat an error code it does not know as `unknown`.

### 5.3 The result comes from `output`, then the last agent message

A reader MUST use `extra.avp.output` as the run's result when it is present, and the last root agent message otherwise.

## 6. Out of scope

- **Sending a Trajectory:** how it reaches the supervisor, for example as a file, over stdout, or over a network connection.
- **Progress during a run:** incremental events are planned for a later version.
- **The agent loop, credentials, and isolation:** ATIF describes a run; it does not run one.
- **Storing runs:** where Trajectories, images, and skill files are kept.
- **Resuming or replaying a run:** this depends on the runtime.
- **Data the runtime hides:** model context, token IDs, or probabilities the runtime never shows the agent.
