# AVP Conformance Suite — v0.1

Language-agnostic test cases that pin down behavior the spec mandates. Every AVP-compliant SDK MUST pass every case in this directory.

This is the operational answer to spec drift. Without a shared core implementation (AVP follows OpenTelemetry's pattern: native idiomatic SDKs per language, not a single Rust core with bindings), the conformance suite is what keeps Python, TypeScript, Go, Rust, and future SDKs from disagreeing about what the spec actually means at the prelude shape, source-field discipline, MCP lifecycle, and tool-dispatch wire shape.

## Layout

```
conformance/v0.1/
├── README.md          (this file — what the suite is and how cases are organized)
├── HARNESS.md         (what an SDK test harness MUST do to consume cases)
├── schema/
│   └── test-case.schema.json   (JSON Schema for case files)
├── validate.py        (validates all cases against test-case.schema.json)
└── cases/
    ├── enabled-builtins/        (Commission.enabled_builtin_* allowlist gating)
    ├── mcp/                     (mcp_server_connected lifecycle, dispatch_target tagging)
    ├── prelude/                 (run_requested → agent_described → agent_started ordering)
    ├── reasoning/               (avp.reasoning.* attributes on assistant_message)
    ├── refusal/                 (refusal_recorded provenance)
    ├── resolver/                (resolver_not_configured / commission_collision gates)
    ├── skills/                  (managed_ref_resolved for skill refs; agent_started.data.skills[] registration)
    ├── source-field/            (source=agent vs supervisor discipline)
    ├── subagent/                (subagent_invoked / subagent_returned bracketing, avp.subagent.run_id)
    ├── tools/                   (built-in tool surface on agent_started, tool_failed semantics)
    └── text/                    (text_emitted shape)
```

## How an SDK uses the suite

1. Implement a small harness per [`HARNESS.md`](./HARNESS.md). The harness is responsible for:
   - Loading a case file.
   - Spinning up the SDK's agent (or supervisor) with `case.config`.
   - Stubbing the model with `case.scripted_model`.
   - Stubbing local tools with `case.scripted_tools`.
   - Driving a mock supervisor with `case.scripted_supervisor`.
   - Capturing the emitted trajectory (NDJSON over stdout, or in-memory equivalent).
   - Asserting `case.expectations`.

2. Run every case in `cases/**/*.json` and report pass/fail.

3. CI gates SDK releases on a green conformance run.

## Case file format

Each case is a JSON document validating against [`schema/test-case.schema.json`](./schema/test-case.schema.json). Minimal example:

```json
{
  "id": "example-case",
  "title": "What this case asserts in one line",
  "spec_refs": ["spec/v0.1/trajectory.md#3-the-agent-loop-normative"],
  "applies_to": ["agent"],
  "commission": { "schema_version": "0.1", "run_id": "test-1" },
  "scripted_model": [
    { "tokens_input": 10, "tokens_output": 5, "cost_usd": 0.001, "duration_ms": 1, "text": "done", "converged": true }
  ],
  "expectations": {
    "events": [
      { "match": { "type": "agent_started", "source": "agent" } },
      { "match": { "type": "agent_stopped", "reason": "converged" } }
    ],
    "final_state": { "stop_reason": "converged", "total_turns": 1 }
  }
}
```

### Matchers

`match` is a partial pattern. Every key/value in `match` must appear in the event with that value (deep-equal for nested objects); other fields MAY be present.

Default ordering is `in_order_subsequence`: matchers must appear in the captured trajectory in the given order, but other events MAY interleave between them. Use `in_order_strict` when the entire trajectory must match exactly. Use `any_order` when matchers must each appear somewhere but order does not matter.

`forbidden_events` patterns MUST NOT appear anywhere in the trajectory.

### Supervisor scripting

The `scripted_supervisor` field is retained in the test-case schema for backwards compatibility but is a no-op in v0.1: there is no supervisor → agent runtime channel for the harness to drive. Existing case files may still declare steps; the v0.1 harness does not dispatch them.

## Adding a case

1. Identify a normative requirement in one of the v0.1 specs ([`trajectory.md`](../../spec/v0.1/trajectory.md), [`commission.md`](../../spec/v0.1/commission.md), [`agent-descriptor.md`](../../spec/v0.1/agent-descriptor.md), [`resolver.md`](../../spec/v0.1/resolver.md)) that two well-meaning implementers could resolve differently.
2. Write the smallest case that distinguishes the right answer from the wrong ones. One requirement per file.
3. File-name slug = `id` field, kebab-case.
4. Run `python3 validate.py` — every case file MUST validate against the schema.
5. Reference the spec section in `spec_refs`.

If a behavior cannot be tested via this format (e.g. cross-cutting transport concerns), add a normative paragraph to the relevant spec (or to the umbrella [`spec/v0.1/README.md`](../../spec/v0.1/README.md)) and link the discussion.
