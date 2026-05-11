# Integration patterns

> How to wire an AI application (an agentic loop, a tool harness, a custom agent) to AVP. Two real-world starting points; pick the one that matches the codebase you already have.

Two questions decide the shape:

1. **Where does the agent loop live today?** Inside an agentic SDK you've adopted (Claude Agent SDK, OpenAI Agents SDK), or inside your own application code calling a raw chat/messages API directly?
2. **What do you want from AVP?** Trajectory events flowing on the wire (observability), supervisor-driven configuration of the run (Commission), or both? You can do them in either order, but most teams start with tracing.

This gives two adoption paths:

| Path | Loop lives in | Typical starting point |
|---|---|---|
| **Wrap an Agent SDK** | The agentic SDK | You're building a new agent on top of an SDK that already ships an agent loop. |
| **Instrument your own loop** | Your application | You need to control the agentic loop directly with a direct API integration and want to add AVP without rewriting it. |

## Wrap an Agent SDK

You subscribe to the SDK's lifecycle (message stream, tool hooks, run-end signal) and translate each event to the corresponding AVP event. The Commission flows in by translating Commission-managed assets (`mcp_servers`, `tools`, `subagents`, `system_prompt`) into the SDK's own configuration slots before the run starts; the resolver round-trips happen at the seam between the Commission and the SDK options builder.

**When to pick.** You're building a new agent on top of an agentic SDK whose loop is the reason you picked it. You want the SDK's behavior preserved and AVP layered on top without restructuring the run.

**What you trade.** Some wire-level rules are observable but not enforceable from outside the SDK (timing of certain lifecycle signals, the SDK's internal cumulative-usage accounting, when exactly a tool is *invoked* vs *prepared*). Expect SDK-version-specific workarounds. See `python/agents/avp-claude-agent/README.md` "Known SDK quirks" for what that looks like in practice.

**Composition.**

```python
translator = ClaudeAgentTranslator(commission, on_event=on_event)
translator.run()
```

The translator builds the SDK's options object from the Commission, opens the SDK's loop, subscribes to its events, and emits AVP events as it goes.

**Worked example.** `python/agents/avp-claude-agent/` — the whole package is this pattern. An OpenAI Agents SDK equivalent would follow the same shape: subscribe to the SDK's run lifecycle, translate each signal.

## Instrument your own loop

You own the `messages.create` / `chat.completions.create` loop. AVP slots in around it. You can adopt incrementally: start with observability, then add Commission honoring when the supervisor needs to drive run config.

### Phase 1 — drop in tracing

Wrap your existing SDK client. Every model call emits the per-turn AVP events (`model_turn_started` / `_ended`, `text_emitted`, `tool_invoked`, `cost_recorded`). Your loop body is unchanged. The Commission is treated as a label: `run_id`, `model`, `prompt` get recorded, but supervisor-managed config doesn't apply yet.

**Composition.**

```python
with AnthropicTracedClient(anthropic.Anthropic(), commission=commission, on_event=on_event) as client:
    while ...:
        resp = client.messages.create(model=commission.model, messages=msgs, tools=my_tools)
        # dispatch tools via `with client.tool(...): ...`
        if resp.stop_reason == "end_turn":
            client.converged()
            break
```

**Worked examples.** `python/supervisors/simple-supervisor-example/examples/06_anthropic_traced_client.py` (Anthropic Messages API) and `07_claude_agent_traced_client.py` (Claude Agent SDK as a black box, observed from outside).

### Phase 2 — layer in Commission

Now the supervisor's Commission starts driving real configuration of the run: which built-in tools the model sees (`enabled_builtin_tools`), what MCP servers are wired (`mcp_servers` refs resolved into the API connector shape), what skill bodies are injected into the system prompt (`skills` refs resolved into content), what subagents are available (`subagents` refs resolved at startup, spawned on demand).

You add: a resolver client, resolution loops over each managed kind, and Commission-to-API helpers. The loop body itself doesn't change; what changes is what you pass into it.

**Composition.**

```python
# 1. Resolve refs (HttpResolver in production; ScriptedResolver for tests).
resolver = http_resolver_from_env()
for entry in commission.skills or []:
    material = resolver.resolve(kind="skill", id=entry.id, ref=entry.ref)
    system_prompt += material["content"]
resolved_mcp = {
    entry.id: resolver.resolve(kind="mcp_server", id=entry.id, ref=entry.ref)
    for entry in commission.mcp_servers or []
}

# 2. Build per-API params from Commission + resolved material.
tools = build_anthropic_tools(commission, builtins=my_local_tools)
mcp_servers = build_anthropic_mcp_servers_from_resolved(resolved_mcp)

# 3. Tracer + wrapped client. The proxy emits AVP events for each turn.
with AVPTracer(commission, on_event=on_event) as tracer:
    client = wrap_anthropic(anthropic.Anthropic())
    while ...:
        resp = client.messages.create(
            model=commission.model, messages=msgs, tools=tools, mcp_servers=mcp_servers, ...
        )
        # dispatch tools via `with tracer.tool(...): ...`
```

**Worked example.** `python/supervisors/simple-supervisor-example/examples/08_anthropic_external_loop_with_commission.py`.

## Conformance internals

`AVPAgent` is the reference implementation: it owns the loop itself (a `while True:` in `python/avp/src/avp/agent/agent.py` that calls a `ModelDriver.step(history)` per turn, dispatches tool calls, accumulates history, handles stop reasons). It's what the conformance harness drives — `ScriptedModel` plugs into `AVPAgent` as a deterministic driver, and the cases under `conformance/v0.1/cases/` exercise every wire-level rule against it. The reference agent at `python/supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py` uses the same shape to demonstrate full Commission honoring end to end against real Claude.

This is **not a recommended integration path** for a product. It exists to certify the wire format and provide a known-correct reference for translator / driver implementers to compare against. If you're considering wiring `AVPAgent` into a production application, one of the two paths above is probably what you actually want.

## How this maps to packaging

The packaging layer (what code lives in which package) is a separate axis covered in `CLAUDE.md` "Agents vs SDK adapters":

- **Agents** (`python/agents/`) own the loop. `avp-claude-agent` is a "Wrap an Agent SDK" agent.
- **SDK adapters** (`python/sdks/`) translate one provider API to AVP and ship pieces — `ModelDriver`, `TracedClient`, Commission-to-API helpers — that the "Instrument your own loop" path composes directly. `avp-anthropic` is an adapter.

A reference agent built on an adapter (e.g. `_anthropic_reference_agent.py`) composes the adapter's `ModelDriver` with `AVPAgent`; that's a *Conformance internals* artifact, not a separate user-facing pattern.
