# Conformance coverage backlog

What the v0.1 suite does NOT yet cover, and why. Distilled from the original
`cases/v0.1-archive/` (now deleted): every archived case was built on the
retired `scripted_model` mechanism and several asserted events that no longer
exist (`text_emitted`, `reasoning_emitted`, `refusal_recorded`,
`mcp_server_connected`/`_disconnected`, `managed_ref_resolved`/`_resolve_failed`,
`subagent_failed`, `tool_failed`). Their still-valid intent is captured here.

## Blocked on infrastructure

- **Resolver (managed refs).** Fail-fast when a Commission carries managed
  `mcp_servers`/`skills`/`subagents` but no resolver is wired
  (`error_occurred(resolver_not_configured)`), and the resolved-ref path.
  Needs an in-repo resolver test service; out of scope today.
- **Subagents.** `subagent_invoked` → `subagent_returned` pairing, shared frame
  `span_id`, `avp.subagent.run_id`. Needs a managed subagent (resolver) or a
  deterministic in-process dispatch fixture.
- **Managed skills.** Resolution + `agent_started` listing the skill. Resolver-
  dependent. (Inline skills — Commission carries file content — are feasible
  without a resolver and worth a future case; goose materializes them, the
  claude SDK path is unverified.)

## `enabled_builtin_tools` — DONE (cross-agent), with remainder

Reference: when the agents disagree, the claude SDK is authoritative; fix goose
to match (but "match claude" sometimes means "finish claude").

- **empty-allowlist (`[]` → `agent_started.tools == []`): LIVE + passing on both
  agents** (2026-05-26). Goose loads its `developer` platform extension as the
  built-in surface and applies `enabled_builtin_tools` as a subtractive allow-list
  via `available_tools` (`None`→all, `[]`→developer not loaded, `[names]`→subset);
  `agent_started` now carries the tools. Claude got the "Stage 3" merge
  (`_apply_enabled_builtin_tools` filters the merged tool bag) AND conformance-run
  isolation (`setting_sources=[]` + `strict_mcp_config=True`, so no ambient host
  MCP leaks in — deterministic).
- **fail-fast on unknown name: LIVE + passing on both agents** (2026-05-26,
  `enabled-builtins/unknown-tool-name-fails-fast`). `enabled_builtin_tools` listing
  a name not in the agent's tool surface → `error_occurred(commission_collision)` +
  `agent_stopped(error)` before any model turn (no `assistant_message`). Goose
  validates after `prelude` in `runner.rs` against `descriptor.tools`; claude
  validates in `query()` against the probe surface, sets `self._aborted` so
  `receive_response` yields nothing. Empty allow-list (`[]`) is valid and does NOT
  collide.
- **Still open:**
  - **subset filter** (`[names]` → exactly those tools). Now mechanically supported
    by both, but no built-in tool name is common across claude (`Bash`/`Read`) and
    goose (`shell`/`write`/`edit`), so a cross-agent case isn't expressible; would
    be agent-specific.

## Blocked on determinism

- **Refusal.** Provider refusal → refusal block in `avp.content` +
  `agent_stopped(refused)`. Hard to trigger deterministically on a real model.
- **Reasoning / thinking.** Thinking blocks surface in `avp.content`. Needs a
  thinking-enabled model + config; provider-specific (candidate for a
  claude-only real-LLM case rather than a cross-agent structural one).
- **Unknown / disabled tool.** Model invoking a missing/disabled tool →
  `tool_invoked` → `tool_returned(isError=true)`, no execution. Needs a way to
  force the model to call a bad tool.
- **Local-dispatch discriminator on tool_invoked.** The archived
  `tools/agent-started-tools-reflects-builtins` asserted `avp.dispatch_target:
  "local"` on each `agent_started` tool *decl*. That field was dropped from
  `ToolDecl`: dispatch is now discriminated by the ABSENCE of `avp.mcp_server_id`
  on the decl, and the explicit `avp.tool.dispatch_target=local` lives only on the
  per-invocation `tool_invoked`. The decl side is covered by
  `enabled-builtins/default-commission-surfaces-builtins` (non-empty tools; names
  differ cross-agent so the list can only be asserted non-empty via `$contains {}`).
  Asserting `dispatch_target=local` on `tool_invoked` needs a forced built-in tool
  call (same determinism blocker as unknown/disabled-tool above).
- **Unsupported model.** Observed 2026-05-26: a bogus `model` string does NOT
  reject consistently. Neither agent pre-validates the model up front (no
  `descriptor.supported_models` list to check against); both hand the raw string
  to the provider. The claude CLI surfaced the bad model as `agent_stopped(error)`,
  but goose's provider silently fell back / accepted it and `agent_stopped(converged)`.
  So this is provider behavior, not an AVP-wire rule, and is not expressible as a
  deterministic cross-agent case today. Making it one requires agents to enumerate
  `supported_models` in the descriptor and fail fast with
  `error_occurred(unsupported_model)` when `commission.model` isn't in it — a real
  feature, tracked here, not a quick green.

## Feasible next (no blockers)

- **MCP server enumeration.** LIVE + passing on both agents (2026-05-26,
  `mcp/agent-started-lists-mcp-server`). Commission with an inline MCP server
  (`${AVP_TEST_MCP}` → `testing/mcp/avp_test_mcp.py`) → `agent_started.data.avp.mcp_servers`
  `$contains` it with `status:"connected"`. (Item retained as the worked example of
  the `$contains` + fixture-token pattern for future enumeration cases.)
