# Protocol-Level TODOs

Open protocol-shape questions surfaced by living-testing the two reference
runners (`aep-anthropic` driver-pattern and `aep-claude-agent` translator-pattern).
Each item below is a place where v0.1 is silent, ambiguous, or where the two
runner styles cannot both be conformant against the same `Config`. These are
not bugs in either implementation — they are spec gaps to resolve before v0.1
ships or to explicitly defer to v0.2.

---

## 1. Driver vs. translator conformance — the central seam

**Problem.** The spec assumes the runner owns the agent loop (§9.3). The
`aep-anthropic` driver runner does. The `aep-claude-agent` translator runner
does NOT — the Claude Agent SDK owns the loop and exposes only `PreToolUse`,
`PostToolUse`, and the `AssistantMessage`/`ResultMessage` async stream. There
is no native hook for "before this turn starts" or "before agent_stopped".

This means a `Config` with `verifiers[].trigger = before_each_turn` (or
`before_first_turn`, or `at_end`) is honored by the driver runner and silently
ignored by the translator runner. Per §13.1 items 13–17 that is a non-conformance,
but nothing on the wire signals it. Two "conforming" runners can produce
divergent trajectories from the same `Config`.

**TODO — pick a stance and write it into §13:**

- [ ] **(a) Strict.** A runner that cannot honor a declared trigger MUST emit
      `error_occurred` at startup naming the unsupported trigger, then
      `agent_stopped(reason="error")`. No silent drops. Smallest spec change.
- [ ] **(b) Profiled.** Carve out a "translator profile" in §13 with a reduced
      MUST list (e.g., omit pre-turn triggers and `inject_correction`). The
      `agent_started` event declares which profile the runner implements.
- [ ] **(c) Mechanism.** Specify how a wrapper-style runner injects user-role
      text between turns of an SDK-owned loop (e.g., via the SDK's prompt-input
      channel). This re-enables `inject_correction` and re-observation on
      translators. Likely a v0.2 conversation.

**Acceptance:** a conformance case `verifier-trigger-unsupported-on-translator`
that demonstrates the chosen behavior, passing for both runners.

---

## 2. Re-observation: removed in `f1e34f8`, decide the v0.2 path

**Problem.** Re-observation was the cleanest way to combat context rot but it
was removed wholesale because the translator pattern can't faithfully inject
content "before each turn". The driver runner could honor it; the translator
could not. The asymmetry made it un-shippable for v0.1.

**TODO:**

- [ ] Confirm the removal is YAGNI for v0.1 and not a permanent design decision.
- [ ] If returning in v0.2, re-introduce only after item 1.(c) above is solved —
      otherwise the same asymmetry recurs.
- [ ] Until then, document in §14 (Deployment scope) that supervisors needing
      pre-turn world refresh should expose it as an RPC tool the agent calls,
      not as a runner-injected observation.

---

## 3. `max_steps: N` exactness across runner styles

**Problem.** §9.2 promises `max_steps: N` runs EXACTLY N turns and §9.4 says
"two conforming runners with identical inputs MUST agree on whether one more
turn is permitted." The translator delegates this to
`ClaudeAgentOptions.max_turns`
(`python/runners/aep-claude-agent/src/aep_claude_agent/translator.py`, around
the `_build_sdk_options` helper). If the SDK's notion of "turn" diverges from
AEP's `model_turn_started`/`model_turn_ended` pair (e.g., counts a tool
roundtrip, or a sub-agent dispatch, as its own turn), the EXACT promise
silently breaks across runners.

**TODO:**

- [ ] Add a conformance case `boundary-max-steps-exact-N` with `max_steps: 3`
      that asserts both runners terminate with `state.total_turns == 3` and
      `agent_stopped.reason == "turn_limit"`.
- [ ] If the SDK semantics differ, the translator MUST count turns itself
      against AEP's definition (post-`model_turn_ended` increment) and stop
      ahead of the SDK's own limit, rather than trusting `max_turns`.
- [ ] Document AEP's "turn" definition explicitly in §9.1: one turn = one
      `model_turn_started`/`model_turn_ended` pair, regardless of how many
      tool calls the model emits within it.

---

## 4. Verifier source unavailability vs. verifier failure

**Problem.** §7.5 (path resolution) and §14 (deployment scope) correctly punt
workspace provisioning out of the spec. But this means the same `Config` run
in two deployments can produce `verifier_evaluated.passed=false` for two very
different reasons: the script genuinely failed, OR the script wasn't there.
Reviewers reading the trajectory cannot tell them apart.

**TODO:**

- [ ] Add an optional `error` distinguisher to `verifier_evaluated`:
      `"source_unavailable" | "source_timed_out" | "source_crashed" | null`.
- [ ] §13.1.18 amended: when the verifier source cannot be located/executed,
      runners MUST set `passed: false` AND `error: "source_unavailable"`.
      This keeps the deterministic Boolean contract while making the
      environment-vs-logic distinction visible on the wire.
- [ ] Conformance case `verifier-source-unavailable-marks-error` covers it.

---

## 5. Translator usage-accounting fragility

**Problem.** The Claude Agent SDK reports usage as cumulative-per-message,
which the translator handles by tracking the previous cumulative and emitting
deltas with a `max(0, cum - prev)` clamp. This silently swallows any case
where the SDK resets its cumulative count mid-run (e.g., sub-agent dispatch,
session compaction). When that happens, `state.total_tokens` and
`state.total_cost_usd` would silently under-report rather than violate §9.4's
monotonicity guarantee — but the supervisor would have no way to detect it.

**TODO:**

- [ ] Add a runner-side invariant check: if `cum < prev`, emit `error_occurred`
      with `code: "accounting_reset"` rather than silently clamping. Trajectory
      consumers can then decide whether to abort or accept the discrepancy.
- [ ] Add a normative note to §9.4: when wrapping an SDK that reports
      cumulative usage, runners MUST detect resets and surface them; silent
      clamping is a conformance violation.

---

## 6. `tool_exec_timed_out` empty-string return — model-visible behavior

**Problem.** §9.3 specifies that on `tool_exec_timed_out`, the runner returns
`""` to the model. From the model's perspective, the tool ran and returned an
empty string — indistinguishable from a tool that legitimately returns empty
output. This is plausible but undertested.

**TODO:**

- [ ] Decide whether to keep `""` or switch to a structured error string
      (e.g., `"Error: tool execution timed out after Nms"`) so the model can
      reason about retry. The latter mirrors the §8 step-4 `Error: ` prefix
      convention for `tool_exec_resolved.error`.
- [ ] Conformance case currently missing; add `tool-exec-timed-out-returns-X`
      after the decision.

---

## 7. `agent_started.tools` content when `allowed_tools` filters built-ins

**Problem.** §13.1.2 says `agent_started` MUST include `tools` when
available. The new `Config.allowed_tools` (§8.1) filters BOTH `Config.tools`
RPC entries AND runner built-ins. Should the `agent_started.tools` array
list:

  (a) only the filtered, model-visible tool set,
  (b) `Config.tools` as declared (RPC tools only — current behavior),
  (c) both: declared RPC tools plus the runner's filtered built-ins?

Today this is implementation-defined and the two runners may differ.

**TODO:**

- [ ] Pin the answer in §13.1.2. Recommendation: (a) — the trajectory should
      reflect the agent's actual tool surface, not the un-filtered declaration.
- [ ] Conformance case `agent-started-tools-reflects-allowed-tools-filter`.

---

## Out of scope for this PR

- The cumulative-vs-delta SDK accounting fix in `translator.py` is correct
  as shipped; only the *invariant check* (item 5) is open.
- The new conformance cases under `conformance/v0.1/cases/{verifier,passthrough,
  tool-exec,skills,allowed-tools}/` already pin down the spec ambiguities they
  target. Items above are the residue.
