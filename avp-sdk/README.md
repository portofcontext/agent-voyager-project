# AVP SDKs

The AVP SDKs (Python, Rust, TypeScript) have two goals:

- **Define the wire:** types for the Commission, the Agent Descriptor, and
  Trajectory events, matching the specs' schemas.
- **Share the common work:** code that every agent runner or supervisor would
  otherwise write itself, such as checking a Commission, writing a Trajectory,
  and pricing a response.

Each SDK behaves the same way, so an agent or supervisor gets the same results
in any of the three languages.

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
| Recorder | Writes an agent's Trajectory to the spec's rules, described below | `avp.recorder` |
| Commission checks | The refusal cases in the Commission spec that need only the Commission and the agent's Descriptor | `avp.utils.preflight` |
| Run plan | What a run uses and what it turns off, from the Commission and the agent's Descriptor, described below | `avp.utils.run_plan` |
| Pricing | `cost_usd` and `cost_source` for a response, from models.dev prices | `avp.utils.pricing` |
| Agent command line | The command line every agent answers, described below | `avp.agent_cli` |

Supervisor tools, built in Python first and in the other SDKs when a supervisor
needs them:

| Part | What it does | Python |
|---|---|---|
| OpenTelemetry | A Trajectory as spans with GenAI attributes, and as OTLP/JSON | `avp.utils.otel` |
| CloudEvents | One event as a CloudEvent | `avp.utils.cloudevents` |
| Default base URLs | A provider's default `base_url`, for a Model without one: for sandbox egress, a credential proxy, or metering | `avp.utils.base_urls` |

### Pricing

Each SDK ships a snapshot of the models.dev prices, refreshed before each
publish (`make sdk-data`), so pricing works offline. A caller can pass a
maximum age to fetch newer prices into a cache file, or its own file for the
same costs on every rerun. Without either, the SDK never calls models.dev.

Default base URLs work the same way, in the same refresh. models.dev gives most
providers' `api` URL but not the ones whose clients have a URL built in, such
as `anthropic` and `openai`; a short list of gap fillers in the SDK covers
those, and models.dev wins where both have one.

### Run plan

Every agent combines its Descriptor with the Commission before the run starts:
the agent settings limit its built-in items (an absent list allows all, `[]`
allows none), the Commission adds its own MCP servers and skills, and its
`system_prompt` replaces the agent's. Each legacy agent wrote this itself, in
its own way. The run plan does it once and returns:

- `started`: what the run uses, as `agent_started` data. The agent configures
  its runtime from it, adds each MCP server's status and tools after
  connecting, and sends it as `agent_started`.
- `turned_off`: the built-in items the run may not use, which the agent hides
  from the model and refuses to run.

Turning the plan into the runtime's own settings stays agent code. Each SDK
passes the shared cases in [`testdata/run_plan/`](testdata/run_plan/).

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

`run` hands the Commission, as received, and an event sink to the agent. The
agent writes every event, through the Recorder or by hand.

Exit codes: `0` when the Trajectory is complete, a refusal included; `130` when
SIGINT or SIGTERM interrupted the run; anything else is a crash.

## The Recorder

Every agent must turn its runtime's events into a Trajectory that follows the
Trajectory spec's rules for agents. Those rules are the same for every agent
and easy to get wrong, so the Recorder implements them once. The agent reports
what its runtime did; the Recorder decides which events to write and in what
order:

- `run_requested`, `agent_described`, and refusing a Commission that doesn't
  match the spec or fails the Commission checks.
- One `assistant_message` per model response, merging a streamed response and
  pricing it.
- A `tool_invoked` for each `tool_use` block, paired with its `tool_returned`.
- Subagents closed as `abandoned` when the run stops while they still run.
- One `agent_stopped`, or an `error_occurred` when the run ends before it starts.

Using it is optional: an agent can write its events by hand. Whether an agent
conforms is for `avp conformance` to judge, not the Recorder. Each SDK's
Recorder passes the shared test cases in [`testdata/recorder/`](testdata/recorder/).

## Out of scope

- Agent base classes, agent loops, and driver protocols: each agent's runtime
  owns its loop.
- Transport, multi-run orchestration, and persistence, apart from the agent
  command line above.
- Workspace and directory setup for launching an agent: avp-cli.
- The conformance harness and cases: `avp conformance` in avp-cli.
- Dropped from the old SDK: `launch` (moved to avp-cli), `history` (see
  "Converting message histories" in `tmp-future-ideas.md`), and `envelope`.
