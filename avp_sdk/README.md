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
SDK reads it the same way to:

- find a provider's default `base_url` when the Model has none
- price a response for `cost_source: "computed"`

Open: the live API or a bundled snapshot.

| | Live API (`https://models.dev/api.json`) | Bundled snapshot |
|---|---|---|
| Size | About 6 MB per fetch | About 0.8 MB trimmed to URLs and prices (95 KB gzipped) |
| Sandboxed agents | Fails: sandboxes deny network by default | Works offline |
| Same cost on rerun | No: prices change between runs | Yes, for the same snapshot |
| Freshness | Current | As of the last sync |

One option is a shared snapshot file that every SDK embeds, refreshed by a
script, which a caller can replace with a newer file.

## Decided case by case

Helpers from the old Python bindings (`avp/bindings/python`). Each is kept only
if the spec requires it or several agents need the same thing. Rewrite what is
kept; don't port it.

| Helper | What it does | Used by (old code) | Decision |
|---|---|---|---|
| Recorder | Turns an agent's native events into a valid Trajectory: event order, usage per response, tool and subagent pairing, closing the run | 10 agents | Open |
| Recorder vectors | Shared test data the Recorder in each SDK must pass | Python, Rust, TypeScript tests | Open |
| `agent_cli` + `sink` | The `run --commission <path> --out <ndjson>` command line and NDJSON writing every agent uses | 11 agents | Open |
| `preflight` | The refusal checks in the Commission spec's rules for agents | 6 agents | Open |
| `launch` | Workspace and directory setup for launching an agent | 1 agent, avp-cli | Open; may belong in avp-cli |
| `history` | Rebuilds the conversation from a Trajectory | None | Open |
| `gen_ai` | Converts a Trajectory to OpenTelemetry GenAI attributes | None | Open |
| `envelope` | Strict base config and shared event fields | avp-cli | Drop |

## Out of scope

- Agent base classes, agent loops, and driver protocols: each agent's runtime
  owns its loop.
- Transport between supervisor and agent, multi-run orchestration, and
  persistence.
- The conformance harness and cases: `avp conformance` in avp-cli.
