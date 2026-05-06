# aep-claude-agent — AEP runner for the Claude Agent SDK

This package wraps the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) (Claude Code as an SDK) so its runs are observable as AEP trajectories.

**Pattern: observer / translator.** This is structurally different from [`aep-anthropic`](../aep-anthropic/), which uses the **driver** pattern. The Claude Agent SDK owns its own agent loop. We can't insert ourselves as the loop owner. So `aep-claude-agent` instead **subscribes** to the SDK's lifecycle events and translates each into the corresponding AEP event.

## Why this is fully AEP-compliant

Under the v0.1 model, AEP draws a clear line:

- **Observability** — runner emits the event stream. Required.
- **Environment** — supervisor declares Config (boundary, tools, skills, verifiers). Optional but recommended.

There is **no mid-run bidirectional control** in v0.1 — no hooks reaching in, no synchronous supervisor decisions. The supervisor configures the environment; the agent operates within it; the runner emits.

This means observer-pattern integrations like `aep-claude-agent` are first-class AEP-compliant — the spec doesn't ask runners to do anything an observer pattern can't do.

| AEP feature | aep-claude-agent |
|---|---|
| `agent_started` / `agent_stopped` | ✅ emit at query open/close |
| `model_turn_started` / `_ended` | ✅ translated from SDK message stream |
| `tool_invoked` / `tool_returned` / `tool_failed` | ✅ translated from SDK tool messages |
| `text_emitted` | ✅ translated |
| `cost_recorded` | ✅ usage from each model message |
| Boundary (cost / tokens / steps, strict-greater) | ✅ runner tallies post-turn and stops the iterator |
| Verifiers (`verifier_evaluated`, on_failure: halt/inject_correction/continue) | ✅ runner runs declared shell verifiers; agent handles on_failure locally |
| Tool exec RPC (supervisor-stood-up tool service) | ✅ register the RPC tool as a Python callable in the SDK; on call, route via `tool_exec_request`/`tool_exec_resolved` |

The TODOs marked `# TODO(claude-agent-sdk):` in `translator.py` are SDK-version-specific glue (which lifecycle events the SDK emits, what its tool-registration API looks like). Once filled in, this runner passes the conformance suite.

## Install

This package is part of the AEP uv workspace; bootstrap from the repo root:

```bash
uv sync
```

You also need the Claude Code CLI (the `claude_agent_sdk` Python package shells
out to it; not pure Python):

```bash
npm install -g @anthropic-ai/claude-code
claude /login
```

Once published, the standalone install will be `pip install aep-claude-agent`.
Until then, work from a checkout of the workspace.

## Pattern

```python
from aep import Config
from aep_claude_agent import ClaudeAgentTranslator

config = Config(
    schema_version="0.1",
    run_id="my-run",
    model="claude-sonnet-4-6",
    prompt="Refactor the auth module.",
    verifiers=[{"name": "tests-pass", "trigger": "after_each_turn",
                "source": {"shell": "cargo test"}, "on_failure": "halt"}],
)

translator = ClaudeAgentTranslator(config, on_event=lambda ev: print(ev))
translator.run()
```

## CLI (stdio)

```bash
echo '<config json>' | aep-claude-agent
```

## Known SDK quirks (observed empirically, not yet resolved)

The translator wraps a moving target — the `claude_agent_sdk` Python package
plus the `claude` CLI binary it shells out to. These behaviors surfaced
running `examples/03_claude_code_audited.py` end-to-end and are worth
flagging for whoever picks up the next round of translator work:

### 1. Cumulative usage drops without a PreCompact / SubagentStart signal

The translator hooks `PreCompact` and `SubagentStart` to anticipate
SDK-side cumulative-counter resets gracefully (see
`_on_baseline_reset_hook`). In practice we observe additional cumulative
drops that fire neither hook — usually within a single "turn" between
multiple AssistantMessages. The translator handles these correctly per
SPEC.md §9.4: emits `error_occurred` with `code: "accounting_reset"` and
adopts the new cumulative as a fresh baseline so subsequent deltas are
still computable.

What's open: identify the SDK lifecycle event (if any) that signals these
internal resets so we can convert the error into a graceful baseline-reset
hook subscription. Candidates worth checking: `Notification` hook,
`PostToolUseFailure`, undocumented internal CLI events. If no signal
exists, current behavior is the correct end state — the trajectory tells
the supervisor "treat totals as a lower bound" rather than silently
swallowing usage.

### 2. Duplicate `PreToolUse` for a single tool dispatch

In real runs we observe two `tool_invoked` events for one tool execution
(e.g., `Read` fires PreToolUse twice before the single PostToolUse +
ToolReturned pair). Most likely the SDK fires PreToolUse once for permission
check and again at actual execution.

What's open: dedupe on `tool_use_id` if both hook fires carry the same id —
emit `tool_invoked` only on the first fire per id. If they carry different
ids, the SDK is doing two genuine invocations and the trajectory is
correctly recording both. Investigation needed before we change behavior;
the current "emit both" path is overcounting-but-faithful, which is the
safer default until the cause is confirmed.

### 3. Heavy session bootstrap

Claude Code's first turn loads a lot of context (CLAUDE.md files, skill
definitions, system prompt) — typically $0.05–$0.10 even on Haiku before
the first user-meaningful turn. Supervisors setting `Config.boundary.max_cost_usd`
against this runner should account for this baseline. The driver-pattern
runners (`aep-anthropic`) don't have this overhead.
