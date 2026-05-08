<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/avp-white.png">
    <img src="assets/avp.png" alt="AVP Logo" style="height: 128px">
  </picture>
  <h1>Agent Voyage Protocol (AVP)</h1>
</div>

> **Status:** Draft v0.1

AVP draws one line, between two roles, and ships a wire format across that line.

- **Supervisor** — issues a Commission at startup declaring the full environment for the run (prompt, model, MCP servers, subagents, skills, the exposed name surface), then observes the trajectory the agent emits — never reaches in unilaterally.
- **Agent** — runs the agent inside the declared environment and emits a stream of facts.

**Two unidirectional flows.** Control flows down at setup; observation flows up during the run. No mid-run bidirectional negotiation. The agent's bounded context is intact because its environment was fully declared up front.

**Built on existing standards** AVP specializes
[CloudEvents 1.0](https://cloudevents.io/), [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
OTel spans, [JSON-RPC 2.0](https://www.jsonrpc.org/specification),
[MCP](https://modelcontextprotocol.io/), [Agent Skills](https://agentskills.io/specification),
and JSON Schema 2020-12 — the way MCP specialized JSON-RPC for LLM tools.
Every event is a CloudEvent. Every model turn carries OTel GenAI attributes.
Every tool call's RPC payload is JSON-RPC 2.0. Every tool descriptor is
MCP-compatible. AVP's own contribution is small and focused: the
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

A **Commission** carries `prompt`, `model`, `mcp_servers`, `subagents`, `skills`, and `exposed` (the exhaustive model-facing name surface, with fnmatch globs allowed) — sent once at startup. The **trajectory** is the stream of CloudEvents the agent emits as it runs; it opens with `run_requested` → `agent_described` (which publishes the agent's **manifest** — built-in tools, capabilities, version) → `agent_started`, and closes with `agent_stopped`.

The one runtime exception is **environmental services**: when the agent calls a Commission-declared tool whose implementation is out-of-process (or fetches an observation from a supervisor-stood-up service), the agent issues an RPC and awaits a reply. The agent records the reply into the trajectory verbatim. This is agent-initiated — the supervisor pre-deployed the service, but at runtime there's no decision-making.

---

## What AVP defines

Three message classes:

1. **Commission** — supervisor → agent, once at startup. Declares the agent's full environment.
2. **Events** — agent → supervisor, streamed throughout the run. The trajectory.
3. **SupervisorMessage** — supervisor service → agent, RPC replies only (`tool_exec_resolved`). The agent records each into the trajectory.

---

## A worked Commission

```jsonc
{
  "schema_version": "0.1",
  "run_id": "auth-refactor-20260502-abc123",

  "tools": [
    {
      "name": "lookup_user",
      "description": "Look up a user by email.",
      "input_schema": { "type": "object", "required": ["email"], "properties": { "email": { "type": "string" } } },
      "timeout_ms": 15000
    }
  ],
  "mcp_servers": [
    { "id": "github",  "transport": "http",  "url": "https://mcp.github.com/", "auth": { "type": "bearer", "token_env": "GH_MCP_TOKEN" } },
    { "id": "weather", "transport": "stdio", "command": ["npx"], "args": ["-y", "@example/weather-mcp"] }
  ],
  "exposed": ["lookup_user", "bash"],

  "prompt":        "Refactor the auth module to use JWT.",
  "system_prompt": "You are a senior Rust developer.",
  "model":         "claude-sonnet-4-6",
  "skills":        [ { "name": "style-guide", "source": "./skills/style-guide" } ],

  "thread_id":     "session-xyz",
  "tags":          ["auth", "refactor"],
  "meta":          { "environment": "dev", "triggered_by": "ci" }
}
```

| Plane | Field | Purpose |
|---|---|---|
| Environment | `tools` | RPC tools the agent can call. Routed through the `tool_exec_*` lifecycle. |
| Environment | `mcp_servers` | Remote MCP servers (HTTP or stdio) the agent connects to natively. Their tools are dispatched by the MCP layer and tagged on the wire with `avp.tool.dispatch_target=mcp_server` + `avp.mcp_server_id`. HTTP `auth.token_env` is resolved at translation time so secrets never land on events. |
| Environment | `subagents` | Delegate agents the parent can invoke by name. Each carries its own `system_prompt` / `model` / `skills`. Routed through the `subagent_invoked` / `subagent_returned` lifecycle so nested runs observe as a span tree, not a flattened tool call. |
| Environment | `exposed` | Required exhaustive list of names the model can invoke this run. Each entry resolves at startup against built-in tools, built-in subagents, Commission.subagents, and live MCP-server catalogs (post-handshake). Supports fnmatch globs (`mcp__github__*`); literals that resolve to nothing fail loud with `error_occurred(exposed_unresolved)`. |
| Environment | `output_schema` | Structured output contract; validated on `agent_stopped`. |
| Agent | `prompt` / `system_prompt` / `model` / `skills` | What the agent runs and how. |
| Metadata | `thread_id` / `tags` / `meta` | For correlation, filtering, ad-hoc context. |

`schema_version` MUST equal `"0.1"`. `run_id` MUST be unique per run. Full field reference is in [`SPEC.md`](spec/v0.1/SPEC.md).

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
