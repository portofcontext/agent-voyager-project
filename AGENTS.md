# AGENTS.md: Agent Voyager Project (AVP)

Orientation for any coding agent working with AVP. AVP (the **Agent Voyager
Project**) is an open standard for the agent-execution case: a **supervisor**
sends an **agent** a JSON **Commission**, the agent runs and streams back a
**Trajectory** of events, and the supervisor only observes (no mid-run push).
AVP specializes existing standards (CloudEvents, OpenTelemetry, JSON-RPC, MCP,
Agent Skills) rather than inventing wire formats.

Deeper references: [`SKILL.md`](SKILL.md) is the full AVP skill (concepts + the
three build patterns); [`README.md`](README.md) is install + quickstart;
[`CLAUDE.md`](CLAUDE.md) is the contributor guide for changing this repo; the
normative specs live under [`avp/core/spec/v0.1/`](avp/core/spec/v0.1/).

## Using AVP (the `avp` CLI)

- `avp init [benchmark]`: scaffold a `<name>.eval.json` and seed its commissions into `~/.avp/commissions/`.
- `avp eval run <config>.eval.json`: run the commissions over the dataset and print a ranked board (accuracy, pass-rate, $/run, turns/run).
- `avp cm create [id]` / `avp cm check <id|file>`: build a Commission into your library / validate one.
- `avp agent install <name>`: install a prebuilt agent (goose, claude-code).
- `avp run --agent A --env E "<task>"`: drop an agent into an environment and give it a task.

Every `avp eval` / `avp run` executes the agent inside a Docker-backed sandbox
(default-deny network); the one prerequisite is a running Docker daemon.

An eval config is `{name, agents, dataset, scorer, commissions}`:
- `dataset.source`: `inline` | `file` | `huggingface`.
- `scorer.name`: `exact-match` | `structural-match` | `structural-fidelity` | `llm-judge`.
- `commissions`: ids resolved from the library; each carries its own `model`.

The bundled ParseBench example uses a `huggingface` dataset (`llamaindex/ParseBench`),
the `structural-fidelity` scorer, and a commission wiring a PDF-vision MCP server.

## Authoring a Commission

A Commission is JSON. Required: `schema_version` (`"0.1"`), `run_id`, and `model`
as a canonical `origin/model` slug (`anthropic/claude-haiku-4-5`, `openai/gpt-4o`).
Optional: `prompt`, `system_prompt`, `mcp_servers` (inline: stdio
`{"type":"stdio","id":...,"command":[...]}` or http `{"type":"http","id":...,"url":...}`),
`skills` (inline `{"id":..., "files": {"SKILL.md": "<content>"}}`),
`enabled_builtin_tools` (subtractive allowlist: absent = all, `[]` = none),
`output_schema`.

```json
{"schema_version":"0.1","run_id":"demo","model":"anthropic/claude-haiku-4-5","prompt":"Say hi."}
```

## Reading a Trajectory

Ten v0.1 event types, every one with `source: avp://agent`: `run_requested`,
`agent_described`, `agent_started`, `agent_stopped`, `assistant_message`,
`tool_invoked`, `tool_returned`, `subagent_invoked`, `subagent_returned`,
`error_occurred`. A run opens `run_requested` → `agent_described` →
`agent_started` and closes `agent_stopped` (with a stop reason). Each
`assistant_message` is one model turn carrying `avp.content`, per-turn
`avp.usage`, and `avp.cost_usd`; totals are reduced from those deltas, not
published. Every event is a CloudEvents 1.0 envelope carrying OTel span ids
(`trace_id` / `span_id` / `parent_span_id`).

## Conventions

- `model` is always `origin/model`, never a bare model name.
- Don't invent supervisor→agent callbacks; runtime rules belong in a managed MCP
  server the agent calls, not a push channel.
- Import the wire types from `avp` (Python: `avp.commission` / `avp.trajectory` /
  `avp.descriptor`); never redefine them inline.
- Workspace provisioning, secret injection, and OS sandboxing are deployment
  concerns, outside AVP's scope.
