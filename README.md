# Agent Execution Protocol (AEP)

> **Status:** Draft (v0.1 model, internal version label `0.3`)

AEP draws one line, between two roles, and ships a wire format across that line.

- **Supervisor** — declares the agent's complete environment (boundary, tools, skills, observation sources, verifiers, prompts) in a Config sent at startup. Then observes the trajectory.
- **Runner** — runs the agent inside the declared environment and emits a stream of facts.

**Two unidirectional flows.** Control flows down at setup; observation flows up during the run. No mid-run bidirectional negotiation. The agent's bounded context is intact because its environment was fully declared up front.

---

## How it works

```
                                      agent's environment
                          (boundary, tools, skills, re_obs, verifiers, prompt)
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
3. **SupervisorMessage** — supervisor service → runner, RPC replies only (`tool_exec_resolved`, `re_observation_resolved`). The runner records each into the trajectory.

---

## Spec

| | |
|---|---|
| Normative spec | [`spec/v0.1/SPEC.md`](spec/v0.1/SPEC.md) — RFC 2119 keywords, reference algorithm, conformance criteria |
| JSON Schemas | [`spec/v0.1/`](spec/v0.1/) — Draft 2020-12 |
| Conformance suite | [`conformance/v0.1/`](conformance/v0.1/) — language-agnostic test cases every SDK MUST pass |
| Prose explainer | [`AGENT_EXECUTION_PROTOCOL.md`](AGENT_EXECUTION_PROTOCOL.md) |
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
