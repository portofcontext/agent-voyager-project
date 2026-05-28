# v0.1 conformance coverage

What the cross-agent conformance suite covers, and what it deliberately does
not yet. This is a rationale map, not a status checklist: the live case count
comes from `avp-conformance` at runtime (`uv run avp-conformance validate`),
never from this file.

Coverage is layered. Below the conformance cases sit the JSON Schemas (every
`Event` / `Commission` / `AgentDescriptor` field shape), per-package unit
tests, seam tests (multi-turn history render, translator/SDK token+cost
parity, supervisor/agent subprocess), and bindings drift detection. The
conformance suite is the language-agnostic behavioral contract on top: every
case runs against a real model and is expected to pass on every conforming
agent (today: `avp-claude-agent-sdk` and `avp-goose`).

## Covered (cross-agent, live)

- **Prelude + lifecycle.** The trajectory opens `run_requested` ->
  `agent_described` -> `agent_started` and closes with
  `agent_stopped(converged)`. (`lifecycle/trivial-prompt-converges`,
  `prelude/prelude-events-open-trajectory`)
- **Self-contained attribution.** `run_requested` carries the full commission
  snapshot plus `avp.supervisor.*`; `agent_described` carries the descriptor.
  (`prelude/run-requested-carries-commission-snapshot`,
  `prelude/agent-described-carries-descriptor`)
- **Source tagging.** Agent-emitted events carry `source: avp://agent`
  (asserted on every case's events).
- **Assistant content.** A turn surfaces its text in `assistant_message.avp.content`.
  (`content/assistant-message-carries-text-content`)
- **`enabled_builtin_tools` (the deepest seam).** `None` exposes all (non-empty
  `agent_started.avp.tools`), `[]` exposes none, and a name the agent does not
  offer is a `commission_collision`: `error_occurred(commission_collision)` +
  `agent_stopped(error)` before any model turn.
  (`enabled-builtins/{default-commission-surfaces-builtins,
  empty-allowlist-hides-builtins, unknown-tool-name-fails-fast}`)
- **Inline MCP enumeration.** An inline `mcp_server` (`${AVP_TEST_MCP}`) surfaces
  on `agent_started.avp.mcp_servers` with `status: connected`. Also the worked
  example of the `$contains` matcher + fixture-token pattern.
  (`mcp/agent-started-lists-mcp-server`)
- **Tool round-trip.** A real-model loop where the model calls a built-in tool:
  `tool_invoked` -> `tool_returned` -> `agent_stopped(converged)`. Tool names
  differ cross-agent so only the event types + ordering are pinned, not the name.
  (`tools/tool-round-trip`)
- **Per-turn usage / cost.** Each `assistant_message` carries `avp.usage` +
  `avp.cost_usd`; the harness folds the stream and asserts nonzero totals (the
  agent publishes no cumulative totals on `agent_stopped`, consumers reduce).
  (`accounting/assistant-message-carries-usage-and-cost`)
- **Span-tree structure (universal).** Not a case but an always-on harness check
  (`_check_structure`, runs on every checked trajectory): one `trace_id` per run,
  well-formed non-zero `span_id` / `parent_span_id`, prelude events at the root,
  and every other event's `parent_span_id` resolving to a span the run emitted
  (this is what pairs `tool_returned` under its `tool_invoked`, turns under the
  agent span). Both agents satisfy it across all cases.

Prelude, descriptor, Commission-side tool filtering, the tool round-trip, cost
accounting, and span structure are all covered. The remaining gaps are the
provider-nondeterministic events, the invalid-Commission entrypoint behavior,
and the entire resolver layer.

## Gaps

### Needs a small feature (not a pure case)

- **Invalid-Commission error path.** A malformed Commission MUST yield
  `error_occurred` + `agent_stopped(error)` (commission.md §6 / trajectory.md §8).
  Two blockers, both small: (1) the case format strictly validates `commission`,
  so a case can't carry a malformed one without a `commission_raw` escape hatch in
  `case.py` + `_run_case`; (2) neither conformance `run` entrypoint emits the two
  events today (claude's `load_commission` and goose's deserialize both just raise
  and exit non-zero) so each entrypoint must wrap commission loading and emit the
  error trajectory first. The reference agent's `main()` already does this
  (`test_reference_agent::test_bad_schema_version`), so the shape is known.

### Blocked on determinism (hard to force on a real model)

- **Refusal.** Provider refusal -> refusal block in `avp.content` +
  `agent_stopped(refused)`. Candidate for a claude-only real-LLM case rather than
  a cross-agent structural one.
- **Reasoning / thinking.** Thinking blocks in `avp.content`. Needs a
  thinking-enabled model + config; provider-specific.
- **Forced bad / disabled tool.** Model invoking a missing tool ->
  `tool_invoked` -> `tool_returned(is_error=true)`, no execution. Needs a way to
  make the model call a bad tool. This is also where the explicit
  `avp.tool.dispatch_target=local` discriminator on `tool_invoked` would be
  asserted (the decl side is covered by `default-commission-surfaces-builtins`;
  `ToolDecl` no longer carries a positive dispatch field, local is the absence of
  `avp.mcp_server_id`).
- **Unsupported model.** A bogus `model` does not reject consistently: neither
  agent pre-validates against `descriptor.supported_models`, so claude surfaces
  the provider's rejection as `agent_stopped(error)` while goose's provider
  silently falls back and converges. Making this a case requires agents to
  enumerate `supported_models` and fail fast with
  `error_occurred(unsupported_model)`: a real feature, not a quick green.

### Blocked on infrastructure (no in-repo resolver)

The entire Resolver API (`resolver.md`) has zero conformance coverage. It is the
least-baked part of v0.1 and there is no in-repo resolver service to dial.

- **Resolver fail-fast + resolved-ref path.** A Commission with managed
  `mcp_servers`/`skills`/`subagents` but no resolver wired ->
  `error_occurred(resolver_not_configured)`, plus the happy path.
- **Managed subagents.** `subagent_invoked` -> `subagent_returned` pairing,
  shared frame `span_id`, `avp.subagent.run_id`. (No conformance case exercises
  the pair on a real agent yet.)
- **Managed skills.** Resolution + `agent_started` listing the skill. Inline
  skills (Commission carries file content, no resolver) are feasible sooner:
  goose materializes them, the claude SDK path is unverified.

## Not expressible cross-agent

- **Subset tool filter** (`[names]` -> exactly those tools). Mechanically
  supported by both agents, but no built-in tool name is common across agents.
