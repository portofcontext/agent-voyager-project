# AGENTS.md — working with the Agent Voyager Project (AVP)

This file orients a coding agent dropped into AVP work. AVP is an open standard
for the agent-execution case: a **supervisor** sends an **agent** a JSON
**Commission**, the agent runs and streams back a **Trajectory** of events, and
the supervisor only observes (there is no mid-run push channel).

## What you'll be asked to do

Three jobs, by intent:

1. **Author a Commission** (the supervisor side): produce the run config below.
2. **Read a trajectory**: answer questions from a stream of events the agent emitted.
3. **Drive the `avp` CLI**: scaffold and run evals that compare commissions.

## Commission: the shape to produce

A Commission is JSON. Required: `schema_version` (`"0.1"`), `run_id`, and `model`
as a canonical `origin/model` slug (`anthropic/claude-haiku-4-5`, `openai/gpt-4o`).
Common optional fields:

- `prompt`, `system_prompt` — what the agent runs.
- `mcp_servers` — inline servers the agent dials. stdio:
  `{"type":"stdio","id":"X","command":[...]}`; http: `{"type":"http","id":"X","url":"..."}`.
- `skills` — inline `{"id":..., "files": {"SKILL.md": "<content>"}}` (files must contain "SKILL.md").
- `enabled_builtin_tools` — allowlist over the agent's built-ins (absent = all,
  `[]` = none). Same for `enabled_builtin_{mcp_servers,subagents,skills}`.
- `output_schema` — JSON Schema for structured output.

```json
{"schema_version":"0.1","run_id":"demo","model":"anthropic/claude-haiku-4-5","prompt":"Say hi."}
```

## Trajectory: the events you'll read

Ten v0.1 event types, every one with `source = avp://agent`: `run_requested`,
`agent_described`, `agent_started`, `agent_stopped`, `assistant_message`,
`tool_invoked`, `tool_returned`, `subagent_invoked`, `subagent_returned`,
`error_occurred`. A run opens `run_requested` → `agent_described` →
`agent_started` and closes `agent_stopped` (with a stop reason). Each
`assistant_message` is one model turn carrying `avp.content`, per-turn
`avp.usage`, and `avp.cost_usd`. Totals are not published; sum the per-turn deltas.

It's CloudEvents 1.0 envelopes carrying OpenTelemetry span ids
(`trace_id`/`span_id`/`parent_span_id`); attributes live in AVP's `avp.*`
namespace; refs use JSON-RPC 2.0; tools are MCP-shaped; skills are Agent Skills.

## The `avp` CLI

- `avp init [benchmark]` — scaffold a `<name>.eval.json` and seed its commissions.
- `avp eval run <config>.eval.json` — run + print a ranked board.
- `avp cm create` / `avp cm check <id|file>` — build / validate a Commission.
- `avp agent install <name>` — install goose or claude-code.

An eval config is `{name, agents, dataset, scorer, commissions}`. `dataset.source`
is `inline` | `file` | `huggingface`. `scorer.name` is `exact-match` |
`structural-match` | `structural-fidelity` | `llm-judge`. `commissions` are ids in
your library; each carries its own `model`.

To run **ParseBench** (PDF table extraction): a `huggingface` dataset
(`llamaindex/ParseBench`), the `structural-fidelity` scorer, and a commission that
wires a PDF-vision MCP server (stdio `pdf-vision`) plus `shell`/`write`/`edit`.

## Conventions

- `model` is always `origin/model`, never a bare model name.
- Don't invent supervisor→agent callbacks; put runtime rules in a managed MCP
  server the agent calls.
- Workspace, secrets, and sandboxing are deployment concerns, outside AVP.
