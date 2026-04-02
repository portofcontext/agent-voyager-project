# Agent Execution Protocol (AEP)

> **Status:** Draft — v0.1

AEP is an open, minimal contract for agent observability. Any agent runner — regardless of SDK, model, or framework — can be AEP-compliant. Any orchestrator that speaks AEP can run any compliant agent without coupling to a specific SDK.

Think of it as what OpenTelemetry is to distributed tracing, applied to agent execution.

---

## What AEP Defines

**Two things only:**

1. **Config** — what an orchestrator passes to a runner at startup (NDJSON over stdin)
2. **Event stream** — what the runner emits during execution (NDJSON over stdout)

Transport: NDJSON over stdio (local subprocess) or HTTP/SSE (remote). Identical schema.

---

## Compliance

A runner is AEP-compliant if it:

1. Reads an AEP config JSON from stdin before starting
2. Emits `agent_start` as the first line to stdout
3. Emits `tool_call` before each tool invocation and `tool_result` after
4. Emits `cost_update` at least once per turn
5. Emits `agent_stop` as the last line to stdout
6. All output is valid NDJSON (one JSON object per line)
7. Flushes stdout after each line

---

## SDKs

| Language | Package | Path |
|---|---|---|
| Python | `agent-execution-protocol` | [python/agent-execution-protocol](python/agent-execution-protocol/) |

---

## Spec

Full event and config reference: [AGENT_EXECUTION_PROTOCOL.md](AGENT_EXECUTION_PROTOCOL.md)

Or read the [visual manifesto](index.html).

---

## License

MIT
