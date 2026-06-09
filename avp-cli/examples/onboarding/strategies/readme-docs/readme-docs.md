# AVP documentation (curated excerpts)

The "hand it the docs" strategy: excerpts from the AVP README and specs, the way
an agent would get them if you pasted the project's documentation into context.

---

## From README.md

AVP is an open standard for AI agents and the systems that run them. A supervisor
sends a job, the agent runs it and reports back, and both sides know what to
expect because both sides speak AVP.

The supervisor sends a small JSON **Commission** (what to do, which model, what
resources are available); the agent runs the work and streams back a
**Trajectory** of events that records every model and tool call, what the run
cost, and how it ended.

AVP picks a shared vocabulary instead of inventing new wire formats: CloudEvents
for the event envelope, OpenTelemetry for spans and token usage, JSON-RPC for
resource lookup, MCP for tools, and Agent Skills for skill files.

### What AVP defines (four specs, each adoptable on its own)

| Sub-spec | What it covers |
|---|---|
| Trajectory | The stream of events an agent emits as it runs. |
| Commission | The run configuration the supervisor sends at startup. |
| Agent Descriptor | What an agent advertises about itself before a run. |
| Resolver API | The JSON-RPC service the agent calls to look up referenced resources. |

The first three are data-shape specs; the Resolver API is the only two-party wire
protocol.

---

## From commission.md (field reference)

A Commission is the supervisor's charter for one run.

- `schema_version`: `"0.1"`.
- `run_id`: string id for the run.
- `model`: REQUIRED. Canonical `origin/model` slug, e.g. `anthropic/claude-haiku-4-5`.
- `prompt`, `system_prompt`: the agent-plane instructions.
- `mcp_servers`: inline servers the agent dials directly. `McpServerStdio` =
  `{"type":"stdio","id":...,"command":[...]}`; `McpServerHttp` =
  `{"type":"http","id":...,"url":...}`. Surfaced on `agent_started` with each
  dial's status.
- `skills`: inline `{"id":..., "files": {"SKILL.md": "<content>"}}` entries (the files map must contain "SKILL.md").
- `enabled_builtin_tools`: subtractive allowlist over the agent's Descriptor
  (absent = all built-ins, `[]` = none, subset = only those). Same for
  `enabled_builtin_{mcp_servers,subagents,skills}`.
- `output_schema`: JSON Schema for the agent's structured output.

---

## From trajectory.md (event catalog)

The trajectory is the ordered sequence of events emitted during a run, the source
of truth a reviewer reads top-to-bottom. Ten event types in v0.1, all past-tense
facts under the `avp.*` namespace, all with `source = avp://agent`:
`run_requested`, `agent_described`, `agent_started`, `agent_stopped`,
`assistant_message`, `tool_invoked`, `tool_returned`, `subagent_invoked`,
`subagent_returned`, `error_occurred`.

A run opens with `run_requested` then `agent_described` then `agent_started`, and
closes with `agent_stopped` carrying a `StopReason`. A **turn** is one
`assistant_message`: it carries the model's `avp.content` plus the per-turn
`avp.usage` and `avp.cost_usd`. The agent publishes no cumulative totals; the
consumer reduces the per-turn deltas. Every event is a CloudEvents 1.0 envelope
carrying OTel span ids (`trace_id`, `span_id`, `parent_span_id`) on its `data`.

---

## From avp-cli/README.md (the CLI)

`avp init [benchmark]` scaffolds a `<name>.eval.json` and seeds its commissions
into `~/.avp/commissions/`. `avp eval run <config>.eval.json` runs the commissions
over the dataset and prints a ranked board. `avp cm create` builds a commission;
`avp cm check <id|file>` validates one. `avp agent install <name>` installs goose
or claude-code.

An eval config is `{name, agents, dataset, scorer, commissions}`:
- `dataset.source`: `inline` | `file` | `huggingface`.
- `scorer.name`: `exact-match` | `structural-match` | `structural-fidelity` | `llm-judge`.
- `commissions`: library ids; each commission carries its own `model`.

The bundled ParseBench config uses a `huggingface` dataset (`llamaindex/ParseBench`),
the `structural-fidelity` scorer, and a commission wiring a PDF-vision MCP server
(stdio `pdf-vision`) with the `shell`/`write`/`edit` built-ins.
