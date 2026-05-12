# avp-claude-agent — conformance state

> Snapshot of which v0.1 conformance cases pass against `ClaudeAgentTranslator` via `avp-claude-agent-conformance run`. Wired into `make conformance` alongside the AVPAgent reference harness.

## Status

**20 / 20 cases passing.** `make conformance` runs both `avp-conformance run` (against `AVPAgent`) and `avp-claude-agent-conformance run` (against `ClaudeAgentTranslator`).

Run locally:

```bash
uv --directory python run avp-claude-agent-conformance run
```

## Adding a per-SDK conformance harness

The reusable framework lives in [`avp.conformance.sdk_harness`](../../avp/src/avp/conformance/sdk_harness.py). It handles case loading, expectation evaluation (matchers, forbidden events, final-state checks), `CaseResult` construction, suite iteration, and the CLI. A new SDK harness implements **one function** and gets the rest for free:

```python
from avp.conformance.sdk_harness import (
    build_commission, build_descriptor, build_resolver,
    make_cli, run_case, run_suite,
)

def _run_one(case):
    commission = build_commission(case)
    events = []
    agent = MyAgent(
        commission=commission,
        on_event=events.append,
        resolver=build_resolver(case, commission),
        descriptor=build_descriptor(case),
        # ... SDK-specific construction
    )
    agent.run()
    return events

main = make_cli(
    runner=_run_one,
    prog="my-sdk-conformance",
    description="Run v0.1 conformance cases against MyAgent.",
)
```

And in `pyproject.toml`:

```toml
[project.scripts]
my-sdk-conformance = "my_sdk.conformance:main"
```

That's the whole contract. The framework provides `--case` / `--suite` / `-v` flags and the `PASS/FAIL` reporting format. Workspace-root discovery walks up from CWD looking for `conformance/v0.1/`.

## What avp-claude-agent's harness has on top of `_run_one`

This is an **observer-pattern** agent: the Claude Agent SDK owns the loop. To drive the translator without opening the real SDK, the harness uses the `sdk_client_cls` constructor seam already on `ClaudeAgentTranslator.__init__` to inject `_ScriptedSDKClient` — a small class that implements `ClaudeSDKClient`'s protocol (async context manager, `connect`, `get_context_usage`, `get_mcp_status`, `receive_response`) and yields canned messages while invoking the translator's PreToolUse / PostToolUse hooks at the points the script specifies.

The CASDK-specific bits in [`conformance.py`](src/avp_claude_agent/conformance.py):

- `_ScriptedSDKClient` — scripted SDK client (no network, no `claude` CLI).
- `_block`, `_assistant_message`, `_result_message` — duck-typed Message / Block stand-ins matching the shapes `_on_sdk_message` dispatches on.
- `_case_to_script` — translates a case's AVP-shape `scripted_model` + `scripted_tools` into the SDK message stream + hook-fire sequence (handles cumulative-usage accumulation, subagent dispatch rewriting to the `Agent` tool, refusal mapping).

Driver-pattern agents (built directly on `AVPAgent`) don't need any of this — the reference `avp.conformance.harness` already drives any `AVPAgent`-shaped agent.

## Production wire order

Now matches the conformance harness exactly, per trajectory.md §2.1 and §2.2:

1. `run_requested` — prelude
2. `agent_described` — prelude
3. `agent_started` — prelude (3rd, always fires even on validation / resolve failure)
4. `managed_ref_resolved*` — replay of silent-phase resolutions
5. `mcp_server_connected*` — per declared server
6. `skill_loaded*` — per skill whose content went into context
7. `model_turn_*` / `tool_*` / ... — drive
8. `mcp_server_disconnected*` — lifecycle bookend
9. `agent_stopped`

The two-phase resolution (`_resolve_managed_assets_silently` + `_emit_resolution_events`) is what lets `agent_started` fire third in the prelude while `managed_ref_resolved` events still come between `agent_started` and the first model turn.
