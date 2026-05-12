# avp-claude-agent — conformance state

> Snapshot of which v0.1 conformance cases pass against `ClaudeAgentTranslator` via `avp-claude-agent-conformance run`, plus the remaining failures with short fix sketches. Updated as cases close.

## Status

**16 / 20 cases passing.** The harness drives the translator via `ClaudeAgentTranslator.run_scripted()` (the non-SDK entry point — same phase sequence as `run()` minus `_async_invoke_sdk`). Production runs are not exercised here; conformance is wire-level only.

Run locally:

```bash
uv --directory python run avp-claude-agent-conformance run
```

## Remaining failures

### B1. `subagent-invoked-and-returned-pair-frame-span` — thin observer shape

**Asserts.** Resolved-subagent dispatch emits `subagent_invoked` carrying `gen_ai.agent.description` (from resolver metadata), `avp.subagent.run_id` (child run's run_id), and `avp.subagent.input`; the paired `subagent_returned` carries the result text + spawn-outcome usage rollup.

**Why it fails.** The translator deliberately implements a **thin observer** shape (`translator.py:_handle_subagent_post`). The Claude Agent SDK runs the subagent **in-process**, so the parent's observer surface sees only a tool_use → tool_result pair for the `Agent` tool — there is no child `run_id`, no per-subagent usage, no resolver-spawned trajectory. The translator emits `gen_ai.agent.name` + `avp.subagent.invocation_id` + empty usage + reason=converged.

**Fix sketch (significant).** Route declared-subagent dispatch through the AVP resolver instead of the SDK's built-in subagent runtime:

1. In `_on_pre_tool_use_hook` when `tool == "Agent"` and `subagent_type` matches a declared subagent, call `self._resolver.spawn_subagent(run_id=..., id=name, ref=ref, input=sanitized_input)` instead of letting the SDK execute it.
2. The resolver returns a `SubagentSpawnOutcome` (child_run_id, text, reason, usage). Emit `subagent_invoked` with `avp.subagent.run_id = outcome.child_run_id`, description from resolved metadata. Emit `subagent_returned` with result.text + usage.
3. Return a hook override that **prevents** the SDK from actually spawning its in-process subagent — feed the resolver's text back as the tool_result so the parent's loop sees a completed `Agent` call.
4. SDK-version concern: whether PreToolUse hooks can short-circuit dispatch this way needs verifying. If the hook can't suppress execution, fall back to: do the resolver call, observe both the resolver result AND the SDK's eventual tool_result, prefer the resolver's payload on the wire.

This is a real design change. It also makes the translator depend on the resolver protocol for subagents (which AVPAgent already does), making the observer-pattern agent symmetric with the driver-pattern reference. Worth doing.

### B2. `subagent-failed-when-spawn-errors` — same root cause as B1

**Asserts.** When `avp.spawn_subagent` errors, the agent emits `subagent_invoked` then `subagent_failed`, NOT `subagent_returned`.

**Why it fails.** Same observer-pattern root cause as B1 — the SDK runs the subagent in-process; the translator has no spawn-error path because it doesn't call the resolver.

**Fix sketch.** Falls out of B1 — when the resolver call in step (1) above raises or returns an error outcome, emit `subagent_failed` instead of `subagent_returned`.

### C1. `text-emitted-carries-assistant-content` — emission order

**Asserts.** Per turn, the order on the wire is `model_turn_started` → `model_turn_ended` → `text_emitted`.

**Why it fails.** The translator emits `text_emitted` **during the AssistantMessage block walk** (between `model_turn_started` and `model_turn_ended`). AVPAgent emits text **after** `model_turn_ended`. The case asserts the latter order.

**Fix sketch (small).** In `_handle_assistant_message`:

1. Walk the blocks in two passes: first pass collects `(text, reasoning_blocks)`, doesn't emit; second pass (after the existing `model_turn_ended` emission below) emits `reasoning_emitted` per block then `text_emitted` for the joined text.
2. Equivalently: keep the single walk, accumulate emissions into a deferred list, replay after `model_turn_ended`. Less restructuring of existing logic.

Either way: no behavior change for production consumers other than event order within a turn. Worth confirming the spec actually mandates this order (trajectory.md §3.1) before committing to it; if the spec is silent on intra-turn order, the case may need restructuring instead.

### C2. `reasoning-emitted-from-thinking-blocks` — likely same root cause as C1

**Asserts.** Per turn, `model_turn_started` → `model_turn_ended` → `reasoning_emitted` matching the case's `avp.reasoning.text` + `avp.reasoning.signature`.

**Why it fails.** Almost certainly the same emission-order issue — the translator fires `reasoning_emitted` during the block walk, before `model_turn_ended`. Verify by re-running after the C1 fix; it likely closes both.

**Fix sketch.** Falls out of C1's deferred-emission restructure.

## Related but separate: production `run()` violates spec event order

Discovered while doing this work. Independent of the cases above.

**Spec (trajectory.md §2.1, §2.2).** Every conforming trajectory opens with `run_requested` → `agent_described` → `agent_started` **in that exact order**. `managed_ref_resolved` events come **between `agent_started` and the first `model_turn_started`**.

**Current production `run()` (translator.py:511-589).** Emits in order: `run_requested` → `agent_described` → `managed_ref_resolved` → `skill_loaded` → `agent_started` (with SDK enrichment from `client.get_context_usage()` after `client.connect()`). The reordering exists so `agent_started.data.{tools,skills,subagents}` can carry SDK-introspected descriptions / agentType / catalogs that only exist post-connect.

**`run_scripted` already fixed.** It emits in spec order (no SDK to connect to, no enrichment to wait for); this is one reason the conformance harness works at all.

**Fix sketch.** Decouple resolution from emission so the merged-view `agent_started` and the post-resolve `managed_ref_resolved` events can both fire in spec order with the same data:

1. Split `_resolve_managed_assets` into `_resolve_managed_assets_silently` (calls resolver, fills `self._resolved_*` dicts, no emission) and `_emit_resolution_events` (replays the round-trips as `managed_ref_resolved` events).
2. New production `run()` order:
   - `_emit_run_prelude()` → `run_requested`, `agent_described`
   - Validation gates
   - `_resolve_managed_assets_silently()` — populates internal state
   - Open SDK client, connect
   - `_emit_agent_started_with_sdk_enrichment(client)` — emits `agent_started` with the merged view (using both resolved material AND SDK introspection)
   - `_emit_resolution_events()` — emits `managed_ref_resolved` per ref
   - `_emit_mcp_connections_after_connect(client)` — emits `mcp_server_connected`
   - `_emit_skills_loaded()` → `skill_loaded`
   - Drive the SDK loop
3. Error semantics: failures during silent resolve become deferred — the resolver round-trip happened, but `managed_ref_resolved` / `managed_ref_resolve_failed` for the failures still need to fire (after `agent_started`, before the agent stops). Straightforward but worth a test.

This change is invisible to consumers reading the wire (event order tightens, content unchanged) but it brings production into spec compliance. Belongs in its own work block; not gated by the cases above.

## Once these close

When B and C are done, all 20 v0.1 cases pass. At that point: wire `avp-claude-agent-conformance run` into the `Makefile`'s `conformance` target so `make check` runs both harnesses, and remove this file (or empty it down to a status line).
