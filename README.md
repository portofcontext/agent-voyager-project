# Agent Execution Protocol (AEP)

> **Status:** Draft v0.1

AEP draws one line, between two roles, and ships a wire format across that line.

- **Supervisor** — declares the agent's complete environment (boundary, tools, skills, verifiers, prompts) in a Config sent at startup. Then observes the trajectory and replies to any agent-initiated RPC tool calls — never reaches in unilaterally.
- **Runner** — runs the agent inside the declared environment and emits a stream of facts.

**Two unidirectional flows.** Control flows down at setup; observation flows up during the run. No mid-run bidirectional negotiation. The agent's bounded context is intact because its environment was fully declared up front.

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
  "allowed_tools": ["lookup_user", "bash"],
  "verifiers": [
    { "name": "tests-pass", "trigger": "after_each_turn", "source": { "shell": "cargo test --quiet" }, "on_failure": "halt" }
  ],
  "boundary":      { "max_cost_usd": 2.0, "max_steps": 30, "max_tokens": 150000 },

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
| Environment | `allowed_tools` | Optional allowlist. When present, the runner exposes ONLY these names — both `Config.tools` and runner built-ins are filtered through it. |
| Environment | `verifiers` | Deterministic Boolean checks the agent runs at declared triggers. Reactions (`halt` / `inject_correction` / `continue`) declared per verifier. |
| Environment | `boundary` | Hard limits the agent enforces on itself. Strict-greater; runs may overshoot cost/tokens by one final turn, but `max_steps: N` runs EXACTLY N turns. |
| Environment | `output_schema` | Structured output contract; validated on `agent_stopped`. |
| Runner | `prompt` / `system_prompt` / `model` / `skills` | What the agent runs and how. |
| Metadata | `thread_id` / `tags` / `meta` | For correlation, filtering, ad-hoc context. |

`schema_version` MUST equal `"0.1"`. `run_id` MUST be unique per run. Full field reference is in [`SPEC.md`](spec/v0.1/SPEC.md).

---

## Spec

| | |
|---|---|
| Normative spec | [`spec/v0.1/SPEC.md`](spec/v0.1/SPEC.md) — RFC 2119 keywords, reference algorithm, conformance criteria |
| JSON Schemas | [`spec/v0.1/`](spec/v0.1/) — Draft 2020-12 |
| Conformance suite | [`conformance/v0.1/`](conformance/v0.1/) — language-agnostic test cases every SDK MUST pass |
| Contributor guide | [`CLAUDE.md`](CLAUDE.md) — the seams principle, test layers, decision tree |
| Visual manifesto | [`index.html`](index.html) |

---

## Python implementation

| Package | Purpose |
|---|---|
| [`python/aep/`](python/aep/) | Wire types, reference runner, conformance harness. Every other AEP package depends on this. |
| [`python/runners/aep-anthropic/`](python/runners/aep-anthropic/) | Driver-pattern runner over the Anthropic Messages API. Owns its loop. |
| [`python/runners/aep-claude-agent/`](python/runners/aep-claude-agent/) | Observer-pattern runner over the Claude Agent SDK. Translates the SDK's lifecycle to AEP. Fully compliant under the v0.1 model. |

---

## License

MIT
