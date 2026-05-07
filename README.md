# Agent Execution Protocol (AEP)

> **Status:** Draft v0.1

AEP draws one line, between two roles, and ships a wire format across that line.

- **Supervisor** — declares the agent's complete environment (boundary, tools, skills, verifiers, prompts) in a Config sent at startup. Then observes the trajectory and replies to any agent-initiated RPC tool calls — never reaches in unilaterally.
- **Runner** — runs the agent inside the declared environment and emits a stream of facts.

**Two unidirectional flows.** Control flows down at setup; observation flows up during the run. No mid-run bidirectional negotiation. The agent's bounded context is intact because its environment was fully declared up front.

**Built on existing standards** AEP specializes
[CloudEvents 1.0](https://cloudevents.io/), [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
OTel spans, [JSON-RPC 2.0](https://www.jsonrpc.org/specification),
[MCP](https://modelcontextprotocol.io/), [Agent Skills](https://agentskills.io/specification),
and JSON Schema 2020-12 — the way MCP specialized JSON-RPC for LLM tools.
Every event is a CloudEvent. Every model turn carries OTel GenAI attributes.
Every tool call's RPC payload is JSON-RPC 2.0. Every tool descriptor is
MCP-compatible. AEP's own contribution is small and focused: verifiers,
boundary semantics, the no-mid-run-reach-in topology, and the
trajectory-as-source-of-truth contract. Read [`FOUNDATIONS.md`](FOUNDATIONS.md)
for the full mapping.

---

## How it works

```
                                      agent's environment
                          (boundary, tools, skills, verifiers, prompt)
                                              │
                                              ▼
   supervisor ──── Config (one-time, setup) ──▶ runner
                                              │
                                              ▼
                                        runs the agent
                                              │
                                              ▼
   supervisor ◀────────── events (continuous, run-end) ────── runner
```

The one runtime exception is **environmental services**: when the agent calls a Config-declared tool whose implementation is out-of-process (or fetches an observation from a supervisor-stood-up service), the agent issues an RPC and awaits a reply. The runner records the reply into the trajectory verbatim. This is agent-initiated — the supervisor pre-deployed the service, but at runtime there's no decision-making.

---

## What AEP defines

Three message classes:

1. **Config** — supervisor → runner, once at startup. Declares the agent's full environment.
2. **Events** — runner → supervisor, streamed throughout the run. The trajectory.
3. **SupervisorMessage** — supervisor service → runner, RPC replies only (`tool_exec_resolved`). The runner records each into the trajectory.

---

## A worked Config

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
  "allowed_tools": ["lookup_user", "bash"],
  "verifiers": [
    { "name": "tests-pass",       "trigger": "after_each_turn",  "source": { "shell": "cargo test --quiet" },   "on_failure": "halt" },
    { "name": "ask-before-deploy", "trigger": "pre_tool:deploy", "source": { "approval": { "prompt": "Deploy to prod?" } }, "on_failure": "halt", "timeout_ms": 60000 }
  ],
  "boundary":      { "max_cost_usd": 2.0, "max_steps": 30, "max_tokens": 150000, "max_duration_seconds": 600 },

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
| Environment | `mcp_servers` | Remote MCP servers (HTTP or stdio) the runner connects to natively. Their tools are dispatched by the MCP layer and tagged on the wire with `aep.tool.dispatch_target=mcp_server` + `aep.mcp_server_id`. HTTP `auth.token_env` is resolved at translation time so secrets never land on events. |
| Environment | `subagents` | Delegate agents the parent can invoke by name. Each carries its own `system_prompt` / `model` / `tools` / `skills` / `verifiers` / `boundary`. Routed through the `subagent_invoked` / `subagent_returned` lifecycle so nested runs observe as a span tree, not a flattened tool call. |
| Environment | `allowed_tools` | Optional allowlist over the model-facing surface (tools AND subagents). When present, the runner exposes ONLY these names. |
| Environment | `verifiers` | Deterministic Boolean checks the agent runs at declared triggers (`before_first_turn`, `after_each_turn`, `pre_tool:<name>`, `on_tool:<name>`, `at_end`). Both polarities (`on_failure` / `on_success`) take `halt` / `inject_correction` / `continue`. Sources can be `shell` (deterministic) or `approval` (human-in-the-loop via the `aep.approval_*` RPC pair). |
| Environment | `boundary` | Hard limits the agent enforces on itself. Strict-greater; runs may overshoot cost/tokens by one final turn, but `max_steps: N` runs EXACTLY N turns. `max_duration_seconds` caps wall-clock. |
| Environment | `output_schema` | Structured output contract; validated on `agent_stopped`. |
| Runner | `prompt` / `system_prompt` / `model` / `skills` | What the agent runs and how. |
| Metadata | `thread_id` / `tags` / `meta` | For correlation, filtering, ad-hoc context. |

`schema_version` MUST equal `"0.1"`. `run_id` MUST be unique per run. Full field reference is in [`SPEC.md`](spec/v0.1/SPEC.md).

---

## Spec

| | |
|---|---|
| Foundations | [`FOUNDATIONS.md`](FOUNDATIONS.md) — what AEP is built on (CloudEvents, OTel GenAI, OTel spans, JSON-RPC 2.0, MCP, Agent Skills, JSON Schema) and what it specializes |
| Normative spec | [`spec/v0.1/SPEC.md`](spec/v0.1/SPEC.md) — RFC 2119 keywords, reference algorithm, conformance criteria |
| JSON Schemas | [`spec/v0.1/`](spec/v0.1/) — Draft 2020-12 |
| Conformance suite | [`conformance/v0.1/`](conformance/v0.1/) — language-agnostic test cases every SDK MUST pass |
| Contributor guide | [`CLAUDE.md`](CLAUDE.md) — the seams principle, test layers, decision tree |
---

## Language bindings

Wire-type bindings for non-Python consumers, generated from the same JSON Schemas the Python types come from. Single chain: `python/aep/types.py` (Pydantic) → `spec/v0.1/*.schema.json` → bindings.

| Language | Path | Generator | Notes |
|---|---|---|---|
| Python | [`python/aep/`](python/aep/) | hand-written Pydantic (source) | The canonical surface; everything else derives from this. |
| Rust | [`rust/aep/`](rust/aep/) | [`cargo-typify`](https://github.com/oxidecomputer/typify) | `cargo build` clean; serde-derived types; `Event` discriminated union. |
| TypeScript | [`typescript/aep/`](typescript/aep/) | [`json-schema-to-typescript`](https://github.com/bcherny/json-schema-to-typescript) | Pure type-only package; discriminator-narrowing on `event.type`. |

`make bindings` regenerates Rust + TypeScript from the current schemas. `make check` includes a drift detector that fails CI if a schema changed and bindings weren't regenerated. Neither is published to a registry yet — vendor by git path until v0.1 stabilizes.

---

## Python implementation

| Package | Purpose |
|---|---|
| [`python/aep/`](python/aep/) | Wire types, conformance harness, and the two reference implementations: `AEPRunner` (owns the loop, for greenfield agents) and `AEPTracer` (instruments a loop the caller controls — `from aep import AEPTracer`, or `aep.tracer` for module-level helpers). Also ships `aep.runner.LocalTools` — a generic `ToolDriver` for in-process Python callables (`@tools.tool` decorator, return-value coercion, composition with a fallback driver). Cost/pricing lives in `aep.pricing`: a single bundled price table both runners load, with `aep.cost.source` (`computed` / `reported` / `unknown`) tagging provenance on the wire. Every other AEP package depends on this. |
| [`python/runners/aep-anthropic/`](python/runners/aep-anthropic/) | Driver-pattern runner over the Anthropic Messages API. Owns its loop. Native MCP via the API's HTTP connector (`build_anthropic_mcp_servers`); native parsing of Anthropic's `mcp_tool_use` / `web_search_tool_use` / `code_execution_tool_use` / `thinking` / `redacted_thinking` content blocks into AEP events. Also ships `AnthropicTracedClient` and `wrap_anthropic` — drop-in instrumentation for an Anthropic SDK loop you already have. |
| [`python/runners/aep-claude-agent/`](python/runners/aep-claude-agent/) | Observer-pattern runner over the Claude Agent SDK. Translates the SDK's lifecycle to AEP. Native MCP via the SDK's `mcp_servers` slot (HTTP and stdio). Bridge `to_sdk_mcp_server(local_tools)` lets one `LocalTools` registration work against either runner — pass `local_tools=...` to `ClaudeAgentTranslator` and the SDK dispatches the same callables. `cost.source="reported"` fires on the reconciliation event from `ResultMessage.total_cost_usd` (per-turn costs stay `computed`). Also ships `TracedClaudeSDKClient` and `traced_claude_sdk_client` — drop-in instrumentation for an existing `ClaudeSDKClient` loop. |

---

## Working in the repo

A `Makefile` exposes the orchestration commands:

```
make help            # list targets
make check           # format-check + lint + test + conformance (free, fast)
make smoke           # check + real-LLM tests + all 7 examples (real $$, ~$0.10–0.20)
make test-real-llm   # gated real-LLM tests for both runners
make examples        # all 7 examples; 03/07 self-skip without the `claude` CLI
```

`make smoke` is the pre-tag sanity check — runs the entire matrix end-to-end against real Anthropic models and the Claude Code CLI.

---

## License

MIT
