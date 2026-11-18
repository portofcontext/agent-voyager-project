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

Every field in an `extra.avp` object is optional unless its table says otherwise; an agent leaves a field out when it does not know the value. Readers MUST accept keys these tables do not list, and other keys beside `avp` in `extra`.

### 3.1 Trajectory

At the trajectory's top-level `extra.avp`, and on each embedded subagent trajectory.

| Field | Type | Required | Description |
|---|---|---|---|
| `avp_version` | string | Yes | The AVP version the Trajectory follows. `"0.1"` for this spec. |
| `commission` | [Commission](./commission.md#31-commission), or any | Yes, when the run has a Commission | The Commission exactly as the agent received it, including one it then refuses. When what it received doesn't match the Commission spec, the JSON value it received, or the text when it isn't JSON. Absent when the run has no Commission. |
| `started_at` | string | Yes, unless the run was [refused](#45-a-refused-run-has-no-model-responses) | When the run started, as an [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339) timestamp. It can be earlier than the first step, since the agent can do work before it records one. |
| `stopped_at` | string | Yes | When the run stopped, as an RFC 3339 timestamp. |
| `stop_reason` | [Stop reason](#38-stop-reason) | Yes | Why the run stopped. |
| `output` | any | No | The run's result, when it differs from the last agent message or has a different JSON type, for example structured output. `null` means the run returned no result. Absent means the result is the last agent message. |

### 3.2 Agent

At `agent.extra.avp`. An embedded subagent trajectory has its own. The values are what the run used: the agent's [Descriptor](./agent-descriptor.md) combined with the [Commission](./commission.md), which [limits the built-in items](./commission.md#52-agent-settings-limit-the-built-in-items), [adds its own](./commission.md#54-added-items-are-used-or-the-run-stops), and [replaces the system prompt](./commission.md#55-system_prompt-replaces-the-agents-own). The prompt, system prompt, model ID, and each tool's name, description, and input schema are in standard ATIF fields, so they are not repeated here.

| Field | Type | Required | Description |
|---|---|---|---|
| `descriptor` | [Agent Descriptor](./agent-descriptor.md#31-descriptor) | Yes, on the root trajectory | The agent's Descriptor, unchanged. Absent on subagent trajectories. |
| `model` | [Model](#321-model) | Yes, unless the run was [refused](#45-a-refused-run-has-no-model-responses) | The service that runs the model in `agent.model_name`. |
| `tools` | map<string, [Tool](#322-tool)> | No | For each tool in `agent.tool_definitions`, keyed by its name, the fields ATIF's tool definition can't hold. |
| `mcp_servers` | [MCP server](./agent-descriptor.md#33-mcp-server)[] | No | The MCP servers the run used, with their `status`. |
| `skills` | [Skill](./agent-descriptor.md#34-skill)[] | No | The skills the run used. `source` points to the saved skill directory beside the Trajectory. |
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
| `error_code` | [Error code](#39-error-code) | Yes, on system steps that record an error | What kind of error. The step's `message` says what happened. |

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

### 3.6 Metrics

TBD.

### 3.7 Final metrics and subagent references

TBD.

### 3.8 Stop reason

TBD.

### 3.9 Error code

TBD.

### 3.10 Content metadata

TBD.

### 3.11 Reasoning metadata

TBD.

## 4. Rules for agents

These rules apply to the agent that writes a Trajectory. An agent conforms to this spec if every Trajectory it writes is valid ATIF v1.8, matches the [reference](#3-reference), and follows every MUST and MUST NOT in this section. The overview and the example add no requirements.

### 4.1 The agent writes one Trajectory when the run ends

The agent MUST write exactly one Trajectory per run, once, when the run ends: when it stops for any [stop reason](#38-stop-reason), or when a fatal error ends it. The Trajectory MUST be valid ATIF v1.8. The agent MUST NOT write partial Trajectories while the run is going.

With `--out <path>`, the agent writes the Trajectory to that path. With `--out -`, it writes it to standard output. Diagnostics go to standard error. A process killed before it can write leaves no Trajectory.

Image content uses ATIF references to files beside the Trajectory. The agent writes each image file before the Trajectory, and writes identical images once. `--out -` cannot carry images, so a run with images needs a file path.

### 4.2 Errors that don't end the run are steps

The agent MUST record each error as a system step with an `error_code`. An error that does not end the run, for example a failed retry, is recorded and the run goes on. When an error ends the run, the agent writes the Trajectory with `stop_reason` set to `error`.

### 4.3 The run's inputs are recorded

The [agent](#32-agent) MUST list what the run can use: the built-in items the Commission doesn't turn off, plus the items it adds. `mcp_servers` lists every server the agent tried to connect to, following the Descriptor's [rules for MCP servers](./agent-descriptor.md#44-tools-from-mcp-servers). The prompt MUST be the first `user` step.

When the agent knows the system prompt, it MUST be the first step: a `system` step without an `error_code`. An empty `message` means the Commission set an empty system prompt. Every `system` step that records an error MUST have an `error_code`.

The Trajectory MUST NOT contain a secret value from the Commission.

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
