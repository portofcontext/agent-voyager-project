# Trajectory Spec

**Status:** Draft

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they appear in all capitals, as shown here.

## 1. Overview

A Trajectory is a JSON document that answers one question: **what happened in this run?** It records the prompts, each model response, the tool calls and their results, the subagents the run started, token usage and cost, and why the run stopped.

A Trajectory is an [ATIF v1.8](https://github.com/harbor-framework/harbor/blob/9c7a39b991d7e2205019f6be0598cbd22d84bfc3/rfcs/0001-trajectory-format.md) (Agent Trajectory Interchange Format) document, with a [JSON Schema](trajectory.schema.json). AVP uses ATIF's standard fields as ATIF defines them, and puts its additions in ATIF's `extra` objects under `avp`, so any ATIF reader can read the conversation.

This spec defines the `extra.avp` fields, the rules an agent follows when it writes a Trajectory, and the rules a reader follows. [Out of scope](#6-out-of-scope) lists what it leaves to implementations.

A Trajectory records what one run did, not what the [Commission](./commission.md) asked for or the [Agent Descriptor](./agent-descriptor.md) offered. [Agent Start](agent-start.md) records the resolved configuration used by the run.

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
            "properties": { "path": { "type": "string" } },
            "required": ["path"]
          }
        }
      }
    ],
    "extra": { "avp": { "provider": "anthropic" } }
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
          "arguments": { "path": "src/login.py" },
          "extra": { "avp": { "observed_at": "2026-01-01T00:00:01.100Z" } }
        }
      ],
      "observation": {
        "results": [
          {
            "source_call_id": "call-1",
            "content": "def login(): ...",
            "extra": { "avp": { "finished_at": "2026-01-01T00:00:01.200Z" } }
          }
        ]
      },
      "metrics": {
        "prompt_tokens": 1200,
        "completion_tokens": 40,
        "cost_usd": 0.0042,
        "extra": { "avp": { "cost_source": "computed" } }
      },
      "llm_call_count": 1,
      "extra": { "avp": { "duration_ms": 800, "finish_reasons": ["tool_use"] } }
    },
    {
      "step_id": 3,
      "timestamp": "2026-01-01T00:00:02Z",
      "source": "agent",
      "model_name": "claude-sonnet-4-6",
      "message": "Fixed: the timeout now reads from settings.",
      "metrics": { "prompt_tokens": 1300, "completion_tokens": 12 },
      "llm_call_count": 1,
      "extra": { "avp": { "duration_ms": 500, "finish_reasons": ["end_turn"] } }
    }
  ],
  "final_metrics": {
    "total_prompt_tokens": 2500,
    "total_completion_tokens": 52,
    "total_steps": 3
  },
  "extra": {
    "avp": {
      "complete": true,
      "started_at": "2026-01-01T00:00:00Z",
      "stopped_at": "2026-01-01T00:00:02Z",
      "stop_reason": "converged"
    }
  }
}
```

The run's `session_id` is the Commission's `run_id`. The trajectory's `extra.avp` has no `output`, so the run's result is the last agent message. The second response has no `cost_usd`, so its cost is unknown, and `final_metrics` leaves the total cost out.

## 3. Reference

The [ATIF RFC](https://github.com/harbor-framework/harbor/blob/9c7a39b991d7e2205019f6be0598cbd22d84bfc3/rfcs/0001-trajectory-format.md) define every standard field. This section defines only the `extra.avp` objects AVP adds. Each one sits at `extra.avp` on the ATIF object its section names.

Every field in an `extra.avp` object is optional unless its table says otherwise; an agent leaves a field out when it does not know the value. Readers MUST accept keys these tables do not list, and other keys beside `avp` in `extra`.

### 3.1 Trajectory

At the trajectory's top-level `extra.avp`, and on each embedded subagent trajectory.

| Field | Type | Required | Description |
|---|---|---|---|
| `complete` | boolean | Yes | `true` when the agent finished writing the Trajectory. |
| `started_at` | string | No | When the run started, as an ISO 8601 timestamp. Absent when the agent [refused](#45-a-refused-run-has-no-model-responses) the Commission. |
| `stopped_at` | string | No | When the run stopped, as an ISO 8601 timestamp. |
| `stop_reason` | [Stop reason](#38-stop-reason) | Yes | Why the run stopped. |
| `output` | any | No | The run's result, when it differs from the last agent message or has a different JSON type, for example structured output. `null` means the run returned no result. Absent means the result is the last agent message. |
| `annotations` | map<string, any> | No | Runtime data with no standard field, for example the runtime's own session ID. |

### 3.2 Agent

At `agent.extra.avp`. These are the defaults for every agent step in the same trajectory. An embedded subagent trajectory has its own.

| Field | Type | Required | Description |
|---|---|---|---|
| `provider` | string | No | The service that ran the model, as in the Commission's [Model](./commission.md#33-model). |
| `base_url` | string | No | The URL of the service's API. |
| `requested_model` | string | No | The model ID the agent asked for, when it differs from `agent.model_name`, the model that answered. |

### 3.3 Step

At `steps[].extra.avp`. Agent steps use every field but `error_code`; system steps use only `error_code`.

| Field | Type | Required | Description |
|---|---|---|---|
| `duration_ms` | integer | No | How long the model response took, in milliseconds. |
| `provider` | string | No | As in [Agent](#32-agent), when this response's value differs. |
| `base_url` | string \| null | No | As in [Agent](#32-agent), when this response's value differs. `null` means this response used the service's default URL. |
| `requested_model` | string | No | As in [Agent](#32-agent), when this response's value differs. |
| `finish_reasons` | string[] | No | Why the model stopped generating, as the service reports it, for example `"end_turn"`. |
| `annotations` | map<string, any> | No | Response data with no standard field, for example the service's response ID. |
| `message_metadata` | [Content metadata](#310-content-metadata)[] | No | Data for parts of `message` that ATIF content parts cannot hold. |
| `reasoning_metadata` | [Reasoning metadata](#311-reasoning-metadata)[] | No | Data for the response's reasoning. |
| `error_code` | [Error code](#39-error-code) | No | On a system step that records an error, what kind of error. The step's `message` says what happened. |

To find a response's provider, URL, or requested model, a reader uses the step's value when it is present, then the agent's. For the requested model, it then uses `agent.model_name`.

### 3.4 Tool call

At `steps[].tool_calls[].extra.avp`.

| Field | Type | Required | Description |
|---|---|---|---|
| `observed_at` | string | No | When the agent saw the call, as an ISO 8601 timestamp. Not always when the tool started: the time to `finished_at` can include dispatch and queueing. Absent when `server_side` is `true`. |
| `server_side` | boolean | No | `true` when the model service ran the tool, not the agent. |
| `provider_metadata` | map<string, any> | No | Call data from the service with no standard field, for example the service's own call ID when it differs from `tool_call_id`. |

### 3.5 Observation result

At `steps[].observation.results[].extra.avp`.

| Field | Type | Required | Description |
|---|---|---|---|
| `finished_at` | string | No | When the result arrived, as an ISO 8601 timestamp. |
| `is_error` | boolean | No | `true` when the call failed. |
| `structured_content` | map<string, any> | No | A result meant for programs, such as MCP's `structuredContent`, given beside `content`. |
| `provider_metadata` | map<string, any> | No | Result data from the service with no standard field. |
| `content_metadata` | [Content metadata](#310-content-metadata)[] | No | Data for parts of `content` that ATIF content parts cannot hold. |

### 3.6 Metrics

At `steps[].metrics.extra.avp`.

| Field | Type | Required | Description |
|---|---|---|---|
| `cache_creation_input_tokens` | integer | No | Input tokens written to the service's prompt cache. |
| `reasoning_output_tokens` | integer | No | Output tokens spent on reasoning. They are also counted in `completion_tokens`. |
| `cost_source` | string | No | Where `cost_usd` comes from: `computed` from token prices, `reported` by the service, or `unknown`. |

### 3.7 Final metrics and subagent references

`final_metrics.extra.avp` and `subagent_trajectory_ref[].extra.avp` have no AVP fields in this version.

### 3.8 Stop reason

| Value | Meaning |
|---|---|
| `converged` | The model gave its final answer. |
| `refused` | The model declined the task. |
| `error` | The run failed. A system step with an `error_code` says why. |
| `interrupted` | Someone stopped the run from outside, for example with SIGINT or SIGTERM. |
| `abandoned` | The run ended while a subagent it started was still running, so the run has no complete answer. On a subagent trajectory: the run ended while the subagent was still running. |

### 3.9 Error code

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

### 3.10 Content metadata

Data for one part of a message or result.

| Field | Type | Required | Description |
|---|---|---|---|
| `part_index` | integer | Yes | The index of the part in `message` or `content`. `0` when the value is a string. |
| `annotations` | map<string, any> | Yes | The part's data with no standard field, for example citations, refusal flags, or image source details. |

### 3.11 Reasoning metadata

Data for one block of the model's reasoning. Extra keys from the service are kept.

| Field | Type | Required | Description |
|---|---|---|---|
| `signature` | string | No | The service's token for passing the reasoning back to it. |
| `redacted` | boolean | No | `true` when the service returned the reasoning encrypted. |
| `start` | integer | No | Where the block starts in the step's `reasoning_content`. |
| `end` | integer | No | Where the block ends in the step's `reasoning_content`. |
| `encrypted_content` | string | No | The encrypted reasoning, when `redacted` is `true`. It is not copied into `reasoning_content`. |

## 4. Rules for agents

These rules apply to the agent that writes a Trajectory. An agent conforms to this spec if every Trajectory it writes is valid ATIF v1.8, matches the [reference](#3-reference), and follows every MUST and MUST NOT in this section. The overview and the example add no requirements.

### 4.1 The agent writes one Trajectory when the run ends

The agent MUST write exactly one Trajectory per run, once, when the run ends: when it stops for any [stop reason](#38-stop-reason), or when a fatal error ends it. The Trajectory MUST be valid ATIF v1.8 with `extra.avp.complete` set to `true`. The agent MUST NOT write partial Trajectories while the run is going.

With `--out <path>`, the agent writes the Trajectory to that path. With `--out -`, it writes it to standard output. Diagnostics go to standard error. A process killed before it can write leaves no Trajectory.

Image content uses ATIF references to files beside the Trajectory. The agent writes each image file before the Trajectory, and writes identical images once. `--out -` cannot carry images, so a run with images needs a file path.

### 4.2 Errors that don't end the run are steps

The agent MUST record each error as a system step with an `error_code`. An error that does not end the run, for example a failed retry, is recorded and the run goes on. When an error ends the run, the agent writes the Trajectory with `stop_reason` set to `error`.

### 4.3 Inputs are recorded in standard fields

The agent MUST record the model in `agent.model_name`, the tools the model sees in `agent.tool_definitions`, the prompt as the first `user` step, and the system prompt, when it knows it, as a `system` step. The Trajectory MUST NOT contain a secret value from the Commission.

### 4.4 One agent step per model response

The agent MUST record each model response it sees as one step with `source` `"agent"` and `llm_call_count` `1`. The response's text, reasoning, and tool calls go on that step. Streamed chunks are joined into one response. An interrupted response keeps the content received so far.

### 4.5 A refused run has no model responses

When the agent [refuses the Commission](./commission.md#51-the-agent-checks-the-commission-before-the-run-starts), the Trajectory has one system step with the `error_code`, `stop_reason` `error`, and no `started_at` or agent steps.

### 4.6 Usage is per response

Each step's `metrics` MUST be that response's own usage, never a running total. Cached input counts in `prompt_tokens`, and reasoning output counts in `completion_tokens`. Usage or cost the agent does not know MUST be left out, not set to zero.

`final_metrics` MUST count every subagent trajectory, including nested ones, once. When a subagent reports only its total, the agent MAY record that total in the subagent's metrics, and MUST NOT also count the subagent's responses.

### 4.7 Every tool call gets a result

Each tool call's result MUST be an observation result on the step that holds the call, with `source_call_id` set to the call's `tool_call_id`, whatever order parallel calls finish in. A call still running when the run ends MUST get a result with `is_error` set to `true`.

### 4.8 Subagents have their own trajectories

Each subagent the run starts MUST have its own trajectory in `subagent_trajectories`, with a stable `trajectory_id`, and the observation of the call that started it MUST reference it in `subagent_trajectory_ref`. The subagent's trajectory records its own responses and tool calls. Nested subagents follow the same rule. The agent MUST NOT invent responses its runtime does not show it.

If the run ends while a subagent is still running, that subagent's trajectory gets `stop_reason` `abandoned`, and the run's `stop_reason` MUST NOT be `converged`.

### 4.9 Interrupted runs still write a Trajectory

On SIGINT or SIGTERM, the agent SHOULD stop its runtime, close running tool calls and subagents, and write the Trajectory with `stop_reason` `interrupted`.

### 4.10 Structured output keeps its type

When the run's result is not the last agent message as a string, for example a JSON object from an output schema, the agent MUST put it in `extra.avp.output` with its JSON type.

## 5. Rules for readers

These rules apply to a program that reads a Trajectory, such as a supervisor. A reader conforms to this spec if it follows every MUST and MUST NOT in this section.

### 5.1 Plain ATIF is accepted

A reader MUST accept ATIF documents without `extra.avp`. A missing `stop_reason` does not make an ATIF document invalid.

### 5.2 Unknown values are read safely

A reader MUST accept keys it does not know in `extra` and `extra.avp`, and MUST treat an error code it does not know as `unknown`.

### 5.3 The result comes from `output`, then the last agent message

A reader MUST use `extra.avp.output` as the run's result when it is present, and the last root agent message otherwise.

## 6. Out of scope

- **Progress during a run:** the agent writes the Trajectory once, at the end. Incremental events are planned for a later version.
- **The agent loop, transport, credentials, and isolation:** ATIF describes a run; it does not run one.
- **Storing and moving runs:** where Trajectories and their image files are kept.
- **Resuming or replaying a run:** this depends on the runtime.
- **Data the runtime hides:** model context, token IDs, or probabilities the runtime never shows the agent.
