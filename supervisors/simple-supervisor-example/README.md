# simple-supervisor-example

A worked example of an AVP v0.1 supervisor. Builds Commissions from profiles, runs them against an AVP agent, observes the streamed trajectory, and surfaces the two trajectory fact-classes [`avp/core/spec/v0.1/trajectory.md`](../../avp/core/spec/v0.1/trajectory.md) calls out:

- **What the agent did**: turns (`assistant_message`), tool calls, subagent invocations.
- **What the run cost**: cost / tokens / duration, reduced from the per-turn `assistant_message` deltas.

Both AVP integration patterns are demonstrated:

| Integration | Pattern | What this example shows |
|---|---|---|
| `avp-anthropic` SDK adapter + a reference agent that inlines its own loop over it (`examples/_anthropic_reference_agent.py`) | Inline loop, spawned as a subprocess | Cost-bounded inspection, in-process subagent delegation, drop-in `AnthropicTracedClient` instrumentation |
| `avp-claude-agent-sdk` (wraps the Claude Agent SDK) | Observer, the SDK owns the loop | The same Commission against a session that owns its own loop; trajectory observed from outside |

This is **not a production framework**. It's a stepping stone, proof that the wire format works end to end. Read the source top to bottom; it should fit in your head.

## Layout

```
src/simple_supervisor/
  profiles.py       # Profile dataclass + DEV_LOOSE / READ_ONLY presets
  builder.py        # build_commission(run_id, prompt, profile, ...) -> Commission
  agent.py          # run_subprocess / stream_subprocess: pipe Commission in, read NDJSON out
  observability.py  # summarize(events) -> Summary; render(summary) -> str
  cli.py            # `simple-supervisor list-profiles` / `show-config` / `examples`
examples/
  _anthropic_reference_agent.py    # reference agent that inlines its own loop over the
                                   # avp-anthropic adapter (spawned by example 01; not numbered)
  01_anthropic_cost_bounded.py
  03_claude_code_audited.py
  05_anthropic_subagent_delegation.py
  06_anthropic_traced_client.py
  07_claude_agent_traced_client.py
  08_anthropic_external_loop_with_commission.py
```

## Quickstart

The repo is a multi-language workspace with the Python workspace root at the repo root. `make sync` from the repo root installs every Python package editably and resolves cross-package deps to local sources:

```bash
cd /path/to/agent-voyager-project
make sync

# Show available profiles
uv run simple-supervisor list-profiles

# Render a Commission without running anything
uv run simple-supervisor show-config --profile read-only --prompt "Explain main.py"

# Run the examples end to end (uses ~/.anthropic-key or $ANTHROPIC_API_KEY)
uv run simple-supervisor examples
```

## What each example demonstrates

### 01: Cost-bounded inspection (inline-loop agent, spawned)

Wires the `read-only` profile (`enabled_builtin_tools=["read_file"]`) at a Claude Haiku model and spawns the reference agent at `examples/_anthropic_reference_agent.py` (which inlines its own loop over the `avp-anthropic` adapter), streaming and observing the trajectory.

What you'll see in the post-run summary:
- `agent_stopped reason="converged"` once the agent finishes.
- `read_file: N call(s)`: the only built-in the allowlist permitted.
- The per-turn cost, reduced from the `assistant_message` deltas as they stream in.

### 03: Audited Claude Code session (observer pattern)

Drives the Claude Agent SDK (Claude Code) through `avp-claude-agent-sdk`'s `AVPClaudeSDKClient`. The supervisor builds a Commission; the client emits AVP events as the SDK runs. Same profile-derived Commission, same post-run summary.

The point: the SDK owns the agent loop, but the supervisor still declares the surface (`enabled_builtin_tools`, inline `mcp_servers`) in the Commission and reads the trajectory back. **No supervisor to agent push channel**: the supervisor sets up the environment in the Commission and observes. This example needs `claude-agent-sdk` installed and the `claude` CLI on PATH (plus an API key); it self-skips with a clear message if any are missing.

### 05: In-process subagent delegation (traced client)

The parent runs against Claude through `AnthropicTracedClient` and exposes a `summarize` tool. When the model calls it, the example delegates to a "summarizer" subagent (a focused second model call) inside `client.subagent(...)`, which brackets it with `subagent_invoked` / `subagent_returned` on the wire. v0.1 dropped the resolver-managed subagent path; this shows the in-process shape, which is what the wire records either way.

### 06: Traced Anthropic client (drop-in instrumentation)

Wraps a plain Anthropic SDK loop with `AnthropicTracedClient`. The caller keeps their existing loop; the wrapper emits one `assistant_message` per `messages.create`, plus `tool_invoked` / `tool_returned` for dispatches bracketed with `client.tool(...)`. Useful when you don't want to restructure your loop but still want trajectory observability.

### 07: Traced Claude Agent SDK client

The same drop-in idea for the Claude Agent SDK: `AVPClaudeSDKClient` is a drop-in `ClaudeSDKClient` subclass that emits AVP events across `query()` / `receive_response()` / `disconnect()`.

### 08: External loop + Commission

Phase 2 of "instrument your own loop": the Commission drives real run config (`enabled_builtin_tools` filters the catalog; inline `skills` content is prepended to the system prompt) while `AnthropicTracedClient` traces the loop you own.

## The supervisor's value-add (what AVP gives you "for free")

When you read the examples, notice how little supervisor code there is. AVP does the heavy lifting:

- **Commission-down means no mid-run plumbing.** You hand the agent one JSON document. No callbacks, no hook registry, no inversion-of-control framework to learn.
- **The agent enforces `enabled_builtin_*` allowlists.** The supervisor doesn't need to police what the agent did; it only needs to observe what happened.
- **The trajectory fact-classes separate cleanly.** The summary view in `observability.py` is short because the wire format already segments by event type, and totals reduce from the per-turn `assistant_message` deltas.

## Running the examples

The fastest path (uses `~/.anthropic-key` if it exists, otherwise `$ANTHROPIC_API_KEY`):

```bash
uv run simple-supervisor examples            # all of them
uv run simple-supervisor examples 01         # just example 01
uv run simple-supervisor examples 01 03 05   # any subset
```

Or invoke one directly (this is what the `make examples` target does):

```bash
export ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)"
uv run python supervisors/simple-supervisor-example/examples/01_anthropic_cost_bounded.py
```

Each example prints (a) the compiled Commission, (b) live events line by line as they stream, then (c) a compact post-run summary. The claude examples (03, 07) additionally need `claude-agent-sdk` and the `claude` CLI, and self-skip when those are absent.

## Where this leaves you

If your real supervisor needs anything beyond what's here (a UI, a database of trajectories, profile composition by a domain expert, programmatic triggers between runs), that's all *above* this layer. AVP defines the wire; this package shows the minimum code to participate; everything richer is your supervisor framework.

The deliberate omissions:
- No persistent storage (events live in memory per run).
- No multi-run orchestration.
- Only the stdio binding to the supervisor/agent pipe is wired here. AVP is transport-agnostic; real supervisors can carry Commissions and trajectories over HTTP, a message bus, in-process callbacks, or anything else that preserves the JSON shapes.
- No profile-authoring tools; profiles live in code.
```
