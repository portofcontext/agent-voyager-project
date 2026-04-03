# Agent Execution Protocol (AEP)

> **Status:** Draft — v0.1

AEP is an open, minimal contract for agent observability. 

Any framework or SDK can be AEP-compliant. 

Any orchestrator that speaks AEP can run any compliant agent without coupling to a specific SDK.

It's like OpenTelemetry applied to agent execution.

---

## How It Works

```
Supervisor            Runner
──────────            ──────
    │                  │
    │   Config ─────▶  │  prompt, model,
    │                  │  boundaries, hooks
    │                  │
    │  ◀── agent_start │
    │  ◀── tool_call   │
    │  ◀── tool_result │
    │  ◀── cost_update │
    │                  │
    │  ◀─ hook_request │  runner pauses
    │  verdict ──────▶ │  continue / stop / inject
    │                  │
    │  ◀── agent_stop  │
    │                  │
    ╰── NDJSON stdio ──╯
        or HTTP/SSE 
```

---

## What AEP Defines

**Three things:**

1. **Config** — what a supervisor passes to a runner at startup (prompt, model, boundaries, hooks)
2. **Event stream** — what the runner emits during execution
3. **Hooks** — bidirectional mid-run control: the runner pauses at declared trigger points, the supervisor inspects and responds with a verdict (continue, stop, or inject a message)

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
