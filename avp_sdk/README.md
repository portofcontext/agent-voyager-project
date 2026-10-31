# AVP SDKs

Working doc for the scope of the AVP SDKs. Each language SDK (Python, Rust,
TypeScript) offers the same things, so an agent gets the same behavior
whichever language it is written in. Anything outside this scope belongs in the
agent or the CLI that needs it.

Status: draft. Decide each open item before building it into the Python SDK,
then copy the decision to Rust and TypeScript.

## In every SDK

### Wire types

Types for the Commission, the Agent Descriptor, and Trajectory events, matching
the JSON Schemas in [`spec/v0.1/`](../spec/v0.1/). Every SDK validates against
the same schemas, so a payload one SDK accepts, the others accept too.

The spec documents are the source of truth. Everything else follows from them:

1. Each spec's reference tables define its fields: name, type, whether it is
   required, and its description.
2. The Python SDK's Pydantic models are written from those tables.
3. The models generate `spec/v0.1/*.schema.json`.
4. Rust and TypeScript use those schemas, possibly by generating their types
   from them (to be decided).

A change to the wire starts in the spec document, never in the models or the
schemas.

- Drift check: open. A test could read each reference table and compare its
  fields, types, and required flags with the generated schema, so a model that
  strays from its spec fails `make check`. Hard to build, because the tables are
  text written for people: types such as
  `map<string, string | Secret reference>` and links would have to be parsed.
  Until then, reviewers check the models against the tables.
- The separate envelope module is dropped: the schemas define each event's
  common fields.

### models.dev data

[models.dev](https://models.dev) is what a Commission's `model` names, so every
SDK prices a response for `cost_source: "computed"` the same way.

- Each SDK ships a snapshot of the prices, refreshed when the package is
  published, so pricing works offline with no setup.
- A caller can ask for newer prices with a maximum age. The SDK then fetches
  models.dev when the prices are older and keeps them in a cache file. Without
  it, the SDK never calls models.dev.
- A caller can pass its own file instead, for the same costs on every rerun.
- No `base_url` lookup: models.dev has none for the main providers (`anthropic`,
  `openai`, `google`, `amazon-bedrock`), and an absent `base_url` already means
  the service's default.

## Decided case by case

Helpers from the old Python bindings (`avp/bindings/python`). Each is kept only
if the spec requires it or several agents need the same thing. Rewrite what is
kept; don't port it.

| Helper | What it does | Used by (old code) | Decision |
|---|---|---|---|
| Recorder | Turns an agent's native events into a valid Trajectory: event order, usage per response, tool and subagent pairing, closing the run | 10 agents | Open |
| Recorder vectors | Shared test data the Recorder in each SDK must pass | Python, Rust, TypeScript tests | Open |
| `agent_cli` + `sink` | The `run --commission <path> --out <ndjson>` command line and NDJSON writing every agent uses | 11 agents, avp-cli, conformance | Keep as `avp.agent_cli`, outside the spec: a provisional file transport until the spec defines one. Drops `--built-in` and `AVP_WORKSPACE`; sends the first events and refuses a Commission that isn't valid or fails `check_commission` |
| `preflight` | The refusal checks in the Commission spec's rules for agents | 6 agents | Keep, rewritten: `check_commission(commission, descriptor)` covers every case but the model ones |
| `launch` | Workspace and directory setup for launching an agent | 1 agent's test, avp-cli | Drop: the spec leaves workspaces out of scope, so it belongs in avp-cli |
| `history` | Rebuilds the conversation from a Trajectory | None | Drop: no users, and it mixes subagent messages into the main conversation. See "Converting message histories" in `tmp-future-ideas.md` |
| `gen_ai` | Converts a Trajectory to OpenTelemetry GenAI attributes | None | Keep, rewritten as `avp.utils.otel`: spans with GenAI attributes, as the spec README promises |
| CloudEvents | Converts a Trajectory event to a CloudEvent | New | Add as `avp.utils.cloudevents`, as the spec README promises |
| `envelope` | Strict base config and shared event fields | avp-cli | Drop |

## Out of scope

- Agent base classes, agent loops, and driver protocols: each agent's runtime
  owns its loop.
- Transport between supervisor and agent, multi-run orchestration, and
  persistence. The one exception is `avp.agent_cli`, a provisional file
  transport outside the spec, kept so agents can be run and tested until the
  spec defines transport.
- The conformance harness and cases: `avp conformance` in avp-cli.
