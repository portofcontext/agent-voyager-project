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

**Worked example.** `agents/avp-claude-agent-sdk/python/` — the whole package is this pattern: SDK messages in, `Recorder` calls out. An OpenAI Agents SDK equivalent would follow the same shape: subscribe to the SDK's run lifecycle, translate each signal.

## Instrument your own loop

You own the `messages.create` / `chat.completions.create` loop. AVP slots in around it: at the points that map to AVP events, you report to the binding's `Recorder`, which writes the wire events to an `EventSink`. The Recorder is a plain object you call; it imposes no base class or driver protocol, so your loop stays yours.

**When to pick.** You own the agentic loop with a direct API integration and want AVP without restructuring it.

**What you report.**

```python
rec = Recorder(sink, run_id=commission.run_id, provider="openai", prices=load_default_prices())
await rec.prelude(commission, descriptor)            # run_requested, agent_described
await rec.start(request_model=model, prompt=prompt, tools=tool_decls)   # agent_started
while not done:
    response = client.chat.completions.create(...)
    await rec.assistant(content_blocks, usage, model=model)   # assistant_message + tool_invoked
    for call in tool_calls:
        await rec.tool_result(call.id, run_tool(call))         # tool_returned
await rec.stop(StopReason.converged, output)          # agent_stopped
```

Tool calls go in `assistant`'s content as `tool_use` blocks; the Recorder derives `tool_invoked` from them, pairs each `tool_result` by id, numbers the steps, mints the span tree, buffers events behind their turn's `assistant_message`, and computes per-turn cost. You publish per-turn deltas, not cumulative snapshots. A streamed inference reports its chunks under one `turn_key`; usage that arrives after the content goes through `usage()`. The rules are pinned by the recorder vectors (`avp/core/conformance/src/avp_conformance/recorder/v0.1/`). The raw event types and sinks stay public if you'd rather emit by hand.

**Honoring the Commission.** Translate the Commission's fields into your API params before the run starts: `enabled_builtin_tools` filters the tool list you hand the model, inline `mcp_servers[]` are dialed by your MCP client, and inline `skills[]` content is materialized into the system prompt. Managed assets carry their connection material on the Commission, so everything you need is in hand before the first model turn.

**Starting point.** `agents/_template/<lang>/` is this shape with a stand-in harness: replace the harness, keep the rest.

## Conformance

Conformance is certified by driving a conforming agent's `run` entrypoint against a real model and matching the emitted trajectory: the cross-agent suite lives at `avp/core/conformance/src/avp_conformance/cases/v0.1/` and is driven by the `avp-conformance` CLI (`check --agent <manifest> --suite v0.1`). There is no shared reference-agent base class; each agent inlines its own loop and reports to the binding's `Recorder`, which owns the ordering and span rules (pinned by the recorder vectors next to the cases). The harness validates the trajectory both case-by-case and against universal span-tree invariants. Cases pin a Claude model; `--model <origin>/<model>` runs the suite on any provider's, and a case whose `requires` names a surface the agent's descriptor doesn't declare (e.g. subagents) reports SKIP. `COVERAGE.md` in that directory maps what the suite covers and the deliberate gaps.

## How this maps to packaging

The packaging layer (what code lives in which package) is the agents-and-supervisors axis covered in `CLAUDE.md` "Agents and supervisors":

- **Agents** (`agents/`) own the loop and honor the `run --commission --out` contract. `avp-claude-agent-sdk` is a "Wrap an Agent SDK" agent; `avp-goose` is an in-process observer of Goose.
- **The local CLI** (`avp-cli/`, command `avp`) commissions agents and consumes their trajectories: it runs setups (Commission variants) over a dataset against the agents and ranks a board.
