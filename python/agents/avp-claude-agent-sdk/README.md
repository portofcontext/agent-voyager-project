# avp-claude-agent-sdk — AVP agent for the Claude Agent SDK

This package wraps the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) (Claude Code as an SDK) so its runs are observable as AVP trajectories.

**Pattern: observer / translator.** This is structurally different from [`avp-anthropic`](../../sdks/avp-anthropic/), the SDK adapter for the raw Anthropic Messages API, which exposes a **driver**. The Claude Agent SDK owns its own agent loop. We can't insert ourselves as the loop owner. So `avp-claude-agent-sdk` instead **subscribes** to the SDK's lifecycle events and translates each into the corresponding AVP event.

## Why this is fully AVP-compliant

Under the v0.1 model, AVP draws a clear line:

- **Observability** — agent emits the event stream. Required.
- **Environment** — supervisor declares Commission (tools, MCP servers, subagents, skills, prompts). Optional but recommended.

There is **no mid-run bidirectional control** in v0.1 — no hooks reaching in, no synchronous supervisor decisions. The supervisor configures the environment; the agent operates within it; the agent emits.

This means observer-pattern integrations like `avp-claude-agent-sdk` are first-class AVP-compliant — the spec doesn't ask agents to do anything an observer pattern can't do.

| AVP feature | avp-claude-agent-sdk |
|---|---|
| `agent_started` / `agent_stopped` | ✅ emit at query open/close |
| `model_turn_started` / `_ended` | ✅ translated from SDK message stream |
| `tool_invoked` / `tool_returned` / `tool_failed` | ✅ translated from SDK tool messages |
| `text_emitted` | ✅ translated |
| `cost_recorded` | ✅ usage from each model message |
| MCP servers (`Commission.mcp_servers`) | ✅ refs resolved via the Resolver API, then translated into the SDK's `mcp_servers` slot; stdio and HTTP transports |

The TODOs marked `# TODO(claude-agent-sdk):` in `translator.py` are SDK-version-specific glue (which lifecycle events the SDK emits, what its tool-registration API looks like). Once filled in, this agent passes the conformance suite.

## Install

This package is part of the AVP uv workspace (rooted at [`python/`](../../) so the repo root stays language-agnostic). Bootstrap from the repo root:

```bash
make sync            # uv --directory python sync
```

You also need the Claude Code CLI (the `claude_agent_sdk` Python package shells
out to it; not pure Python):

```bash
npm install -g @anthropic-ai/claude-code
claude /login
```

Once published, the standalone install will be `pip install avp-claude-agent-sdk`.
Until then, work from a checkout of the workspace.

## Pattern

```python
from avp import Commission
from avp_claude_agent import ClaudeAgentTranslator

config = Commission(
    schema_version="0.1",
    run_id="my-run",
    model="claude-sonnet-4-6",
    prompt="Refactor the auth module.",
)

translator = ClaudeAgentTranslator(config, on_event=lambda ev: print(ev))
translator.run()
```

## CLI (stdio)

```bash
echo '<config json>' | avp-claude-agent-sdk
```

## SDK options pass-through (`extra_sdk_options`)

`ClaudeAgentTranslator` accepts an `extra_sdk_options: dict[str, Any]` kwarg that's merged into `ClaudeAgentOptions` before the SDK starts. This is the escape hatch for SDK-specific concerns AVP intentionally doesn't put on the wire (per [`spec/v0.1/README.md` §6](../../../spec/v0.1/README.md): deployment-layer config is out of scope for the wire format).

The most common knobs:

```python
translator = ClaudeAgentTranslator(
    commission,
    on_event=on_event,
    extra_sdk_options={
        # Non-interactive runs need this — without it, the CLI auto-rejects
        # tool calls before execution. PreToolUse fires (model wanted to
        # call), PostToolUse never does, and `tool_returned` won't appear
        # on the AVP wire because the tool literally never ran.
        "permission_mode": "bypassPermissions",
        # Scopes the CLI's filesystem access. Required if you want the
        # agent to read/write files outside its default cwd — which is
        # typical when staging a workspace per run.
        "cwd": "/path/to/workspace",
        # Additional readable directories beyond cwd.
        "add_dirs": ["/tmp/staging", "/etc/skills"],
    },
)
```

Commission-derived kwargs (`tools` / `system_prompt` / `model` / `agents` / `mcp_servers`) take precedence — `extra_sdk_options` cannot override the AVP wire shape. It's strictly a way to pass SDK behavior knobs (permissions, filesystem scope, retries, etc.) that don't belong on the trajectory.

If you find yourself reaching for `extra_sdk_options` for something that *should* be portable across AVP agents (cost caps, output schemas, allowlists), that's a signal it belongs on Commission instead — file an issue.

## Known SDK quirks (observed empirically, not yet resolved)

The translator wraps a moving target — the `claude_agent_sdk` Python package
plus the `claude` CLI binary it shells out to. These behaviors surfaced
running `examples/03_claude_code_audited.py` end-to-end and are worth
flagging for whoever picks up the next round of translator work:

### 1. Cumulative usage drops without a PreCompact / SubagentStart signal

The translator hooks `PreCompact` and `SubagentStart` to anticipate
SDK-side cumulative-counter resets. In practice we observe additional
cumulative drops that fire neither hook — usually within a single "turn"
between multiple AssistantMessages. Per [`spec/v0.1/trajectory.md` §3.3](../../../spec/v0.1/trajectory.md#33-cost--token-accounting-rules-normative)
reset handling is a translator implementation detail; the translator
adopts the new cumulative as a fresh baseline so subsequent deltas
remain computable. The supervisor treats reduced totals as a lower bound.

What's open: identify the SDK lifecycle event (if any) that signals these
internal resets so we can hook baseline-reset explicitly. Candidates
worth checking: `Notification` hook, `PostToolUseFailure`, undocumented
internal CLI events.

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
the first user-meaningful turn. Supervisors monitoring cost on this agent
should account for this baseline. The driver-pattern agents
(agents built on `avp-anthropic`) don't have this overhead.
