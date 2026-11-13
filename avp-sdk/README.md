# AVP SDKs

The AVP SDKs (Python and TypeScript) have two goals:

- **Define the wire:** types for the Commission, Agent Descriptor, Agent Start,
  and ATIF trajectory, matching the specs' schemas.
- **Share the common work:** code that every agent runner or supervisor would
  otherwise write itself, such as checking a Commission, writing a Trajectory,
  and pricing a response.

Each SDK behaves the same way, so an agent or supervisor gets the same results
in either language.

## Source of truth

The spec documents in [`spec/v0.1/`](../spec/v0.1/) come first. A change to the
wire starts there, never in an SDK or a schema.

The Python SDK comes second, because the rest is generated from it:

1. Commission and Descriptor reference tables define their fields; Trajectory adopts the pinned upstream ATIF models.
2. Python implements those tables and vendors the upstream ATIF models.
3. The models generate `spec/v0.1/*.schema.json` (`make schemas`).
4. TypeScript takes its types from those schemas.

Nothing yet checks the models against the tables automatically, because the
tables are text written for people. Reviewers check them by hand.

A new feature is built and decided in Python first, then copied to TypeScript.

## What every SDK provides

| Part | What it does | Python |
|---|---|---|
| Wire types | The Commission, the Agent Descriptor, and ATIF trajectories, validated as the schemas define them | `avp.commission`, `avp.descriptor`, `avp.trajectory` |
| Agent Start | Complete resolved configuration with inline skill contents | `avp.agent_start` |
| Recorder | Writes an agent's Trajectory to the spec's rules, described below | `avp.recorder` |
| Commission checks | The refusal cases in the Commission spec that need only the Commission and the agent's Descriptor | `avp.utils.preflight` |
| Run plan | What a run uses and what it turns off, from the Commission and the agent's Descriptor, described below | `avp.utils.run_plan` |
| Pricing | `cost_usd` and `cost_source` for a response, from models.dev prices | `avp.utils.pricing` |
| Endpoints | A provider's default `base_url` and API-key header, for sandbox egress, credential proxies, and metering | `avp.utils.endpoints` |
| Agent command line | The command line every agent answers, described below | `avp.agent_cli` |

Trajectories use ATIF directly. See the [ATIF guide](docs/atif.md) for reading
them with the SDK and existing ecosystem tools.

### Shared provider data

Each SDK ships a snapshot of the models.dev prices, refreshed before each
publish (`make sdk-data`), so pricing works offline. A caller can pass a
maximum age to fetch newer prices into a cache file, or its own file for the
same costs on every rerun. Without either, the SDK never calls models.dev.

The repository stores prices, endpoints, and endpoint refresh rules once in
[`data/`](data/). Relative file links in each SDK's data directory point there.
`make sdk-data` fetches the catalog once, refreshes both snapshots, and links
all shared JSON files into every SDK. URL fallbacks and package-to-auth rules
live in `avp_endpoint_defaults.json`, so refreshes use the same rules in every
language.

Package builds embed the linked data as regular files, so each published package
contains its snapshot without depending on the repository or another SDK.
`make sdk-data-check` verifies the complete file inventory and shared links,
then checks every data file in the Python wheel, source distribution, and TypeScript npm package.

Endpoints load, cache, and refresh the same way as prices in both SDKs.
models.dev gives most providers' `api` URL but not the ones whose clients have
a URL built in, such as `anthropic` and `openai`; a short list of gap fillers covers
those, and models.dev wins where both have one. Python exposes
`avp.utils.endpoints` and TypeScript
`@agent-voyager-project/sdk/utils/endpoints`. Catalog translation is checked
against the same cases in [`testdata/endpoints/`](testdata/endpoints/).

Each endpoint also says where the provider's API key goes, so a supervisor can
set up a credential proxy for a Model's `proxy` credential: `authorization`
with `Bearer `, or a header such as Anthropic's `x-api-key`. It comes from the
AI SDK package models.dev names for the provider, so new providers on a known
package need no change. A provider has no auth when its key isn't a fixed
header value, such as `google-vertex` with short-lived OAuth tokens, or when
its package isn't known; a proxy can't add that key.

### Run plan

Every agent combines its Descriptor with the Commission before the run starts:
the agent settings limit its built-in items (an absent list allows all, `[]`
allows none), the Commission adds its own MCP servers and skills, and its
`system_prompt` replaces the agent's. Each legacy agent wrote this itself, in
its own way. The run plan does it once and returns:

- `started`: a `RunContext` describing effective configuration. The adapter
  configures its runtime, adds connected MCP tools and status, and passes it
  to `Recorder.start` to populate the ATIF agent and prompt steps and snapshot
  effective configuration and accessible skill directories.
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
| `ping` | `{"type": "pong", "avp_version": "0.1"}`, without loading the agent: checks installation and the AVP version it speaks |
| `describe` | The agent's Descriptor as JSON |
| `run` | ATIF JSON; atomic file snapshots, or one completed document on stdout with `-` |

Paths default to stdout where `--out` is optional.

`run` hands the Commission and a `TrajectorySink` to the adapter. The Recorder
publishes `Recording` snapshots containing the ATIF document, referenced image
bytes, Commission, Descriptor, and Agent Start. File sinks save the input
documents and images before the trace snapshot. Stdout retains only ATIF.

Exit codes: `0` when the Trajectory is complete, a refusal included; `130` when
SIGINT or SIGTERM interrupted the run; anything else is a crash.

## The Recorder

The Recorder assembles native reports into ATIF. It validates the Commission,
records effective inputs, merges streamed response chunks, prices each response,
attaches observations to tool calls, and records embedded child trajectories.
It closes abandoned work and preserves typed output and terminal reasons in
`extra.avp`. Missing usage stays unknown.

Adapter method inputs live in `avp.reports` (TypeScript: `sdk/reports`). They
are not a persisted event format. `avp.trajectory` exposes upstream wire models,
`parse_trajectory`, and `Recording`. Both SDKs run the same Recorder cases in
[`testdata/recorder/`](testdata/recorder/).

### Saved run documents

File output saves `commission.json`, `descriptor.json`, `agent-start.json`, and
`trajectory.json`. The [Agent Start spec](../spec/v0.1/agent-start.md) defines the
resolved snapshot, including full tool metadata and inline skill contents.
The adapter reports what its runtime actually selected; the SDK captures exposed
skill directories, including supporting files and subagent skills.

Read the snapshot with Python `AgentStart.model_validate_json(...)` from
`avp.agent_start`, or TypeScript `parseAgentStart(...)` from `sdk/agent_start`.
A refused run has no Agent Start; direct runs may have no Commission.

The final result stays in ATIF. Python `final_output(trajectory)` and TypeScript
`finalOutput(trajectory)` return a distinct `extra.avp.output` when present and
otherwise use the final agent message. Generated files are ordinary files saved
by the runtime or deployment; the SDK has no generic artifact API or manifest.

## Out of scope

- Agent base classes, agent loops, and driver protocols: each agent's runtime
  owns its loop.
- Transport, multi-run orchestration, and persistence, apart from the agent
  command line above.
- Workspace and directory setup for launching an agent: avp-cli.
- The conformance harness and cases: `avp conformance` in avp-cli.
- Conversation-history conversion between provider formats.
