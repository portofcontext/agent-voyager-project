# simple-supervisor-example

A worked example of an AVP v0.1 supervisor. Builds Commissions from category profiles, runs them against an AVP agent, observes the streamed trajectory, and surfaces the trajectory classes SPEC.md §10 calls out:

- **What the agent did** — model turns, tool calls, subagent invocations
- **What the run cost** — cumulative cost / tokens / duration

Both agent SDKs are demonstrated:

| SDK | Pattern | What this example shows |
|---|---|---|
| `avp-anthropic` | Driver — owns the loop | Cost-tracked refactor, subagent delegation, drop-in `AnthropicTracedClient` instrumentation |
| `avp-claude-agent` | Observer — wraps Claude Agent SDK | Same Commission wrapping a session that owns its own loop; trajectory observable from outside |

This is **not a production framework**. It's a stepping stone — proof that the wire format works end-to-end. Read the source top to bottom; it should fit in your head.

## Layout

```
src/simple_supervisor/
  profiles.py       # Profile dataclass + DEV_LOOSE / COST_BOUNDED
  builder.py        # build_commission(profile, overrides) -> Commission
  agent.py          # run_subprocess(cmd, commission) — pipes Commission in, reads NDJSON out
  observability.py  # summarize(events) -> Summary; render(summary) -> str
  cli.py            # `simple-supervisor list-profiles` / `show-commission` / `examples`
examples/
  01_anthropic_cost_bounded.py
  03_claude_code_audited.py
  05_anthropic_subagent_delegation.py
  06_anthropic_traced_client.py
  07_claude_agent_traced_client.py
```

## Quickstart

The repo is a uv workspace — `uv sync` from the root installs all AVP
packages editably and resolves cross-package deps to local sources. Use `uv` for everything:

```bash
cd /path/to/agent-execution-protocol
uv sync

# Show available profiles
uv run simple-supervisor list-profiles

# Render a Commission without running anything
uv run simple-supervisor show-commission --profile cost-bounded --prompt "Explain main.py"

# Run the examples end-to-end (uses ~/.anthropic-key or $ANTHROPIC_API_KEY)
uv run simple-supervisor examples
```

## What each example demonstrates

### 01 — Read-only inspection (driver pattern)

Wires the `cost-bounded` profile (`exposed=["read_file"]`) at a Claude Haiku model. Runs `avp-anthropic`, observes the trajectory.

What you'll see in the post-run summary:
- `agent_stopped reason="converged"` once the agent finishes
- `read_file: N call(s)` — the only tool the allowlist permitted
- The cost trajectory line-by-line as `cost_recorded` events stream in

### 03 — Audited Claude Code session (observer pattern)

Wraps the Claude Agent SDK (Claude Code as an SDK) via `avp-claude-agent`'s translator. The supervisor builds a Commission and the translator emits AVP events as the SDK runs. Same Profile-derived Commission, same post-run summary.

The point: the SDK owns the agent loop, but the supervisor still declares the surface (`exposed`, `mcp_servers`) and reads the trajectory from the bus. **No mid-run reach-in** — the supervisor sets up environment in Commission and observes events.

This example uses a mock SDK by default (so it runs without `claude-agent-sdk` installed and without an API key). Set `USE_REAL_SDK=1` and install the SDK to drive against the real thing.

### 05 — Subagent delegation (driver pattern)

Wires a Commission that declares a `Subagent` the parent agent can invoke by name. The parent dispatches a question to the subagent; the subagent runs its own model loop; both lifecycles are visible on the trajectory as a span tree (parent's `subagent_invoked` / `subagent_returned` bracketing the child's `model_turn_*` events).

### 06 — Traced Anthropic client (drop-in instrumentation)

Wraps a plain Anthropic SDK loop with `AnthropicTracedClient` / `wrap_anthropic`. The caller keeps their existing loop; the wrapper emits AVP events transparently. Useful when you can't switch to `AVPAgent` but still want trajectory observability.

### 07 — Traced Claude Agent SDK client

Same drop-in pattern, but for `ClaudeSDKClient`. `traced_claude_sdk_client` produces a context manager that emits AVP events as the wrapped client runs.

## The supervisor's value-add (what AVP gives you "for free")

When you read the examples, notice how little supervisor code there is. AVP does the heavy lifting:

- **Commission-down means no mid-run plumbing.** You hand the agent one JSON document. No callbacks, no hook registry, no inversion-of-control framework to learn.
- **The agent enforces `exposed`.** The supervisor doesn't need to police what the agent did; it only needs to *observe what happened*.
- **The trajectory classes separate cleanly.** The summary view in `observability.py` is short because the wire format already segments by event type.

## Running the examples

The fastest path — uses `~/.anthropic-key` if it exists, otherwise `$ANTHROPIC_API_KEY`:

```bash
uv run simple-supervisor examples            # all five
uv run simple-supervisor examples 01         # just example 01
uv run simple-supervisor examples 01 03 05   # any subset
```

Or invoke them directly:

```bash
export ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)"

# Real Haiku, ~$0.001 each (driver pattern)
uv run python python/supervisors/simple-supervisor-example/examples/01_anthropic_cost_bounded.py

# Real claude-agent-sdk + Claude Code, ~$0.10 (observer pattern)
USE_REAL_SDK=1 uv run python python/supervisors/simple-supervisor-example/examples/03_claude_code_audited.py
```

Each example prints (a) the compiled Commission, (b) live events line-by-line as they stream, then (c) a compact post-run summary.

## Where this leaves you

If your real supervisor needs anything beyond what's here — a UI, a database of trajectories, profile composition by domain expert, programmatic triggers between runs — that's all *above* this layer. AVP defines the wire; this package shows the minimum code to participate; everything richer is your supervisor framework.

The deliberate omissions:
- No persistent storage (events live in memory per run).
- No multi-run orchestration.
- No HTTP transport (stdio only).
- No category/profile authoring tools — profiles live in code.
