# Trajectory Spec

**Status:** Draft

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are interpreted as
[BCP 14](https://www.rfc-editor.org/rfc/rfc8174) when capitalized.

## 1. Overview

An AVP run produces an **ATIF-v1.8** document. ATIF is the
[Agent Trajectory Interchange Format](https://harborframework.com/docs/agents/atif).
Its standard fields describe the conversation, model responses, tools,
observations, subagents, and metrics. AVP uses these fields directly.

The normative upstream model revision is
[`9c7a39b`](https://github.com/harbor-framework/harbor/tree/9c7a39b991d7e2205019f6be0598cbd22d84bfc3/src/harbor/models/trajectories).
The [JSON Schema](trajectory.schema.json) is generated from those models.
The Python SDK vendors the upstream models with their license; the TypeScript
SDK generates its wire types from the same schema.

AVP adds operational details in ATIF's `extra.avp` extension fields. A generic
ATIF consumer can read the conversation without understanding these extensions.
Full configuration, skill files, and provider details live in [run artifacts](artifacts.md).
The trace stays focused on what happened during execution; artifacts retain
the material needed for evaluation and improvement.

## 2. Example

```json
{
  "schema_version": "ATIF-v1.8",
  "session_id": "example-run",
  "agent": {"name": "example-agent", "version": "1.0", "model_name": "example-model"},
  "steps": [
    {"step_id": 1, "source": "user", "message": "What is 20 + 22?"},
    {
      "step_id": 2, "source": "agent", "message": "", "llm_call_count": 1,
      "tool_calls": [{"tool_call_id": "c1", "function_name": "add", "arguments": {"a": 20, "b": 22}}],
      "observation": {"results": [{"source_call_id": "c1", "content": "42"}]},
      "metrics": {"prompt_tokens": 30, "completion_tokens": 12}
    },
    {"step_id": 3, "source": "agent", "message": "42", "llm_call_count": 1,
     "metrics": {"prompt_tokens": 45, "completion_tokens": 2}}
  ],
  "final_metrics": {"total_prompt_tokens": 75, "total_completion_tokens": 14},
  "extra": {"avp": {"complete": true, "stop_reason": "converged", "output": "42"}}
}
```

## 3. Reference

ATIF owns the document and field definitions. This table describes AVP's use of
them; it does not introduce another trajectory schema.

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

### 3.1 Operational extensions

Extensions live under `extra.avp` on the relevant ATIF object. Optional fields
are omitted when unknown. They MUST NOT duplicate the original event stream.

| Object | Fields and meaning |
|---|---|
| Trajectory | `complete`, `started_at`, `stopped_at`, `stop_reason`, typed JSON `output` |
| Agent | Effective `provider`; full configuration is an input artifact |
| Agent step | `duration_ms`, requested model when different, `finish_reasons`, `details_path` when response details were captured |
| System step | `error_code`, with the error description in standard `message` |
| Tool call | `started_at`, `mcp_server_id`, `details_path` when needed |
| Observation result | `ended_at`, `duration_ms`, `is_error`, `structured_content`, `details_path` when needed |
| Metrics | `cache_creation_input_tokens`, `reasoning_output_tokens`, `cost_source` |
| Final metrics | Known partial totals and unknown-field indicators when complete totals cannot be established |
| Opaque child trajectory | `usage_details` for aggregate usage the runtime exposes without individual responses |

Stop reasons are `converged`, `refused`, `error`, `interrupted`, and `abandoned`.
The SDK's reporting API defines supported error codes. A refusal is represented
by a system step with an error code and a complete document with reason `error`.
It has no start time or model-response steps.

Encrypted reasoning, signatures, citations, refusal annotations, and other
bulky provider data are output artifacts. `extra.avp.details_path` on the
applicable object points to a relative JSON file listed in `artifacts.json`.
Readers resolve it from the run directory and verify its manifest hash.
Encrypted reasoning is not presented as public reasoning text.

### 3.2 Document delivery

The agent command's `--out <path>` writes a complete JSON snapshot to that path
and atomically replaces it as the run advances. The supervisor CLI uses
`trajectory.json` in the run directory. A reader can reopen the file to follow
new responses and observations on existing steps. Pending calls are valid;
their observations appear when results arrive.

Image content uses ATIF references to files beside the document. The sink writes
assets before publishing the snapshot and deduplicates identical content.
Moving a complete run requires moving its manifest and every listed artifact,
including images, alongside the trajectory.

`--out -` writes one completed JSON document to stdout. It does not stream
snapshots or artifact files. Use file output to retain the complete run record;
runs with binary assets require it. Diagnostics use
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
Document totals MUST include descendants once. An opaque child's aggregate MAY
be included when individual child responses are unavailable; it MUST NOT also
be counted when those responses have been recorded.

### 4.5 Match tool results

Every completed call MUST have an observation on the step containing its call,
matched by call ID. Parallel completion order MUST NOT change that association.
A call abandoned at run termination MUST receive an error observation.

### 4.6 Subagents

A child MUST have its own trajectory and stable reference from the parent's
delegation observation. The child records its own model responses and tools.
Nested children follow the same rule. An opaque child records only the details
the runtime exposes; agents MUST NOT invent hidden responses.

### 4.7 Errors and stops

Agents MUST retain operational errors and a terminal reason. Structured output
MUST retain its JSON type in `extra.avp.output`. SIGINT and SIGTERM SHOULD close
pending work and publish a terminal interrupted document. Readers MUST tolerate
incomplete snapshots from processes that cannot finish.

## 5. Rules for readers

Readers MUST accept standard ATIF without AVP extensions and MUST tolerate
unknown extension fields. Generic output can be read from the last root agent
message; a typed AVP output, when present, takes precedence. Absence of an AVP
stop reason does not invalidate an external ATIF document.

## 6. Out of scope

ATIF does not supply an agent loop, transport, credentials, isolation, or
persistence service. Provider-specific session resumption and replay depend on
runtime support. Neither the format nor the Recorder can recover hidden model
context, token IDs, or probabilities that the runtime never exposes.
