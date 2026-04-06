# Agent Execution Protocol (AEP)

> **Status:** Draft spec — v0.2
> **Package name:** `agent-execution-protocol` (pip) / `agent_execution_protocol` (import)
>
> AEP is an open standard. Any agent SDK, framework, or tool can implement AEP compliance without depending on any specific supervisor.

---

## What AEP Is

A minimal, open contract for agent observability. Two parts:

1. **Config** — what an supervisor passes to a runner at startup (NDJSON over stdin)
2. **Event stream** — what the runner emits during execution (NDJSON over stdout)

Transport: **NDJSON over stdio** (local) or **HTTP/SSE** (remote), identical schema.

AEP is to agent observability what OpenTelemetry is to distributed tracing — framework-agnostic, open, and implementable without a vendor account.

---

## Roles

AEP defines two roles:

**Supervisor** — the process that defines the run and observes the outcome. The supervisor writes the AEP config to the runner's stdin and reads the event stream from stdout. It decides what to run, sets limits, and interprets results. It never needs to know which SDK or model the runner uses internally.

**Runner** — the process that executes the agent. The runner reads the AEP config from stdin, runs the agent using whatever SDK it wraps, and emits AEP events to stdout. A runner is AEP-compliant if it follows the event requirements in this spec.

The supervisor/runner boundary is a process boundary. Communication is over stdio (local) or HTTP/SSE (remote). There is no shared library, no SDK dependency between them — only the AEP wire format.

---

## AEP Config

The config is the complete specification of what the runner needs to execute the agent. Any AEP-compliant runner reads this config and translates it to its SDK's options internally. The supervisor never needs to know which SDK is running.

```json
{
  "schema_version": "0.2",
  "run_id": "auth-refactor-20260326-abc123",
  "thread_id": "session-xyz",
  "prompt": "Refactor the auth module to use JWT",
  "system_prompt": "You are a senior Rust developer...",
  "model": "anthropic/claude-sonnet-4-6",
  "boundary": {
    "max_cost_usd": 2.00,
    "max_steps": 30,
    "max_tokens": 150000
  },
  "skills": [
    { "name": "pptx", "source": "anthropic:pptx@latest" },
    { "name": "style-guide", "source": "./skills/style-guide" }
  ],
  "hooks": [
    {
      "name": "after-each-write",
      "trigger": "on_tool:write_file",
      "timeout_ms": 10000,
      "default_verdict": "continue"
    }
  ],
  "output_schema": null,
  "meta": { "environment": "dev", "triggered_by": "ci" },
  "tags": ["auth", "refactor"]
}
```

### Config field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | Protocol version, e.g. `"0.2"` |
| `run_id` | string | yes | Unique run identifier (UUID or slug) |
| `model` | string | no | Model identifier, e.g. `"anthropic/claude-sonnet-4-6"` — if omitted, the runner uses its own default |
| `prompt` | string | no | Initial user prompt / task |
| `system_prompt` | string | no | System prompt prepended to all turns |
| `thread_id` | string | no | Links multi-turn sessions |
| `boundary` | object | no | Execution limits the runner enforces — stops the agent when any limit is reached |
| `skills` | object[] | no | Skills the runner should make available — see below |
| `tools` | object[] | no | Supervisor-executed tools the runner presents to the LLM — see below |
| `output_schema` | object | no | JSON schema for structured output |
| `hooks` | object[] | no | Supervisor hook declarations — trigger points where the runner pauses for a verdict |
| `meta` | object | no | Arbitrary metadata passed through to trajectory |
| `tags` | string[] | no | For filtering and organization |

### `skills` fields

Each skill is a reference to a SKILL.md — the runner loads it and makes it available to the agent.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Display name — used in `skill_read` and `skill_execute` events |
| `source` | string | yes | Where to load the skill from — scheme determines how the runner loads it (see below) |
| `config` | object | no | Opaque provider-specific options — AEP does not interpret this |

**`source` scheme conventions:**

| Scheme | Example | Runner behavior |
|---|---|---|
| `anthropic:<id>@<version>` | `anthropic:pptx@latest` | Anthropic-managed skill — runner uses beta API with `container` |
| Local path | `./skills/my-skill` or `/abs/path` | Runner reads `SKILL.md` from the path and injects content into context |
| Remote URL | `https://github.com/owner/repo/tree/main/skills/my-skill` | Runner fetches `SKILL.md` and injects content into context |
| Unknown scheme | `myplatform:skill-id` | Runner emits `skill_read` (trajectory records the request) then skips — does not fail the run |

### `tools` fields

Each entry declares a tool the runner registers with the LLM. When the model calls the tool, the runner pauses, emits `tool_exec_request`, reads `tool_exec_result` from stdin, and returns the result. The tool's logic runs on the supervisor side — config-declared tools are always supervisor-executed.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Tool name — used in `tool_call`, `tool_exec_request`, `tool_exec_applied` events |
| `description` | string | yes | Shown to the LLM to explain when to call the tool |
| `input_schema` | object | yes | JSON Schema for the tool's arguments |
| `output_schema` | object | no | JSON Schema documenting what the tool returns — not enforced by AEP |

**Supervisor tool execution flow:**

```
LLM calls tool
  → runner emits tool_call
  → runner emits tool_exec_request {call_id, tool, input}   [stdout]
  → supervisor executes tool locally
  → supervisor sends tool_exec_result {call_id, output}      [stdin]
  → runner returns result to LLM
  → runner emits tool_result
  → runner emits tool_exec_applied {call_id}                 [stdout]
```

On timeout: runner uses `""` as output and emits `tool_exec_applied` with `timed_out: true`.

### `boundary` fields

| Field | Type | Description |
|---|---|---|
| `max_cost_usd` | float | Stop when cumulative cost exceeds this value |
| `max_steps` | int | Stop after this many model turns |
| `max_tokens` | int | Stop when cumulative context tokens exceed this |

### Runner behavior expectations

**`boundary`** — the runner tracks cumulative cost, steps, and tokens and stops the agent when any limit is reached, emitting `agent_stop` with `reason: "budget_exhausted"`, `"turn_limit"`, or `"token_limit"` accordingly.

---

## AEP Event Stream: NDJSON

Each line is one JSON object. Required fields on every event: `type`, `run_id`, `ts` (ISO8601).

### Full event sequence example

```jsonl
{"type":"agent_start","schema_version":"0.1","run_id":"auth-refactor-20260326-abc123","model":"anthropic/claude-sonnet-4-6","prompt":"Refactor the auth module to use JWT","system_prompt":"You are a senior Rust developer...","tools":[{"name":"bash","description":"Run shell commands"},{"name":"write_file","description":"Write files to disk"}],"ts":"2026-03-26T10:00:00Z","tags":["auth","refactor"]}
{"type":"model_turn_start","run_id":"auth-refactor-20260326-abc123","step":1,"ts":"2026-03-26T10:00:01Z"}
{"type":"model_turn_end","run_id":"auth-refactor-20260326-abc123","step":1,"ts":"2026-03-26T10:00:02Z","duration_ms":980,"tokens_input":120,"tokens_output":45,"cost_usd":0.0004}
{"type":"tool_call","run_id":"auth-refactor-20260326-abc123","step":1,"call_id":"c1","tool":"bash","subtype":"shell","input":{"command":"find src/auth -name '*.rs'"},"ts":"2026-03-26T10:00:02Z"}
{"type":"tool_result","run_id":"auth-refactor-20260326-abc123","step":1,"call_id":"c1","tool":"bash","output":"src/auth/mod.rs\nsrc/auth/jwt.rs","duration_ms":230,"ts":"2026-03-26T10:00:02Z"}
{"type":"tool_call","run_id":"auth-refactor-20260326-abc123","step":2,"call_id":"c2","tool":"write_file","input":{"path":"/etc/cron.d/evil","content":"..."},"ts":"2026-03-26T10:00:03Z"}
{"type":"tool_result","run_id":"auth-refactor-20260326-abc123","step":2,"call_id":"c2","tool":"write_file","output":"rejected: path not in allow_write","rejected":true,"rejection_reason":"path_not_in_allow_write","duration_ms":1,"ts":"2026-03-26T10:00:03Z"}
{"type":"cost_update","run_id":"auth-refactor-20260326-abc123","total_cost_usd":0.031,"total_tokens":12400,"ts":"2026-03-26T10:00:30Z"}
{"type":"text_output","run_id":"auth-refactor-20260326-abc123","step":8,"text":"I've refactored the auth module to use JWT...","ts":"2026-03-26T10:00:45Z"}
{"type":"agent_stop","run_id":"auth-refactor-20260326-abc123","reason":"converged","total_tokens":13200,"total_cost_usd":0.041,"total_turns":9,"duration_ms":52000,"ts":"2026-03-26T10:00:52Z"}
```

---

## Event Type Reference

### `agent_start`

The first event. Captures full run context — prompt, model, tools, skills, system prompt. Without this, a trajectory is uninterpretable.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"agent_start"` | yes | |
| `schema_version` | string | yes | e.g. `"0.1"` |
| `run_id` | string | yes | UUID or slug, unique per run |
| `model` | string | yes | e.g. `"anthropic/claude-sonnet-4-6"` |
| `prompt` | string | no | The prompt/task given to the agent |
| `system_prompt` | string | no | System prompt provided to the model |
| `tools` | array | no | Tools available — each object has at minimum `name: string` |
| `skills` | string[] | no | Names of skills loaded for this run |
| `thread_id` | string | no | Links multi-turn sessions |
| `session_id` | string | no | SDK-internal session identifier |
| `ts` | ISO8601 | yes | |
| `tags` | string[] | no | |
| `meta` | object | no | Arbitrary key-values |

### `model_turn_start`

Emitted when the runner sends a request to the model.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"model_turn_start"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | Turn counter |
| `context_messages` | int | no | Number of messages in conversation history at this turn |
| `ts` | ISO8601 | yes | |

### `model_turn_end`

Emitted when the model response is received.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"model_turn_end"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | |
| `tokens_input` | int | yes | |
| `tokens_output` | int | yes | |
| `cost_usd` | float | yes | Cost of this inference call |
| `duration_ms` | int | yes | Time from request to response |
| `tokens_cache_read` | int | no | Tokens served from prompt cache (reduces cost) |
| `tokens_cache_write` | int | no | Tokens written to prompt cache |
| `ts` | ISO8601 | yes | |

### `tool_call`

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"tool_call"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | |
| `call_id` | string | yes | Unique within run |
| `tool` | string | yes | Tool name |
| `subtype` | string | no | `shell` \| `function` \| `retrieval` \| `embedding` \| `mcp` |
| `input` | object | yes | Tool input as passed by model |
| `ts` | ISO8601 | yes | |

### `tool_result`

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"tool_result"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | |
| `call_id` | string | yes | Matches `tool_call.call_id` |
| `tool` | string | yes | |
| `output` | string | yes | Result returned to model |
| `duration_ms` | int | yes | Execution time |
| `rejected` | bool | no | `true` if boundary enforcement fired |
| `rejection_reason` | string | no | `path_not_in_allow_write` \| `ceiling_reached` \| `tool_not_allowed` |
| `ts` | ISO8601 | yes | |

### `tool_call_failed`

For execution errors (not boundary rejections — those use `tool_result` with `rejected: true`).

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"tool_call_failed"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | |
| `call_id` | string | yes | |
| `tool` | string | yes | |
| `error` | string | yes | Error message |
| `ts` | ISO8601 | yes | |

### `text_output`

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"text_output"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | |
| `text` | string | yes | Agent's text response |
| `ts` | ISO8601 | yes | |

### `cost_update`

Periodic budget signal. Orchestrators read this to enforce cost or token ceilings.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"cost_update"` | yes | |
| `run_id` | string | yes | |
| `total_cost_usd` | float | yes | Cumulative cost so far |
| `total_tokens` | int | yes | Cumulative tokens so far |
| `ts` | ISO8601 | yes | |

### `skill_read`

Emitted when the runner loads a skill's `SKILL.md` into the agent's context.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"skill_read"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | |
| `name` | string | yes | Skill name from frontmatter |
| `source` | string | no | Path or URL the skill was loaded from |
| `ts` | ISO8601 | yes | |

### `skill_execute`

Emitted when the runner activates and begins executing a skill.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"skill_execute"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | |
| `name` | string | yes | Skill name |
| `ts` | ISO8601 | yes | |

### `context_compaction`

Emitted when the runner compacts the conversation history.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"context_compaction"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | Turn at which compaction fired |
| `tokens_before` | int | yes | Context size before compaction |
| `tokens_after` | int | yes | Context size after compaction |
| `compacted_messages` | array | no | The synthetic messages produced by compaction that replaced the prior history — typically 1-2 entries. Without these, the trajectory is uninterpretable after this event. |
| `ts` | ISO8601 | yes | |

### `error`

General error event (not tool-specific): rate limit, context window exceeded, runner crash.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"error"` | yes | |
| `run_id` | string | yes | |
| `code` | string | yes | `rate_limit` \| `context_limit` \| `auth_error` \| `runner_crash` \| `unknown` |
| `message` | string | yes | |
| `ts` | ISO8601 | yes | |

### `agent_stop`

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"agent_stop"` | yes | |
| `run_id` | string | yes | |
| `reason` | string | yes | `converged` \| `budget_exhausted` \| `token_limit` \| `turn_limit` \| `error` \| `interrupted` \| `supervisor_stopped` |
| `total_tokens` | int | yes | |
| `total_cost_usd` | float | yes | |
| `total_turns` | int | yes | |
| `duration_ms` | int | yes | Wall time for full run |
| `output` | any | no | Structured output if `output_schema` was set |
| `ts` | ISO8601 | yes | |

---

## Supervisor Hooks

Hooks give the supervisor active control over a run. The supervisor declares hook points in the config; when the runner reaches one, it pauses and waits for a verdict before continuing. The supervisor can run any checks it wants — test suites, file inspection, LLM judges, human review — and return a verdict that drives the runner forward, stops it, or injects a message into the agent's context.

This is the protocol layer. The supervisor decides what to check; AEP defines only the wire format for pausing and responding.

### How it works

**Transport: stdin is bidirectional.** After the runner reads the initial config from stdin at startup, stdin stays open. The runner reads hook verdicts from stdin as the run progresses. This requires no additional infrastructure — a supervisor that launches the runner as a subprocess already controls its stdin pipe.

For remote runners (HTTP/SSE transport), the supervisor provides a `hook_callback_url` in the config. The runner POSTs `hook_request` events to that URL and expects a `hook_verdict` JSON response body.

**Hook lifecycle:**

1. Runner reaches a declared trigger point
2. Runner emits `hook_request` to stdout (pauses execution)
3. Supervisor reads it, runs checks, writes `hook_verdict` to runner's stdin
4. Runner reads verdict, emits `hook_verdict_applied` to stdout
5. Runner applies the verdict: continues, stops, or injects a message

On timeout (runner waited `timeout_ms` with no response), the runner applies `default_verdict` and emits `hook_verdict_applied` with `timed_out: true`.

### `hooks` config fields

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | yes | — | Unique identifier within the run |
| `trigger` | string | yes | — | When to fire — see triggers below |
| `timeout_ms` | int | no | 30000 | How long runner waits for a verdict before applying `default_verdict` |
| `default_verdict` | string | no | `"continue"` | `continue` \| `stop` \| `inject` — applied on timeout |

### Hook triggers

| Trigger | Fires after |
|---|---|
| `on_start` | `agent_start` is emitted, before first model call |
| `on_turn_end` | each `model_turn_end` |
| `always` | each `model_turn_end` and each `tool_result` |
| `on_tool:<name>` | `tool_result` for the named tool, e.g. `on_tool:bash` |
| `on_stop` | `agent_stop` is emitted |

### `hook_request`

Emitted by the runner when it pauses at a hook trigger. Contains a context snapshot relevant to the trigger so the supervisor doesn't need to track state itself.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"hook_request"` | yes | |
| `run_id` | string | yes | |
| `request_id` | string | yes | Unique within run; matched in `hook_verdict` and `hook_verdict_applied` |
| `hook_name` | string | yes | Matches `hook.name` from config |
| `trigger` | string | yes | The trigger that fired |
| `step` | int | yes | Current agent step |
| `timeout_ms` | int | yes | How long runner will wait before applying default verdict |
| `call_id` | string | no | Present when trigger is `on_tool:<name>` |
| `context` | object | no | Snapshot of triggering event context (tool input/output, model response, etc.) |
| `ts` | ISO8601 | yes | |

### `hook_verdict` (stdin → runner)

Sent by the supervisor in response to a `hook_request`. Flows over stdin (not emitted to stdout). The runner reads this, then emits `hook_verdict_applied`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"hook_verdict"` | yes | |
| `run_id` | string | yes | |
| `request_id` | string | yes | Must match the `hook_request.request_id` |
| `verdict` | string | yes | `continue` \| `stop` \| `inject` |
| `message` | string | no | Required when `verdict: inject` — injected as a user message into agent context |
| `ts` | ISO8601 | yes | |

**Verdict semantics:**

- `continue` — runner resumes normally
- `stop` — runner emits `agent_stop` with `reason: "supervisor_stopped"` and halts
- `inject` — runner injects `message` as a user-role message into the conversation history, then continues; the agent's next turn will see it

### `hook_verdict_applied`

Emitted by the runner after it receives and acts on a verdict. Closes the `hook_request` / `hook_verdict_applied` pair in the trajectory, making it unambiguous what happened at the hook point.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"hook_verdict_applied"` | yes | |
| `run_id` | string | yes | |
| `request_id` | string | yes | Matches `hook_request.request_id` |
| `verdict` | string | yes | The verdict that was applied |
| `timed_out` | bool | no | `true` if `default_verdict` was applied due to timeout |
| `ts` | ISO8601 | yes | |

### `tool_exec_request`

Emitted by the runner when the model calls a config-declared tool. The runner pauses execution and waits for a `tool_exec_result` from the supervisor over stdin.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"tool_exec_request"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | |
| `call_id` | string | yes | Matches `tool_call.call_id` |
| `tool` | string | yes | Tool name |
| `input` | object | yes | Arguments the model passed |
| `timeout_ms` | int | yes | How long the runner waits before falling back to `""` |
| `ts` | ISO8601 | yes | |

### `tool_exec_result` (stdin → runner)

Sent by the supervisor in response to a `tool_exec_request`. Flows over stdin (not emitted to stdout). The runner reads this and returns the output to the model.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"tool_exec_result"` | yes | |
| `run_id` | string | yes | |
| `call_id` | string | yes | Must match the `tool_exec_request.call_id` |
| `output` | string | yes | Tool result returned to the model |
| `error` | string | no | Error message; runner prefixes with `"Error: "` and returns to model |
| `ts` | ISO8601 | yes | |

### `tool_exec_applied`

Emitted by the runner after it receives and applies a tool result. Closes the `tool_exec_request` / `tool_exec_applied` pair in the trajectory.

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"tool_exec_applied"` | yes | |
| `run_id` | string | yes | |
| `step` | int | yes | |
| `call_id` | string | yes | Matches `tool_exec_request.call_id` |
| `tool` | string | yes | Tool name |
| `timed_out` | bool | no | `true` if supervisor did not respond within `timeout_ms`; runner used `""` as output |
| `ts` | ISO8601 | yes | |

### Wire format example

Config declares a hook on every write tool call:

```json
{
  "schema_version": "0.2",
  "run_id": "eval-001",
  "model": "anthropic/claude-sonnet-4-6",
  "hooks": [{ "name": "review-writes", "trigger": "on_tool:write_file", "timeout_ms": 15000, "default_verdict": "stop" }]
}
```

Run with a suspicious write:

```jsonl
{"type":"agent_start","schema_version":"0.2","run_id":"eval-001","model":"anthropic/claude-sonnet-4-6","ts":"2026-03-30T10:00:00Z"}
{"type":"tool_call","run_id":"eval-001","step":1,"call_id":"c1","tool":"write_file","input":{"path":"/etc/cron.d/evil","content":"..."},"ts":"2026-03-30T10:00:01Z"}
{"type":"tool_result","run_id":"eval-001","step":1,"call_id":"c1","tool":"write_file","output":"written","duration_ms":5,"ts":"2026-03-30T10:00:01Z"}
{"type":"hook_request","run_id":"eval-001","request_id":"hr-001","hook_name":"review-writes","trigger":"on_tool:write_file","step":1,"call_id":"c1","context":{"tool":"write_file","input":{"path":"/etc/cron.d/evil"},"output":"written"},"timeout_ms":15000,"ts":"2026-03-30T10:00:01Z"}
```

Supervisor reads `hook_request`, runs its checks, writes on stdin:

```json
{"type":"hook_verdict","run_id":"eval-001","request_id":"hr-001","verdict":"stop","ts":"2026-03-30T10:00:02Z"}
```

Runner applies verdict:

```jsonl
{"type":"hook_verdict_applied","run_id":"eval-001","request_id":"hr-001","verdict":"stop","ts":"2026-03-30T10:00:02Z"}
{"type":"agent_stop","run_id":"eval-001","reason":"supervisor_stopped","total_tokens":165,"total_cost_usd":0.0004,"total_turns":1,"duration_ms":2000,"ts":"2026-03-30T10:00:02Z"}
```

---

## Custom Event Types

Any `type` value not listed above is a **custom event**. The validator passes custom events through without error. Use dot-namespaced types to avoid future conflicts:

```jsonl
{"type":"myframework.verifier_result","run_id":"r1","name":"tests-pass","passed":true,"ts":"..."}
{"type":"openai.reasoning_summary","run_id":"r1","summary":"...","ts":"..."}
```

Implementers are free to emit any additional events. AEP consumers that don't recognize a type should ignore it.

---

## Implementing AEP Compliance

A runner is AEP-compliant if it:

1. Reads a valid AEP config JSON from stdin before starting
2. Emits `agent_start` as the first line to stdout (including `prompt` and `tools` when available)
3. Emits `tool_call` before each tool invocation and `tool_result` after
4. Emits `model_turn_start` / `model_turn_end` around each model inference
5. Emits `cost_update` at least once per turn (or after each model call)
6. Emits `agent_stop` as the last line to stdout
7. All output is valid NDJSON (one JSON object per line, no pretty-printing)
8. Flushes stdout after each line

Optional but recommended: `text_output`, `error`.

If the config includes `hooks`, a compliant runner additionally:

9. Keeps stdin open after reading the initial config
10. At each declared trigger point: emits `hook_request`, pauses execution, reads one `hook_verdict` from stdin, emits `hook_verdict_applied`, and applies the verdict
11. On `verdict: stop` — emits `agent_stop` with `reason: "supervisor_stopped"` and halts
12. On `verdict: inject` — inserts `message` as a user-role message into conversation history before the next model call
13. On timeout — applies `default_verdict` and sets `timed_out: true` in `hook_verdict_applied`
