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

You subscribe to the SDK's lifecycle (message stream, tool hooks, run-end signal) and translate each event to the corresponding AVP event. The Commission flows in by translating its fields (inline `mcp_servers`, `system_prompt`, `model`, the `enabled_builtin_*` allowlists) into the SDK's own configuration slots before the run starts.

**When to pick.** You're building a new agent on top of an agentic SDK whose loop is the reason you picked it. You want the SDK's behavior preserved and AVP layered on top without restructuring the run.

**What you trade.** Some wire-level rules are observable but not enforceable from outside the SDK (timing of certain lifecycle signals, the SDK's internal cumulative-usage accounting, when exactly a tool is *invoked* vs *prepared*). Expect SDK-version-specific workarounds. See `agents/avp-claude-agent-sdk/python/README.md` for what that looks like in practice.

**Composition.** `AVPClaudeSDKClient` is a drop-in `ClaudeSDKClient` subclass: it builds the SDK options from the Commission, emits the prelude, and tees each message through AVP emission.

```python
async with AVPClaudeSDKClient(commission=commission, sink=sink) as client:
    await client.query(commission.prompt)
    async for _message in client.receive_response():
        ...  # your existing message handling; AVP events are already on the wire
```

**Worked example.** `agents/avp-claude-agent-sdk/python/` — the whole package is this pattern. An OpenAI Agents SDK equivalent would follow the same shape: subscribe to the SDK's run lifecycle, translate each signal.

## Instrument your own loop

You own the `messages.create` / `chat.completions.create` loop. AVP slots in around it. You can adopt incrementally: start with observability, then add Commission honoring when the supervisor needs to drive run config.

### Phase 1 — drop in tracing

Wrap your existing SDK client. Every model call emits one `assistant_message` (carrying `avp.content`, `avp.usage`, and `avp.cost_usd`), and tool dispatches you bracket with `client.tool(...)` emit `tool_invoked` / `tool_returned`. Cost / token totals come from reducing the per-turn `assistant_message` deltas at the consumer. Your loop body is unchanged. The Commission is treated as a label: `run_id`, `model`, `prompt` get recorded, but supervisor-managed config doesn't apply yet.

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

**Worked examples.** `supervisors/simple-supervisor-example/examples/06_anthropic_traced_client.py` (Anthropic Messages API) and `07_claude_agent_traced_client.py` (Claude Agent SDK as a black box, observed from outside).

### Phase 2 — layer in Commission

Now the supervisor's Commission starts driving real configuration of the run: which built-in tools the model sees (`enabled_builtin_tools`), what MCP servers are wired (the inline `mcp_servers[]` entries the agent dials), and what skill content is injected into the system prompt (the inline `skills[]` entries). Managed assets carry their connection material on the Commission, so there is no resolver round-trip in this path.

You add: Commission-to-API helpers. The loop body itself doesn't change; what changes is what you pass into it.

**Composition.**

```python
# 1. Build per-API params from the Commission's inline assets.
tools = build_anthropic_tools(commission, builtins=my_local_tools)   # filtered by enabled_builtin_tools
system_prompt = commission.system_prompt or ""
for skill in commission.skills or []:
    system_prompt += "\n\n" + skill.content   # materialize inline skill content

# 2. Instrument the client; the loop body is unchanged.
with AnthropicTracedClient(anthropic.Anthropic(), commission=commission, on_event=on_event) as client:
    while ...:
        resp = client.messages.create(
            model=commission.model, system=system_prompt, messages=msgs, tools=tools, ...
        )
        # dispatch tools via `with client.tool(...): ...`
        if resp.stop_reason == "end_turn":
            client.converged()
            break
```

**Worked example.** `supervisors/simple-supervisor-example/examples/08_anthropic_external_loop_with_commission.py`.

## Conformance

Conformance is certified by driving a conforming agent's `run` entrypoint against a real model and matching the emitted trajectory: the cross-agent suite lives at `avp/core/conformance/src/avp_conformance/cases/v0.1/` and is driven by the `avp-conformance` CLI (`check --agent <manifest> --suite v0.1`). There is no shared reference-agent base class; each agent inlines its own loop, and the harness validates the trajectory both case-by-case and against universal span-tree invariants. `COVERAGE.md` in that directory maps what the suite covers and the deliberate gaps.

The reference agent at `supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py` is the worked "Instrument your own loop" example built on the `avp-anthropic` adapter; it is a teaching artifact, not a production integration path. For a product, one of the two paths above is what you want.

## How this maps to packaging

The packaging layer (what code lives in which package) is a separate axis covered in `CLAUDE.md` "Agents vs SDK adapters":

- **Agents** (`agents/`) own the loop. `avp-claude-agent-sdk` is a "Wrap an Agent SDK" agent; `avp-goose` is an in-process observer of Goose.
- **SDK adapters** (`sdks/`) translate one provider API to AVP and ship pieces (a per-turn translator, a traced client, Commission-to-API helpers) that the "Instrument your own loop" path composes directly. `avp-anthropic` is an adapter.

A reference agent built on an adapter (e.g. `_anthropic_reference_agent.py`) inlines its own loop over the adapter's per-turn translator; the wire-types binding ships no agent base class to inherit from.
