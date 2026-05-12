# avp-claude-agent — conformance state

> Snapshot of which v0.1 conformance cases pass against `ClaudeAgentTranslator` via `avp-claude-agent-conformance run`. Wired into `make conformance` alongside the AVPAgent reference harness.

## Status

**20 / 20 cases passing.** `make conformance` runs both `avp-conformance run` (against `AVPAgent`) and `avp-claude-agent-conformance run` (against `ClaudeAgentTranslator`).

Run locally:

```bash
uv --directory python run avp-claude-agent-conformance run
```

## How conformance is driven

The translator has one public entry point: `run()`. The conformance harness uses the SDK-injection seam already on `ClaudeAgentTranslator.__init__` (`sdk_client_cls`, `sdk_options_cls`, `sdk_hook_matcher_cls`) to swap the real `claude_agent_sdk.ClaudeSDKClient` for `_ScriptedSDKClient` — a small class that yields canned messages and invokes the translator's PreToolUse / PostToolUse hooks at the points the script specifies. No network, no `claude` CLI.

Production wire order (now matches the conformance harness exactly, per trajectory.md §2.1 and §2.2):

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

## Adding a case

The v0.1 conformance cases are language-agnostic JSON under `conformance/v0.1/cases/`. The avp-claude-agent harness translates a case's `scripted_model` + `scripted_tools` + `scripted_resolver` into SDK-shape stand-ins (`AssistantMessage`, `ResultMessage`, `ToolUseBlock`, etc.) — see `_scripted_to_translator_script` in `conformance.py` for the mapping. Subagent tool_calls get rewritten to the SDK's `Agent` tool with a `subagent_type` input field, since that's how the SDK dispatches managed subagents.
