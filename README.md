<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/portofcontext/agent-voyage-protocol/main/assets/avp-white.png">
    <img src="https://raw.githubusercontent.com/portofcontext/agent-voyage-protocol/main/assets/avp.png" alt="AVP Logo" style="height: 128px">
  </picture>
  <h1>Agent Voyage Protocol (AVP)</h1>
</div>

> **Status:** Draft v0.1

AVP draws one line, between two roles, and ships a wire format across that line.

- **Supervisor** — issues a Commission at startup, then observes the trajectory the agent emits.
- **Agent** — runs inside the declared environment and emits a stream of facts.

**Built on existing standards.** AVP specializes
[CloudEvents 1.0](https://cloudevents.io/), [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
OTel spans, [JSON-RPC 2.0](https://www.jsonrpc.org/specification),
[MCP](https://modelcontextprotocol.io/), [Agent Skills](https://agentskills.io/specification),
and JSON Schema 2020-12 — the way MCP specialized JSON-RPC for LLM tools.
Every event is a CloudEvent. Every model turn carries OTel GenAI
attributes. AVP's own contribution is small and focused: the
no-mid-run-reach-in topology, the agent self-description manifest, and
the trajectory-as-source-of-truth contract. Read
[`FOUNDATIONS.md`](FOUNDATIONS.md) for the full mapping.

---

## How it works

```
   supervisor  ──────── Commission ─────────▶  agent
                                                 │
                                                 │  runs the run,
                                                 │  emits events
                                                 ▼
   supervisor  ◀──────── trajectory ─────────  agent
```

The supervisor sends one Commission at startup describing the run's environment. The agent runs the loop and emits the trajectory: a stream of CloudEvents that opens with the run prelude and closes with `agent_stopped`. The supervisor never reaches in mid-run.

---

## What AVP defines

Two message classes:

1. **Commission** — supervisor → agent, once at startup.
2. **Events** — agent → supervisor, streamed throughout the run. The trajectory.

Plus a small **resolver protocol** (JSON-RPC 2.0) the agent calls against a supervisor-stood-up service to dereference managed-asset refs in the Commission. The agent dials it; nothing pushes back.

---

## A worked Commission

```jsonc
{
  "schema_version": "0.1",
  "run_id": "auth-refactor-20260502-abc123",

  "supervisor": { "name": "acme-engineering-supervisor", "version": "2.4.1" },

  "mcp_servers": [
    { "id": "github", "ref": { "vault": "prod", "key": "gh-mcp-v2" } }
  ],
  "skills": [
    { "id": "style-guide",     "ref": "sha256:abc..." },
    { "id": "domain-glossary", "ref": { "vault": "prod", "key": "skill-glossary-v2" } }
  ],
  "subagents": [
    { "id": "researcher", "ref": "sk_subagent_abc123" }
  ],

  "prompt":        "Refactor the auth module to use JWT.",
  "system_prompt": "You are a senior Rust developer.",
  "model":         "claude-sonnet-4-6",

  "thread_id":     "session-xyz",
  "tags":          ["auth", "refactor"],
  "meta":          { "environment": "dev", "triggered_by": "ci" }
}
```

`schema_version` MUST equal `"0.1"`. `run_id` MUST be unique per run. Optional `enabled_builtin_tools` / `enabled_builtin_subagents` / `enabled_builtin_skills` allow-lists scope which agent built-ins (from the manifest below) the model sees this run; absent = all. Full field reference is in [`SPEC.md`](spec/v0.1/SPEC.md).

---

## A worked manifest

The agent's self-description. This payload rides on `agent_described.data["avp.manifest"]` at run-time for pre-flight introspection.

```jsonc
{
  "agent_name":       "avp-claude-agent",
  "agent_version":    "0.1.0",
  "avp_spec_version": "0.1",
  "default_model":    null,
  "supported_models": ["claude-*"],

  "built_in_tools": [
    { "name": "Read",         "avp.dispatch_target": "local" },
    { "name": "Write",        "avp.dispatch_target": "local" },
    { "name": "Edit",         "avp.dispatch_target": "local" },
    { "name": "Glob",         "avp.dispatch_target": "local" },
    { "name": "Grep",         "avp.dispatch_target": "local" },
    { "name": "Bash",         "avp.dispatch_target": "local" },
    { "name": "WebFetch",     "avp.dispatch_target": "local" },
    { "name": "WebSearch",    "avp.dispatch_target": "local" },
    { "name": "Task",         "avp.dispatch_target": "local" },
    { "name": "TodoWrite",    "avp.dispatch_target": "local" },
    { "name": "NotebookEdit", "avp.dispatch_target": "local" }
  ],

  "built_in_subagents": [
    { "name": "general-purpose", "avp.agent_type": "general-purpose" }
  ],

  "built_in_skills": null,

  "capabilities": [
    "mcp", "subagents", "skills", "skills:progressive",
    "thinking", "filesystem-skills", "filesystem-subagents"
  ]
}
```

---

## Spec

| | |
|---|---|
| Foundations | [`FOUNDATIONS.md`](FOUNDATIONS.md) — what AVP is built on (CloudEvents, OTel GenAI, OTel spans, JSON-RPC 2.0, MCP, Agent Skills, JSON Schema) and what it specializes |
| Normative spec | [`spec/v0.1/SPEC.md`](spec/v0.1/SPEC.md) — RFC 2119 keywords, reference algorithm, conformance criteria |
| JSON Schemas | [`spec/v0.1/`](spec/v0.1/) — Draft 2020-12 |
| Conformance suite | [`conformance/v0.1/`](conformance/v0.1/) — language-agnostic test cases every SDK MUST pass |
---

## Language bindings

Wire-type bindings for non-Python consumers, generated from the same JSON Schemas the Python types come from. Single chain: `python/avp/types.py` (Pydantic) → `spec/v0.1/*.schema.json` → bindings.

| Language | Path | Generator | Notes |
|---|---|---|---|
| Python | [`python/avp/`](python/avp/) | hand-written Pydantic (source) | The canonical surface; everything else derives from this. |
| Rust | [`rust/avp/`](rust/avp/) | [`cargo-typify`](https://github.com/oxidecomputer/typify) | `cargo build` clean; serde-derived types; `Event` discriminated union. |
| TypeScript | [`typescript/avp/`](typescript/avp/) | [`json-schema-to-typescript`](https://github.com/bcherny/json-schema-to-typescript) | Pure type-only package; discriminator-narrowing on `event.type`. |

`make bindings` regenerates Rust + TypeScript from the current schemas. `make check` includes a drift detector that fails CI if a schema changed and bindings weren't regenerated. Neither is published to a registry yet — vendor by git path until v0.1 stabilizes.

---

## Python implementation

| Package | Purpose |
|---|---|
| [`python/avp/`](python/avp/) | Wire types, conformance harness, and the two reference implementations: `AVPAgent` (owns the loop, for greenfield agents) and `AVPTracer` (instruments a loop the caller controls — `from avp import AVPTracer`, or `avp.tracer` for module-level helpers). Also ships `avp.agent.LocalTools` — a generic `ToolDriver` for in-process Python callables (`@tools.tool` decorator, return-value coercion, composition with a fallback driver). Cost/pricing lives in `avp.pricing`: a single bundled price table both agents load, with `avp.cost.source` (`computed` / `reported` / `unknown`) tagging provenance on the wire. Every other AVP package depends on this. |
| [`python/agents/avp-anthropic/`](python/agents/avp-anthropic/) | Driver-pattern agent over the Anthropic Messages API. Owns its loop. Native MCP via the API's HTTP connector (`build_anthropic_mcp_servers`); native parsing of Anthropic's `mcp_tool_use` / `web_search_tool_use` / `code_execution_tool_use` / `thinking` / `redacted_thinking` content blocks into AVP events. Also ships `AnthropicTracedClient` and `wrap_anthropic` — drop-in instrumentation for an Anthropic SDK loop you already have. |
| [`python/agents/avp-claude-agent/`](python/agents/avp-claude-agent/) | Observer-pattern agent over the Claude Agent SDK. Translates the SDK's lifecycle to AVP. Native MCP via the SDK's `mcp_servers` slot (HTTP and stdio). Bridge `to_sdk_mcp_server(local_tools)` lets one `LocalTools` registration work against either agent — pass `local_tools=...` to `ClaudeAgentTranslator` and the SDK dispatches the same callables. `cost.source="reported"` fires on the reconciliation event from `ResultMessage.total_cost_usd` (per-turn costs stay `computed`). Also ships `TracedClaudeSDKClient` and `traced_claude_sdk_client` — drop-in instrumentation for an existing `ClaudeSDKClient` loop. |

---

## Working in the repo

A `Makefile` exposes the orchestration commands:

```
make help            # list targets
make check           # format-check + lint + test + conformance (free, fast)
make smoke           # check + real-LLM tests + all 7 examples (real $$, ~$0.10–0.20)
make test-real-llm   # gated real-LLM tests for both agents
make examples        # all 7 examples; 03/07 self-skip without the `claude` CLI
```

`make smoke` is the pre-tag sanity check — runs the entire matrix end-to-end against real Anthropic models and the Claude Code CLI.
