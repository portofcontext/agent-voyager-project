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

```bash
pip install aep-claude-agent
```

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
