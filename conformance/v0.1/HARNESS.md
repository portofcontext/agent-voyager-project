# AVP Conformance Harness Contract — v0.1

Every AVP SDK ships a harness binary or test-agent module that consumes the cases in this directory. The harness is small (a few hundred lines of code in any language) and stable. This document specifies what it MUST do.

## Inputs

The harness is invoked once per case file. Its inputs are:

- A path to a case file (validates against [`schema/test-case.schema.json`](./schema/test-case.schema.json)).
- Optionally, a path to write a JUnit-style report (so CI can aggregate).

## What the harness MUST do

1. **Parse and validate the case** against `test-case.schema.json`. Reject malformed cases with a clear error.
2. **Configure the SDK under test** with `case.commission`. The Commission MUST be passed to the agent exactly as written — the harness MUST NOT modify it.
3. **Stub the model.** The SDK's model client MUST be replaced (via dependency injection, monkey-patching, or a recording HTTP layer — language-idiomatic) with one that returns `case.scripted_model[i]` on the i-th turn. The mock model MUST NOT make network calls. If the agent requests more turns than the script provides, the harness MUST raise an error.
4. **Stub built-in tools.** When the agent invokes a tool whose name is in `case.scripted_tools`, the harness returns the configured `output` (or raises with `error`). Tools NOT in `scripted_tools` either fall through to a Commission-managed MCP server (post-resolution) or surface as `tool_failed` (unknown tool); the harness doesn't synthesize replies for them.
5. **Wire the resolver.** When the Commission carries any managed assets (`mcp_servers`, `skills`, or `subagents` non-empty) the harness MUST inject a `ResolverDriver`. The reference Python harness builds one from `case.scripted_resolver` (canned `avp.resolve` outcomes per `<kind>:<id>` and canned `avp.spawn_subagent` outcomes per subagent id; see `python/avp/src/avp/agent/mock.py`'s `ScriptedResolver`). Cases that want to exercise the `resolver_not_configured` startup gate set `case.omit_resolver: true` so the harness passes `resolver=None` even with managed assets present.
6. **Capture the trajectory.** Read every event the agent emits to its trajectory channel. The harness MUST record events in emission order with millisecond-or-better resolution.
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
- Time out the run independently. The harness has no clock of its own — cases drive turns through `scripted_model` and resolver outcomes through `scripted_resolver`; the harness has no asynchronous prodding.

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
PASS  prelude-emits-run-requested-then-agent-described       (12ms)
FAIL  source-field-agent-stopped-must-be-agent-source
        expected event matching {type: "agent_stopped", source: "avp://agent"}
        captured: agent_stopped { source: "avp://supervisor", ... }
        full trajectory: <last 20 events>
```

## Suggested invocation shape

```
avp-conformance --case <path>           # run one case
avp-conformance --suite ./cases         # run all cases under a directory
avp-conformance --suite ./cases --junit out.xml
```

Each SDK's harness binary SHOULD share this CLI surface so CI configs are portable.
