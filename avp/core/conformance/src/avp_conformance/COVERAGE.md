# v0.1 conformance coverage

What the cross-agent conformance suite covers, and what it deliberately does
not yet. This is a rationale map, not a status checklist: the live case count
comes from `avp-conformance` at runtime (`avp-conformance validate`),
never from this file.

Coverage is layered. Below the conformance cases sit the JSON Schemas (every
`Event` / `Commission` / `AgentDescriptor` field shape), per-package unit
tests, seam tests (multi-turn history render, translator/SDK token+cost
parity, supervisor/agent subprocess), and bindings drift detection. The
conformance suite is the language-agnostic behavioral contract on top: every
case runs against a real model and is expected to pass on every conforming
agent. A case that exercises an
optional surface declares it in `requires` (e.g. `subagents`) and is skipped,
not failed, for an agent whose descriptor doesn't declare it.

Report passes together with skips and the exercised surfaces. Passing the
applicable cases is not evidence that an undeclared surface works. In particular,
a framework agent with no built-in tools skips the built-in tool case, but must
still pass the managed MCP round trip below. This proves actual dispatch, result
pairing, and a subsequent model response, rather than only MCP connection.

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
- **Managed MCP tool round-trip (all agents).** The model invokes the supplied
  echo tool with a marker, receives a successful matching result, then returns
  the marker in a subsequent assistant response. The case requires
  `dispatch_target=mcp_server`; universal structure checks pair the call/result
  IDs and spans. It has no descriptor-based `requires` gate. `$text_contains`
  matches either string tool output or a list of text blocks.
  (`mcp/managed-mcp-tool-round-trip`)
- **Tool calls beyond one round trip (all agents, through the MCP fixture).**
  Three dependent rounds, two calls requested in one response, and a tool that
  fails both ways an MCP tool can (an `isError` result and a protocol error).
  Each case judges every call's own result through `tool_calls` (a call whose
  input matches must have its own result match), so results handed to the
  wrong call fail even when every id is consistent. Failures must be
  `is_error: true` with the failure text, and the run must still converge.
  Whether the model really calls in parallel is its choice; the pairing
  requirements hold either way, and adapters' seam tests script the parallel
  path. (`mcp/{multi-round-tool-calls, parallel-tool-calls,
  tool-error-result-is-recorded, tool-protocol-error-is-recorded}`)
- **Built-in tool round-trip (declared tools).** A real-model loop where the model calls a built-in tool:
  `tool_invoked` -> `tool_returned` -> `agent_stopped(converged)`. Tool names
  differ cross-agent so only the event types + ordering are pinned, not the name.
  (`tools/tool-round-trip`)
- **Per-turn usage / cost.** Each `assistant_message` carries `avp.usage` +
  `avp.cost_usd`; the harness folds the stream and asserts nonzero totals (the
  agent publishes no cumulative totals on `agent_stopped`, consumers reduce).
  (`accounting/assistant-message-carries-usage-and-cost`)
- **Accounting correctness (universal).** An always-on check
  (`_check_accounting`, every trajectory, every case): token counts are
  non-negative integers, the cache split sits inside `input_tokens`, an
  `unknown` cost is `0`, and every `computed` cost equals the bundled price
  table's figure for the turn's usage (response model, else request model). A
  turn whose models the table can't price is not judged. This is what catches
  double-counted cache tokens and mis-priced turns, which nonzero totals miss.
- **Provider authentication failure.** With the provider's credential variables
  replaced by an invalid key (`credentials: "invalid"`), the run ends
  `error_occurred(auth_error)` + `agent_stopped(error)` and emits no
  `assistant_message`: a failed inference is never presented as model output.
  (`errors/invalid-credentials-fail-cleanly`)
- **Commission system prompt.** A marker only the system prompt asks for appears
  in the reply. (`commission/system-prompt-is-honored`)
- **Inline skills.** `agent_started.avp.skills` lists the Commission's skill,
  and a codeword that lives only in its body appears in the reply, so the skill
  was materialized and reached the model. (`commission/inline-skill-is-loaded`)
- **Interruption.** SIGTERM one second after `agent_started`, mid-inference,
  ends the trajectory with `agent_stopped(interrupted)`
  (`interrupt` in the case; the exit status is not judged).
  (`lifecycle/sigterm-stops-interrupted`)
- **Subagent frames (declared subagents).** Every `subagent_invoked` closes, and
  an abandoned frame never coexists with `converged`.
  (`lifecycle/subagent-frame-always-closes`, plus the universal structure check)
- **Span-tree structure (universal).** Not a case but an always-on harness check
  (`_check_structure`, runs on every checked trajectory): one `trace_id` per run,
  well-formed non-zero `span_id` / `parent_span_id`, prelude events at the root,
  and every other event's `parent_span_id` resolving to a span the run emitted
  (this is what pairs `tool_returned` under its `tool_invoked`, turns under the
  agent span). Both agents satisfy it across all cases.
- **Tool pairing (universal).** Every `tool_use` block in a turn has exactly one
  `tool_invoked` under that turn; every `tool_returned` sits under its
  `tool_invoked` and carries that call's id; no call returns twice; and a
  converged run leaves no call unreturned (an interrupted or failed run may stop
  with one in flight).
- **Metering (universal, `--meter`).** Provider traffic runs through a local
  proxy; the bill must equal the trajectory's turns plus subagent rollups. With
  no rollups and no cut-off responses, each billed response must also be one
  turn's usage, so usage filed on the wrong turn fails even when totals match.

The remaining gaps are the provider-nondeterministic events and the
invalid-Commission entrypoint behavior below.

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
  make the model call a bad tool (a tool that runs and fails is covered above).
  This is also where the explicit
  `avp.tool.dispatch_target=local` discriminator on `tool_invoked` would be
  asserted (the decl side is covered by `default-commission-surfaces-builtins`;
  `ToolDecl` no longer carries a positive dispatch field, local is the absence of
  `avp.mcp_server_id`).
- **Unsupported model.** A bogus `model` does not reject consistently: Claude
  surfaces the provider's rejection as `agent_stopped(error)`, Goose's provider
  silently falls back and converges, and Pi fails fast with
  `error_occurred(unsupported_model)` from its model catalog. A cross-agent case
  needs every agent to fail fast the way Pi does.
- **Forced delegation.** Whether the model delegates is its decision, so the
  subagent case asks for delegation and judges the frames only where the agent
  declares subagents. No case can force a child run that then fails.

### Feasible, deliberately deferred

- **Live runs in CI.** The live suites run on demand from contributors'
  machines; the manual CI jobs (Claude, Pi) have not been dispatched.

## Not expressible cross-agent

- **Subset tool filter** (`[names]` -> exactly those tools). Mechanically
  supported by both agents, but no built-in tool name is common across agents.
