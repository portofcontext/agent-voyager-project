# AEP Conformance Harness Contract — v0.1

Every AEP SDK ships a harness binary or test-runner module that consumes the cases in this directory. The harness is small (a few hundred lines of code in any language) and stable. This document specifies what it MUST do.

## Inputs

The harness is invoked once per case file. Its inputs are:

- A path to a case file (validates against [`schema/test-case.schema.json`](./schema/test-case.schema.json)).
- Optionally, a path to write a JUnit-style report (so CI can aggregate).

## What the harness MUST do

1. **Parse and validate the case** against `test-case.schema.json`. Reject malformed cases with a clear error.
2. **Configure the SDK under test** with `case.config`. The Config MUST be passed to the SDK exactly as written — the harness MUST NOT modify it.
3. **Stub the model.** The SDK's model client MUST be replaced (via dependency injection, monkey-patching, or a recording HTTP layer — language-idiomatic) with one that returns `case.scripted_model[i]` on the i-th turn. The mock model MUST NOT make network calls. If the runner requests more turns than the script provides, the harness MUST raise an error.
4. **Stub local tools.** When the SDK invokes a tool whose name is in `case.scripted_tools`, the harness returns the configured `output` (or raises with `error`). Tools NOT in `scripted_tools` MUST be assumed to be supervisor-executed (i.e. they appear in `case.config.tools`) and route via `tool_exec_requested`.
5. **Drive the mock supervisor.** As the runner emits events:
   - For each `case.scripted_supervisor` step whose `on.match` is satisfied by the latest emitted event, the harness fires the step.
   - After `step.delay_ms`, if `step.skip` is false, the harness substitutes placeholders in `step.send` (see [Placeholder substitution](#placeholder-substitution) below) and sends the resulting message to the runner over its supervisor-message channel. If `step.skip` is true, the harness deliberately does nothing (timeout cases rely on this).
   - **A step fires every time its `on` matcher is satisfied.** A single step that matches a given event type will fire on every occurrence. To respond differently on different fires, declare separate steps; when one event satisfies multiple `on` matchers, every matching step fires in declaration order.
6. **Capture the trajectory.** Read every event the runner emits to its trajectory channel. The harness MUST record events in emission order with millisecond-or-better resolution.
7. **Assert expectations:**
   - `expectations.events` patterns MUST match per `expectations.ordering` (default `in_order_subsequence`).
   - `expectations.forbidden_events` patterns MUST NOT match any captured event.
   - `expectations.final_state` MUST hold for the run's terminal state (taken from the `agent_stopped` event).
8. **Exit code.** `0` on pass, non-zero on any assertion failure or harness error. Print which expectation failed and the captured trajectory snippet.

## What the harness MUST NOT do

- Make network calls. All cases are deterministic and self-contained.
- Mutate the case file or config.
- Interpret event types not enumerated in the v0.1 spec — custom events MUST be passed through as opaque objects.
- Modify event order or field values during capture.
- Time out the run independently. Boundary and hook timeouts in cases are exercised by the SDK's own timeout machinery; the harness has no clock of its own besides `delay_ms` for supervisor scripting.

## Placeholder substitution

Supervisor messages need to reference IDs the runner generates at runtime (`request_id`, `run_id` if not authored by the supervisor, sometimes `call_id`). The harness MUST support the following substitutions in any string value within `step.send` before transmitting:

| Placeholder | Replaced with |
|---|---|
| `{{event.<field>}}` | The value of `<field>` from the event that matched `step.on`. Dotted paths (`{{event.context.input.path}}`) recurse into nested objects. |
| `{{now}}` | The current timestamp, ISO 8601 / RFC 3339 with `Z` suffix. |
| `{{run_id}}` | Shorthand for `{{event.run_id}}`. |

Substitutions are applied to string values only. Numeric, boolean, and structural fields are passed through unchanged. If a placeholder cannot be resolved (the field is absent on the matched event), the harness MUST fail the case with a clear error.

## Matching rules (normative)

`match` is a deep partial-equality pattern over a single event:

- Object fields: every key in `match` MUST be present in the event with a deep-equal value. Object-valued matchers recurse.
- Array fields: matched as ordered exact equality (not subsequence). To match a subset of an array, the case author SHOULD restructure the matcher.
- Scalar fields: strict equality (no coercion).
- Fields absent from `match` are unconstrained.

A captured event matches the matcher if every constraint in `match` holds. The captured event MAY have additional fields.

## Ordering modes

| Mode | Semantics |
|---|---|
| `in_order_subsequence` (default) | The matchers form an ordered subsequence of the captured trajectory. Unmatched events MAY appear before, between, or after matchers. |
| `in_order_strict` | The matchers correspond 1:1 to the captured trajectory in order. Number of captured events MUST equal number of matchers. |
| `any_order` | Each matcher MUST match at least one captured event. Captured-event-to-matcher assignment is bijective. |

## Reporting

The harness prints (and optionally writes JUnit XML) per case:

```
PASS  boundary-cost-strict-less-than-runs       (12ms)
FAIL  hook-verdict-stop-yields-supervisor-stopped
        expected event matching {type: "agent_stopped", reason: "supervisor_stopped"}
        captured: agent_stopped { reason: "converged", ... }
        full trajectory: <last 20 events>
```

## Suggested invocation shape

```
aep-conformance --case <path>           # run one case
aep-conformance --suite ./cases         # run all cases under a directory
aep-conformance --suite ./cases --junit out.xml
```

Each SDK's harness binary SHOULD share this CLI surface so CI configs are portable.
