# AVP SDKs

The AVP SDKs (Python, Rust, TypeScript) give agents and supervisors the same
behavior in every language.

## Source of truth

The spec documents in [`spec/v0.1/`](../spec/v0.1/) come first. A change to the
wire starts there, never in an SDK or a schema.

The Python SDK comes second, because the rest is generated from it:

1. Each spec's reference tables define its fields.
2. The Python SDK's Pydantic models are written from those tables.
3. The models generate `spec/v0.1/*.schema.json` (`make schemas`).
4. Rust and TypeScript take their types from those schemas.

Nothing yet checks the models against the tables automatically, because the
tables are text written for people. Reviewers check them by hand.

A new feature is built and decided in Python first, then copied to Rust and
TypeScript.

## What every SDK provides

| Part | What it does | Python |
|---|---|---|
| Wire types | The Commission, the Agent Descriptor, and Trajectory events, validated as the schemas define them | `avp.commission`, `avp.descriptor`, `avp.trajectory` |
| Commission checks | The refusal cases in the Commission spec that need only the Commission and the agent's Descriptor | `avp.utils.preflight` |
| Pricing | `cost_usd` and `cost_source` for a response, from models.dev prices | `avp.utils.pricing` |
| Agent command line | The command line every agent answers, described below | `avp.agent_cli` |
| Recorder | Open, see below | |

Supervisor tools, built in Python first and in the other SDKs when a supervisor
needs them:

| Part | What it does | Python |
|---|---|---|
| OpenTelemetry | A Trajectory as spans with GenAI attributes, and as OTLP/JSON | `avp.utils.otel` |
| CloudEvents | One event as a CloudEvent | `avp.utils.cloudevents` |

### Pricing

Each SDK ships a snapshot of the models.dev prices, refreshed before each
publish (`make prices`), so pricing works offline. A caller can pass a
maximum age to fetch newer prices into a cache file, or its own file for the
same costs on every rerun. Without either, the SDK never calls models.dev.

## The agent command line

**Not part of the AVP spec**, which leaves transport to the deployment. It is a
provisional file transport, so every agent can be started the same way by
avp-cli, `avp conformance`, and anyone trying AVP, until the spec defines
transport.

```text
<agent> ping [--out <path>]
<agent> describe [--out <path>]
<agent> run --commission <path | JSON> --out <path | ->
```

| Command | Writes |
|---|---|
| `ping` | `{"type": "pong"}`, without loading the agent: a check that it is installed and runs |
| `describe` | The agent's Descriptor as JSON |
| `run` | The Trajectory as NDJSON, one event per line, to a file or to stdout with `-` |

Paths default to stdout where `--out` is optional.

`run` sends `run_requested` and `agent_described` itself, and refuses a
Commission that doesn't match the spec or fails the Commission checks. Only
then does it hand over to the agent, which sends everything from
`agent_started` on.

Exit codes: `0` when the Trajectory is complete, a refusal included; `130` when
SIGINT or SIGTERM interrupted the run; anything else is a crash.

## Open: the Recorder

The old SDK's Recorder turned an agent's native events into a valid Trajectory:
event order, usage per response, tool and subagent pairing, and closing the
run. Ten agents used it, with shared test data that each SDK's Recorder had to
pass. To decide:

- What it covers, and its interface.
- Whether the shared test data comes back, written before the Recorder, in
  `avp_sdk/testdata/recorder-vectors/`.

## Out of scope

- Agent base classes, agent loops, and driver protocols: each agent's runtime
  owns its loop.
- Transport, multi-run orchestration, and persistence, apart from the agent
  command line above.
- Workspace and directory setup for launching an agent: avp-cli.
- The conformance harness and cases: `avp conformance` in avp-cli.
- Dropped from the old SDK: `launch` (moved to avp-cli), `history` (see
  "Converting message histories" in `tmp-future-ideas.md`), and `envelope`.
