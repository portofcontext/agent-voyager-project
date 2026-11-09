# ATIF export

The Python supervisor utility `avp.utils.atif` exports a run to
[ATIF](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md),
Harbor's trajectory interchange format. ATIF-v1.8 is the target trajectory
format. This utility is the current migration entry point for runs emitted by
existing adapters. The SDK has no Harbor runtime dependency.

## Export a run

From the repository root:

```sh
uv run --project avp-sdk/python python -m avp.utils.atif \
  path/to/trajectory.ndjson --out export/trajectory.json
```

The command writes `trajectory.json` and any referenced images in `export/images/`.
It also accepts incomplete runs once an `agent_described` event is present.
Inspect `extra.avp.complete` and
`extra.avp.stop_reason` before using a run as a successful training example.
Invalid events, unknown event types, mixed run IDs, and unmatched tool results
fail the export instead of silently dropping data. This utility assumes AVP's
event ordering rules; it does not replace the conformance checker.

In Python, `to_atif(events)` returns an `AtifExport`. Its `trajectory` is a JSON
dictionary, and `assets` maps relative image paths to bytes. `write(Path(...))`
writes both. Calling `to_atif` alone performs no file or network IO.

## Mapping

| AVP | ATIF |
|---|---|
| `run_id` | `session_id`; separate deterministic document IDs identify subagents |
| `agent_described` | Root agent name and version |
| `agent_started` | Actual model, tool definitions, and initial system/user steps |
| `assistant_message` | One agent step with `llm_call_count: 1`, content, reasoning, calls, and metrics |
| `tool_returned` | Observation on the step that requested the call, matched by call ID and agent scope |
| Provider-hosted tool blocks | Calls and observations on their originating step, marked `extra.avp.server_side` on calls |
| Subagent events | Embedded child documents with references from the parent's observations |
| `error_occurred` | A system step containing the error message |
| `agent_stopped` | Completion and stop reason in root extension metadata |

Tool errors and MCP structured content are preserved in each observation's
`extra.avp`. Public reasoning becomes `reasoning_content`; encrypted reasoning
does not. Images become content-addressed files, deduplicated across the run.
ATIF supports PNG, JPEG, GIF, and WebP images; other image types fail explicitly.

A child starts with its recorded input serialized as JSON in a user step,
marked `extra.avp.input_encoding: "json"`. Its agent version is `"unknown"`
because AVP does not report one. Its prompt expansions, system instructions,
and model calls are not invented when the adapter cannot report them.
Delegation without a model-issued tool call becomes a system step.

## Metrics and fidelity

Each model response retains its usage independently. `final_metrics` includes
the document and its descendants once, as its `notes` and
`extra.avp.usage_scope` explain. Do not add a child's totals to its parent's
totals again. `total_steps` counts only the steps in that document.

For an opaque child, the exporter uses `subagent_usage` when available and does
not fabricate agent steps. An aggregate metric is omitted if any contributing
usage is unknown; `final_metrics.extra.avp.known_totals` holds the measured
portion. In particular, AVP's zero placeholder for an unknown cost does not
become an ATIF claim that the model call was free. For incomplete runs, all
metrics cover only what was recorded.

ATIF fields hold the run's messages, tool definitions, calls, observations,
subagents, image references, and metrics. The export does not embed source
events, source-event IDs, a reconstruction map, the original Commission, or the
unused Descriptor catalog. The launcher already saves the dispatched Commission
separately. Only the effective agent configuration belongs in this record.

Extensions under each object's `extra.avp` have operational purposes:

| Location | Details | Purpose |
|---|---|---|
| Root or child document | Completion, stop reason, timestamps, final typed `output` | Distinguish success, failure, and interrupted runs; score structured answers |
| Agent and tool definitions | Provider and endpoint, effective MCP servers, skills, subagents, tool ownership and output schemas | Understand the environment the agent actually used |
| Agent step | Response duration, requested model when different, provider finish reasons | Attribute latency and model behavior |
| Message or observation | Indexed citations, refusal flags, provider annotations | Interpret visible content and retain provider-specific semantics |
| Agent step reasoning | Signatures and encrypted content, with character spans for public reasoning | Keep provider reasoning data without presenting ciphertext as readable thought |
| Tool call and observation | Start/end timestamps, duration, error flag, structured content, provider metadata | Inspect pending or failed work and consume typed tool results |
| Metrics | Cache-write and reasoning-token counts, cost source, partial known totals | Preserve accounting distinctions without copying mapped usage fields |

Opaque children retain unrepresented reported usage details, including response
counts, in their document's `extra.avp.usage_details`. Runtime annotations are
attached to the relevant ATIF objects. Generic readers use standard fields;
AVP consumers read these extensions where they need the additional behavior.

For file-size comparisons, use the same JSON formatting and include referenced
image files. Images are stored once per bundle. The export does not redact data.

## Completing the migration

The current SDK Recorders, adapter commands, CLI monitoring, scorers, conformance
checks, and sharing code still consume AVP events. This utility does not by
itself replace that live contract. The next implementation step is to make both
SDKs produce ATIF and update those consumers together, without an old-format
compatibility or archival layer.

The main integration issue is live delivery: ATIF defines a document with steps
and observations, while the CLI currently tails an append-only event stream.
The recorder and launcher need to deliver updates to the ATIF document so a
viewer can see pending calls and later results, and so interruption leaves a
usable partial document. That delivery mechanism need not preserve the old
AVP event schema. Structured outputs and termination states must remain
explicit so scorers do not infer them from final prose.

The checked schema has no blocker for the recorded conversation, tool,
subagent, image, or usage capabilities exercised so far. Provider-exact session
resumption remains a separate capability: ATIF groups message, reasoning,
calls, and observations rather than preserving their original interleaving.
The exporter retains provider annotations but does not claim to reconstruct a
provider request or resume its session. Neither format can recover context,
token IDs, or log probabilities that the runtime never recorded. Full migration
still requires changing the live producers and consumers; export coverage alone
does not complete that work.

## Validation

Tests use the shared Recorder cases plus the upstream generated JSON Schema in
[`testdata/atif`](../testdata/atif/README.md). They check semantic properties the
schema cannot express, including matching call IDs, nested references, complete
versus truncated runs, and usage accounting.

`make check` also runs `make atif-adapters-check`: it converts temporary
trajectories from all eight adapter suites and checks their ATIF schemas,
response boundaries, tool links, image assets, usage, and typed final outputs.
Python suites expose their normal temporary output files through a pytest
capture hook; TypeScript suites capture their existing event sinks only while
this check runs. Captured inputs are deleted afterward. The check makes no
paid calls. Native Codex and Claude tests retain their documented opt-in flags.

For an independent check, install the pinned Harbor source in a development
environment that already has the SDK's Pydantic dependency:

```sh
uv pip install --python avp-sdk/python/.venv/bin/python --no-deps \
  'harbor @ git+https://github.com/harbor-framework/harbor.git@9c7a39b991d7e2205019f6be0598cbd22d84bfc3'
avp-sdk/python/.venv/bin/python -m harbor.utils.trajectory_validator export/trajectory.json
```

Harbor's validator checks its Pydantic models and referenced media. It also
checks rules beyond JSON Schema, such as sequential step IDs and observation
references to calls in the same step.

Live checks exercise Pydantic AI, Pi, Deep Agents, OpenAI Agents, Codex, Claude,
OpenCode, and Gemini CLI across Anthropic, OpenAI, and Google. They include
intentional tool errors, native shell or MCP tools, structured output where
supported, and subagents. ATIF documents are checked with Harbor's validator
and against the usage reported by each runtime. Unsupported capabilities remain
those documented in each adapter's README; conversion does not invent them.
