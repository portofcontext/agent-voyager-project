# Trajectory Spec

**Status:** Draft

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are interpreted as
[BCP 14](https://www.rfc-editor.org/rfc/rfc8174) when capitalized.

## 1. Overview

AVP v0.1 trajectories use **ATIF v1.8**. ATIF is the
[Agent Trajectory Interchange Format](https://harborframework.com/docs/agents/atif).
Its standard fields describe the conversation, model responses, tools,
observations, subagents, and metrics. AVP uses these fields directly.

AVP uses the ATIF models from Harbor commit
[`9c7a39b`](https://github.com/harbor-framework/harbor/tree/9c7a39b991d7e2205019f6be0598cbd22d84bfc3/src/harbor/models/trajectories).
The Python SDK includes a copy of these models and their license. They generate
the [JSON Schema](trajectory.schema.json), which also defines the TypeScript types.

AVP adds run outcomes and execution details in ATIF's `extra.avp` fields.
ATIF readers can read the conversation without understanding these additions.
[Agent Start](agent-start.md) records the resolved configuration and paths to
saved skill files. The trajectory records what happened during the run.

## 2. Examples

This example shows AVP's completion fields. ATIF reserves `extra` for additions;
AVP groups its fields under `avp`. Expand the dropdown for the full list.

```json
{
  "extra": {
    "avp": {
      "complete": true,
      "stop_reason": "converged",
      "output": {"answer": 42}
    }
  }
}
```

<details>
<summary>All AVP extras, grouped by where they appear in ATIF</summary>

This list shows each AVP field with an example value. It isn't a complete
trajectory. Each label names the ATIF object where the fields appear inside
`extra.avp`. A run includes only the fields that apply. Child trajectories can
also use the trajectory fields shown first.

```json
{
  "trajectory.extra.avp": {
    "complete": true,
    "started_at": "2026-01-01T00:00:00Z",
    "stopped_at": "2026-01-01T00:00:02Z",
    "stop_reason": "converged",
    "output": {
      "answer": 42
    },
    "annotations": {
      "runtime_session_id": "session-1"
    }
  },
  "agent.extra.avp": {
    "provider": "openai",
    "base_url": "https://api.openai.com/v1",
    "requested_model": "example-model"
  },
  "steps[source=agent].extra.avp": {
    "duration_ms": 800,
    "provider": "anthropic",
    "base_url": "https://proxy.example/v1",
    "requested_model": "alternate-model",
    "finish_reasons": [
      "end_turn"
    ],
    "annotations": {
      "response_id": "response-1"
    },
    "message_metadata": [
      {
        "part_index": 0,
        "annotations": {
          "citations": [
            {
              "type": "url_citation",
              "source_url": "https://example.com"
            }
          ]
        }
      }
    ],
    "reasoning_metadata": [
      {
        "signature": "provider-signature",
        "redacted": false,
        "start": 0,
        "end": 12
      },
      {
        "redacted": true,
        "encrypted_content": "encrypted-reasoning"
      }
    ]
  },
  "steps[source=system].extra.avp": {
    "error_code": "auth_error"
  },
  "steps[].tool_calls[].extra.avp": {
    "server_side": true,
    "provider_metadata": {
      "provider_call_id": "distinct-provider-id"
    },
    "observed_at": "2026-01-01T00:00:01Z"
  },
  "steps[].observation.results[].extra.avp": {
    "finished_at": "2026-01-01T00:00:01.200Z",
    "is_error": false,
    "structured_content": {
      "answer": 42
    },
    "provider_metadata": {
      "provider_result_id": "native-result-1"
    },
    "content_metadata": [
      {
        "part_index": 0,
        "annotations": {
          "citations": [
            {
              "type": "url_citation",
              "source_url": "https://example.com"
            }
          ]
        }
      }
    ]
  },
  "steps[].metrics.extra.avp": {
    "cache_creation_input_tokens": 20,
    "reasoning_output_tokens": 12,
    "cost_source": "reported"
  }
}
```

- The first response establishes `agent.model_name` and the agent's provider,
  endpoint, and requested-model defaults. Steps only record differences from
  those defaults. `requested_model` is omitted on the agent when it matches
  `agent.model_name`. Each child has independent defaults.
- To read a response, use its `model_name` or `agent.model_name`. For provider
  and endpoint, use a step override or the agent default. A step's `base_url: null` explicitly clears an inherited endpoint. For the requested model, use
  a step override, then `agent.extra.avp.requested_model`, then `agent.model_name`.
- MCP ownership lives in the tool catalog in `agent-start.json`.
  Match recorded calls to that catalog by `function_name`; the trace does not
  repeat `mcp_server_id` on definitions or calls.
- `observed_at` records when the Recorder receives a runtime-executed tool call.
  It is not a guaranteed execution-start time. The interval to the result's
  `finished_at` includes any dispatch, queueing, and reporting delays.
  `server_side` is present only for provider-executed tools; these calls do not
  receive an SDK-observed start timestamp.
- `output` is present only when the returned value differs from the last root
  agent message or has a different JSON type. When absent on a complete run,
  use that message. An explicit `output: null` means no returned result, even
  if the trace contains agent messages. Incomplete AVP runs have no inferred
  result.
- `annotations` and `provider_metadata` are open objects. Their sample keys
  above illustrate runtime/provider data, not a fixed AVP field list.
- Tool definitions use standard ATIF fields only. The full catalog, including
  `title`, `outputSchema`, MCP `annotations`, and server ownership, lives in
  `agent-start.json`.
- Use ATIF's `tool_call_id` to identify a call. The Recorder omits
  `provider_call_id`, `call_id`, and `tool_call_id` from `provider_metadata`
  when they repeat that ID. It keeps a different provider ID when supplied.
- `message_metadata` and `content_metadata` entries contain `part_index` and
  `annotations`. Those annotations preserve citations, refusal flags, image
  source metadata, and other provider content fields.
- `reasoning_metadata` preserves `signature`, `redacted`, and other provider
  fields. `start`/`end` locate public reasoning text; `encrypted_content` holds
  redacted reasoning instead of exposing it as public text.
- Complete usage totals use standard ATIF `final_metrics`. Unknown totals stay
  absent. Readers can add step metrics and child totals, counting each child
  once. There is no extra field for partial totals.
- When a child reports totals without individual responses, the Recorder saves
  those totals in standard ATIF metrics. Per-response `cost_source` is
  `computed`, `reported`, or `unknown`.

</details>

## 3. Reference

ATIF defines the document and its fields. This table explains how AVP uses them.

| ATIF field | AVP use |
|---|---|
| `schema_version` | `ATIF-v1.8` |
| `session_id` | The Commission's `run_id`, or a generated run ID |
| `agent` | Effective agent identity, model, and tool definitions |
| `steps` | Sequential system, user, and agent steps |
| `message` | Visible text or ATIF content parts |
| `reasoning_content` | Public reasoning text, when the runtime exposes it |
| `tool_calls` | Calls requested by this model response |
| `observation.results` | Results linked to calls by `source_call_id` |
| `metrics` | Usage and cost for this response |
| `subagent_trajectories` | Embedded child trajectories with stable `trajectory_id` values |
| `subagent_trajectory_ref` | References from a delegation observation to its child trajectories |
| `final_metrics` | Totals for the document and its descendants, counted once |

### 3.1 AVP fields

AVP fields go under `extra.avp` on the ATIF object they describe. Omit optional
fields when their values are unknown. Agents MUST use a standard ATIF field
when one exists for the information. Other execution details go in `extra.avp`;
readers don't need separate files to find them. Extensions MUST NOT duplicate
the original event stream.

The [All AVP extras dropdown](#2-examples) lists the complete SDK-defined
fields, including metadata objects that accept provider-specific keys.

Stop reasons are `converged`, `refused`, `error`, `interrupted`, and `abandoned`.
The SDK's reporting API defines supported error codes. A refusal is represented
by a system step with an error code and a complete document with reason `error`.
It has no start time or model-response steps.

Encrypted reasoning, signatures, citations, refusal annotations, and provider
metadata remain in the relevant ATIF object's `extra.avp`. Encrypted reasoning
is not shown as readable reasoning. Agent Start records the resolved
configuration and paths to saved skills. Execution details stay in the trace.

### 3.2 Document delivery

The agent command's `--out <path>` writes a complete JSON snapshot to that path
and atomically replaces it as the run advances. The supervisor CLI uses
`trajectory.json` in the run directory. A reader can reopen the file to follow
new responses and observations on existing steps. Pending calls are valid;
their observations appear when results arrive.

Image content uses ATIF references to files beside the document. The sink writes
image files before saving the snapshot and reuses a file for identical images.
Keep referenced image files beside the trajectory when moving a run. Keep
`commission.json`, `descriptor.json`, `agent-start.json`, and its referenced
skill directories to retain the run inputs.

`--out -` writes one completed JSON document to stdout. It does not stream
snapshots or the other run documents. Use file output to retain the complete run record;
runs with images require it. Diagnostics use
stderr. A hard-killed process may leave the latest incomplete file snapshot.

## 4. Rules for agents

### 4.1 Produce valid ATIF

Agents MUST produce ATIF-v1.8 with sequential step IDs and valid call and child
references. A completed run MUST set `extra.avp.complete` to true. Partial file
snapshots MUST also be valid ATIF documents.

### 4.2 Record effective inputs

Agents MUST record the effective model and tool definitions, user prompt, and
system prompt when available. Credentials MUST NOT be included. A preflight
refusal MUST be recorded without claiming that the run started.

### 4.3 One agent step per model response

Agents MUST record each exposed model response once, with `source: "agent"`
and `llm_call_count: 1`. Text, public reasoning, and tool calls belong to that
step. Streamed chunks are assembled into a response; they are not separate
steps. Interrupted partial responses retain the content already received.

### 4.4 Usage is per response

Response metrics MUST be deltas, never cumulative runtime totals. Cached input
is included in prompt tokens; reasoning output is included in completion tokens.
Missing usage or cost MUST remain unknown rather than being invented as zero.
Document totals MUST count each child, including nested children, once. A child's
reported total MAY be used when its individual responses are unavailable. That
total MUST NOT be added again when those responses have already been counted.

### 4.5 Match tool results

Every completed call MUST have an observation on the step containing its call,
matched by call ID. Parallel completion order MUST NOT change that association.
A call abandoned at run termination MUST receive an error observation.

### 4.6 Subagents

A child MUST have its own trajectory and stable reference from the parent's
delegation observation. The child records its own model responses and tools.
Nested children follow the same rule. Record only the child activity the runtime
reports; agents MUST NOT invent responses they cannot observe.

### 4.7 Errors and stops

Agents MUST record execution errors and the reason the run stopped. Structured output
MUST retain its JSON type in `extra.avp.output`. SIGINT and SIGTERM SHOULD close
pending work and save a completed document with stop reason `interrupted`. Readers MUST tolerate
incomplete snapshots from processes that cannot finish.

## 5. Rules for readers

Readers MUST accept standard ATIF without AVP extensions and MUST tolerate
unknown extension fields. Generic output can be read from the last root agent
message; a typed AVP output, when present, takes precedence. Absence of an AVP
stop reason does not invalidate an external ATIF document.

## 6. Out of scope

ATIF does not supply an agent loop, transport, credentials, isolation, or
storage service. Resuming or replaying a session depends on the runtime. Neither the format nor the Recorder can recover hidden model
context, token IDs, or probabilities that the runtime never exposes.
