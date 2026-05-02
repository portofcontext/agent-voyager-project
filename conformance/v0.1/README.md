# AEP Conformance Suite — v0.1

Language-agnostic test cases that pin down behavior the spec mandates. Every AEP-compliant SDK MUST pass every case in this directory.

This is the operational answer to spec drift. Without a shared core implementation (AEP follows OpenTelemetry's pattern: native idiomatic SDKs per language, not a single Rust core with bindings), the conformance suite is what keeps Python, TypeScript, Go, Rust, and future SDKs from disagreeing about what the spec actually means at the timeout boundary, the cost edge, the source-field discipline, and the verifier lifecycle.

## Layout

```
conformance/v0.1/
├── README.md          (this file — what the suite is and how cases are organized)
├── HARNESS.md         (what an SDK test harness MUST do to consume cases)
├── schema/
│   └── test-case.schema.json   (JSON Schema for case files)
├── validate.py        (validates all cases against test-case.schema.json)
└── cases/
    ├── boundary/                (cost / steps / tokens edges)
    ├── hook-lifecycle/          (fired → resolved | timed_out)
    ├── source-field/            (source=runner vs supervisor discipline)
    └── timeout/                 (default verdicts, empty-string fallback)
```

## How an SDK uses the suite

1. Implement a small harness per [`HARNESS.md`](./HARNESS.md). The harness is responsible for:
   - Loading a case file.
   - Spinning up the SDK's runner (or supervisor) with `case.config`.
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
  "spec_refs": ["spec/v0.1/SPEC.md#10-the-runner-loop-normative"],
  "applies_to": ["runner"],
  "config": { "schema_version": "0.1", "run_id": "test-1" },
  "scripted_model": [
    { "tokens_input": 10, "tokens_output": 5, "cost_usd": 0.001, "duration_ms": 1, "text": "done", "converged": true }
  ],
  "expectations": {
    "events": [
      { "match": { "type": "agent_started", "source": "runner" } },
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

A `scripted_supervisor` step fires when a runner-emitted event matches its `on` pattern. The harness then either sends the `send` SupervisorMessage (after `delay_ms`) or, if `skip: true`, deliberately does nothing — so timeout cases can assert `*_timed_out` events.

## Adding a case

1. Identify a normative requirement in [`spec/v0.1/SPEC.md`](../../spec/v0.1/SPEC.md) that two well-meaning implementers could resolve differently.
2. Write the smallest case that distinguishes the right answer from the wrong ones. One requirement per file.
3. File-name slug = `id` field, kebab-case.
4. Run `python3 validate.py` — every case file MUST validate against the schema.
5. Reference the spec section in `spec_refs`.

If a behavior cannot be tested via this format (e.g. cross-cutting transport concerns), add a normative paragraph to SPEC.md instead and link the discussion.
