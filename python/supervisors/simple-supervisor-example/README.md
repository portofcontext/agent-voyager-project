# simple-supervisor-example

A worked example of an AEP v0.1 supervisor. Builds Configs from category profiles, spawns an AEP runner subprocess, observes the streamed trajectory, and surfaces the three classes of facts SPEC.md §10 calls out:

- **What the agent did** — model turns, tool calls
- **What the rules said** — verifier pass/fail
- **What the run cost** — cumulative cost / tokens / duration

Both runner SDKs are demonstrated:

| SDK | Pattern | What this example shows |
|---|---|---|
| `aep-anthropic` | Driver — owns the loop | Cost-bounded refactor, self-correcting verifier with `inject_correction` |
| `aep-claude-agent` | Observer — wraps Claude Agent SDK via hooks | Same Config wrapping a session that owns its own loop; `allowed_tools` + verifiers enforced from outside |

This is **not a production framework**. It's a stepping stone — proof that the wire format works end-to-end before going deep on a real (e.g. DDD-shaped) supervisor. Read the source top to bottom; it should fit in your head.

## Layout

```
src/simple_supervisor/
  profiles.py       # Profile dataclass + DEV_LOOSE / QUALITY_GUARDS / DDD_STRICT / COST_BOUNDED
  builder.py        # build_config(profile, overrides) -> Config
  runner.py         # run_subprocess(cmd, config) — pipes Config in, reads NDJSON out
  observability.py  # summarize(events) -> Summary;  render(summary) -> str
  cli.py            # `simple-supervisor list-profiles` / `show-config` / `examples`
examples/
  01_anthropic_cost_bounded.py
  02_anthropic_self_correcting.py
  03_claude_code_audited.py
  04_ddd_supervisor.py            # full DDD profile applied to a real toy domain
  04_ddd_domain/                  # the toy domain — Order, Customer, invariants
```

## Quickstart

The repo is a uv workspace — one sync from the root installs all four AEP packages editably and resolves cross-package deps to local sources (avoiding a PyPI name collision with an unrelated `aep` package).

```bash
cd /path/to/agent-execution-protocol
uv sync

# Show available profiles
uv run simple-supervisor list-profiles

# Render a Config without running anything
uv run simple-supervisor show-config --profile ddd-strict --prompt "Explain main.py"
```

If you'd rather not use uv, you can still install each package individually with pip — but you'll hit the PyPI collision unless you install the local `aep` first:

```bash
pip install -e python/aep \
            -e python/runners/aep-anthropic \
            -e python/runners/aep-claude-agent \
            -e python/supervisors/simple-supervisor-example
```

## What each example demonstrates

### 01 — Cost-bounded inspection (driver pattern)

Wires the `cost-bounded` profile (`max_cost_usd=$0.05`, `max_steps=3`, `allowed_tools=[read_file]`) at a Claude Haiku model. Spawns `aep-anthropic`, pipes Config, watches the trajectory.

What you'll see in the post-run summary:
- `agent_stopped reason="budget_exhausted"` if the agent overshoots, or `"converged"` if it finishes early
- `read_file: N call(s)` — the only tool the allowlist permitted
- The cost trajectory line-by-line as `cost_recorded` events stream in

### 02 — Self-correcting verifier (driver pattern)

Wires the `quality-guards` profile, which ships a `no-todos-in-writes` verifier on `on_tool:write_file` with `on_failure=inject_correction`. When the agent writes a file containing a `TODO`, the verifier fails, and the supervisor's correction message is injected as a user-role message before the next turn — the agent sees its own output failed a rule and self-corrects.

What you'll see:
- `verifier_evaluated` events with `passed: false`
- A subsequent `model_turn_started` where the agent reads the correction
- Final agent output that no longer contains the offending TODO

### 03 — Audited Claude Code session (observer pattern)

Wraps the Claude Agent SDK (Claude Code as an SDK) via `aep-claude-agent`'s translator. The supervisor builds the same Config and registers AEP-emitting hooks against the SDK's `PreToolUse` / `PostToolUse` / `Stop` events. From outside, it looks identical: same Profile-derived Config, same post-run summary, same three-class breakdown.

The point: the SDK owns the agent loop, but the supervisor still gates the surface (`allowed_tools`), monitors the trajectory, and runs verifiers. **No mid-run reach-in** — the hooks observe, the verifiers run before/after fixed lifecycle points, and the supervisor reads the trajectory from the bus.

This example uses a mock SDK by default (so it runs without `claude-agent-sdk` installed and without an API key). Set `USE_REAL_SDK=1` and install the SDK to drive against the real thing.

### 04 — DDD-strict supervisor over a toy domain (driver pattern)

The most complete example: a real `DDD_STRICT` profile compiling Domain-Driven Design concerns into AEP verifiers, applied to a hand-written DDD codebase at `examples/04_ddd_domain/` (Order aggregate, Customer aggregate, OrderLine + EmailAddress value objects, 20+ invariant tests).

The profile ships three verifiers, each compiling one DDD concern:

1. `domain-layer-purity` (on_tool:write_file, halt) — `grep` `domain/` for infrastructure imports. Domain MUST stay pure.
2. `aggregate-invariants` (after_each_turn, halt) — `python -m pytest tests/invariants/`. Invariants MUST hold on every state.
3. `no-anemic-suffixes-in-domain` (on_tool:write_file, inject_correction) — flags `*Manager.py` / `*Helper.py` / `*Util.py` in domain. Names MUST reflect business concepts.

The agent's task: extend `Order` with `apply_discount`, preserving the `total == sum(line subtotals)` invariant and adding a test. The naive way is to write an `OrderDiscountManager.py` — verifier 3 catches that and tells the agent to put the method on `Order` itself. If the math is wrong, verifier 2 catches the broken invariant and halts.

Read the toy domain first to see what DDD-correct code looks like, then read the profile to see how each concept maps to a verifier. That's the supervisor framework pattern compressed into one example.

## The supervisor's value-add (what AEP gives you "for free")

When you read the examples, notice how little supervisor code there is. AEP does the heavy lifting:

- **Config-down means no mid-run plumbing.** You hand the runner one JSON document. No callbacks, no hook registry, no inversion-of-control framework to learn.
- **The runner enforces `allowed_tools` and `boundary`.** The supervisor doesn't need to police what the agent did; it only needs to *observe what happened*.
- **Verifiers run inside the agent's loop.** The supervisor declares the rule; the agent enforces it; the trajectory records the outcome. The supervisor reads it after the fact.
- **The three trajectory classes separate cleanly.** The summary view in `observability.py` is ~30 lines because the wire format already segments by event type.

## Running the examples

The fastest path — uses `~/.anthropic-key` if it exists, otherwise `$ANTHROPIC_API_KEY`:

```bash
uv run simple-supervisor examples            # all four (~$0.15 total)
uv run simple-supervisor examples 01         # just example 01
uv run simple-supervisor examples 01 02 04   # any subset
```

Or invoke them directly:

```bash
export ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)"

# Real Haiku, ~$0.001 each (driver pattern)
uv run python python/supervisors/simple-supervisor-example/examples/01_anthropic_cost_bounded.py
uv run python python/supervisors/simple-supervisor-example/examples/02_anthropic_self_correcting.py

# Real claude-agent-sdk + Claude Code, ~$0.10 (observer pattern)
USE_REAL_SDK=1 uv run python python/supervisors/simple-supervisor-example/examples/03_claude_code_audited.py
```

Each example prints (a) the compiled Config, (b) live events line-by-line as they stream, then (c) a compact post-run summary in the three trajectory classes.

## Where this leaves you

If your real supervisor needs anything beyond what's here — a UI, a database of trajectories, profile composition by domain expert, programmatic triggers between runs — that's all *above* this layer. AEP defines the wire; this package shows the minimum code to participate; everything richer is your supervisor framework.

The deliberate omissions:
- No persistent storage (events live in memory per run).
- No multi-run orchestration.
- No HTTP transport (stdio only).
- No category/profile authoring tools — profiles live in code.
- No real DDD invariant compiler — just demo verifiers.

That's all yours to build.
