# avp-claude-agent — AVP agent for the Claude Agent SDK

This package wraps the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) (Claude Code as an SDK) so its runs are observable as AVP trajectories.

**Pattern: observer / translator.** `avp-claude-agent` **subscribes** to the SDK's lifecycle events and translates each into the corresponding AVP event.

## Why this is fully AVP-compliant

Under the v0.1 model, AVP draws a clear line:

- **Observability** — agent emits the event stream. Required.
- **Environment** — supervisor declares Commission (tools, MCP servers, subagents, skills, prompts). Optional but recommended.

There is **no mid-run bidirectional control** in v0.1 — no hooks reaching in, no synchronous supervisor decisions. The supervisor configures the environment; the agent operates within it; the agent emits.

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
echo '<config json>' | avp-claude-agent
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

