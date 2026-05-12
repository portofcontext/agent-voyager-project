# avp-claude-agent — conformance state

> Snapshot of the v0.1 conformance suite against `ClaudeAgentTranslator` via `avp-claude-agent-conformance run`. Wired into `make conformance` alongside the AVPAgent reference harness.

## Status

`make conformance` runs both harnesses:

- **`avp-conformance run`** drives the reference `AVPAgent` with `ScriptedModel`. Deterministic, all 20 / 20 cases pass.
- **`avp-claude-agent-conformance run`** drives `ClaudeAgentTranslator` against the **real** Claude Agent SDK. Requires `ANTHROPIC_API_KEY` + the `claude` CLI on `PATH`. 14 / 20 pass; 6 are skipped via `scripted_only: true` (see below).

Run locally:

```bash
uv --directory python run avp-claude-agent-conformance run
```

## Two case shapes: live vs scripted_only

Cases divide into two groups based on whether their wire rule can be triggered with a non-deterministic live model.

**Live-friendly** — match structural events (event type, ordering, lifecycle bookends). The exact text / tool sequence the model produces doesn't matter. These run against both harnesses.

**`scripted_only: true`** — the wire rule needs the model to do something specific that can't be reliably triggered (invoke a forbidden tool, refuse on cue, produce thinking blocks reliably, invoke a managed subagent on cue, hallucinate a tool name). Live harnesses skip these; the AVPAgent harness with `ScriptedModel` still runs them.

Six cases are currently tagged `scripted_only`:

| Case | Why scripted |
|---|---|
| `allowlist-runtime-blocks-disabled-tool` | Needs the model to invoke a tool the SDK filters out of its catalog. |
| `tool-failed-on-unknown-tool` | Needs the model to fabricate a tool name. |
| `refusal-recorded-stops-with-refused` | Needs `stop_reason="refusal"`; modern Claude doesn't refuse arbitrary prompts. |
| `reasoning-emitted-from-thinking-blocks` | Needs extended-thinking output; unreliable to trigger on demand. |
| `subagent-invoked-and-returned-pair-frame-span` | Needs the model to invoke a declared subagent on cue. |
| `subagent-failed-when-spawn-errors` | Same as above + needs the resolver's spawn outcome to surface as a failure. |

## Pattern for writing new cases

Write live-friendly by default. Match the wire SHAPE, not specific content. Use `scripted_only: true` only when the wire rule is genuinely unreliable to trigger live.

**Do:**

```json
{
  "match": { "type": "avp.text_emitted" },
  "label": "text_emitted fires after some model_turn_ended"
}
```

**Avoid** (unless `scripted_only`):

```json
{
  "match": {
    "type": "avp.text_emitted",
    "data": { "step": 1, "avp.text": "the answer is 42. DONE." }
  }
}
```

`text-emitted-carries-assistant-content.json` is the canonical live-friendly example: structural matchers, no `step` constraint, no exact-text assertion. The `commission.model` is set to a real Claude model and `commission.prompt` is short and predictable.

## How the harness is wired

`translator.run()` is the single public entry point. The harness wires resolver / descriptor / commission from the case (via `avp.conformance.sdk_harness.build_*` helpers), runs `translator.run()` against the real SDK, and returns the events the translator emitted. The framework (`avp.conformance.sdk_harness`) handles case loading, expectation evaluation, `scripted_only` skipping (`SkipCase` exception), CaseResult construction, and the CLI.

The full per-SDK harness lives in [`conformance.py`](src/avp_claude_agent/conformance.py) and is ~60 lines.

## Production wire order

Matches the conformance harness exactly, per trajectory.md §2.1 and §2.2:

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
