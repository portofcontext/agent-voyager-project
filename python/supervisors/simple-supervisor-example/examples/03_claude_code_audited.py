"""Example 03 — Audited Claude Code session (observer pattern, aep-claude-agent).

Story: the user runs an existing Claude Code session (the Claude Agent SDK
owns its own loop) but the supervisor still wants the same observability and
the same Config-declared environment they'd get from a driver-pattern runner.

What this example demonstrates:
  - The same Config-building flow as examples 01/02 — profile + overrides
  - Translation of Config → ClaudeAgentOptions:
      Config.allowed_tools  → SDK's allowed_tools (enforced natively by SDK)
      Config.boundary       → max_turns / max_budget_usd
      Config.system_prompt  → SDK's system_prompt
      Config.model          → SDK's model
  - Claude Code hooks (PreToolUse / PostToolUse) registered by the translator
    to emit AEP tool_invoked / tool_returned in step with the SDK's own dispatch
  - Same three-class post-run summary as the driver examples

Requires:
  - The Claude Code CLI binary on PATH (the SDK shells out to it; not pure Python)
      npm install -g @anthropic-ai/claude-code
      claude /login
  - ANTHROPIC_API_KEY set in the environment
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from simple_supervisor import build_config, render, summarize

from aep_claude_agent import ClaudeAgentTranslator


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    run_id = f"claude-code-audit-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    # Allowed tools are Claude Code's tool names (Read / Write / Bash / Edit / Glob).
    # The supervisor narrows the surface to read-only audit; the SDK enforces it.
    #
    # Boundary override: Claude Code's session bootstrap (CLAUDE.md files, skill
    # defs, system prompt) often exceeds a $0.05 budget on the FIRST turn alone,
    # so the cost-bounded profile's default cap doesn't fit. The SDK enforces
    # max_budget_usd by terminating its CLI subprocess, which surfaces as
    # "Command failed with exit code 1" if you under-budget. A real supervisor
    # framework would carry per-runner profiles that know Claude Code's baseline.
    config = build_config(
        run_id=run_id,
        prompt="Read the README.md and tell me what this project demonstrates. End with 'DONE'.",
        profile="cost-bounded",
        model="claude-haiku-4-5-20251001",
        boundary_overrides={"max_cost_usd": 2.00, "max_steps": 10, "max_tokens": 200_000},
    ).model_copy(update={"allowed_tools": ["Read"]})

    print("== Config (compiled from profile='cost-bounded', re-targeted at Claude Code tools) ==")
    print(config.model_dump_json(indent=2, exclude_none=True))
    print()
    print("== Live trajectory ==")

    events: list = []
    translator = ClaudeAgentTranslator(config, on_event=events.append)
    translator.run()

    for ev in events:
        type_name = type(ev).__name__
        if type_name == "ModelTurnEndedEvent":
            print(
                f"  [turn {ev.step}] cost=${ev.cost_usd:.5f}  "
                f"tokens={ev.tokens_input}+{ev.tokens_output}"
            )
        elif type_name == "TextEmittedEvent":
            preview = ev.text.replace("\n", " ")[:80]
            print(f"  [turn {ev.step}] text: {preview!r}")
        elif type_name == "ToolInvokedEvent":
            print(f"  [turn {ev.step}] -> {ev.tool}({list(ev.input.keys())})")
        elif type_name == "ToolReturnedEvent":
            head = ev.output.replace("\n", " ")[:60]
            print(f"  [turn {ev.step}] <- {ev.tool}: {head!r}...")
        elif type_name == "AgentStoppedEvent":
            print(f"  STOPPED reason={ev.reason}")

    print()
    print(render(summarize(events)))

    issues = _validate_outcome(events)
    print()
    if issues:
        print("== ✗ FAIL — example 03 ==")
        for msg in issues:
            print(f"  - {msg}")
        return 1
    print("== ✓ PASS — example 03 ==")
    return 0


def _validate_outcome(events: list) -> list[str]:
    """Post-conditions for example 03. LLM trajectory varies; outcomes don't.

    PASS criteria:
      - Run converged
      - At least one Read tool call fired (the only allowed_tool)
      - Some text was emitted (the agent actually answered)
      - Errors limited to the documented accounting_reset SDK quirk
        (any OTHER error_occurred is a real failure)
    """
    issues: list[str] = []
    types = [type(ev).__name__ for ev in events]

    stop = next((ev for ev in events if type(ev).__name__ == "AgentStoppedEvent"), None)
    if stop is None:
        issues.append("no agent_stopped event — translator exited mid-trajectory")
        return issues
    if str(stop.reason) != "converged":
        issues.append(f"expected stop reason 'converged'; got {stop.reason!r}")

    tool_invokes = [ev for ev in events if type(ev).__name__ == "ToolInvokedEvent"]
    if not tool_invokes:
        issues.append("no tool calls — agent should have used Read")
    elif not any(ev.tool == "Read" for ev in tool_invokes):
        issues.append(f"agent never called Read; called: {[ev.tool for ev in tool_invokes]}")

    if "TextEmittedEvent" not in types:
        issues.append("no text_emitted events — agent didn't produce a response")

    # accounting_reset is a known SDK quirk (see aep-claude-agent README).
    # Any OTHER error_occurred is a real failure.
    errs = [ev for ev in events if type(ev).__name__ == "ErrorOccurredEvent"]
    unexpected = [ev for ev in errs if ev.code.value != "accounting_reset"]
    if unexpected:
        issues.append(
            f"unexpected error_occurred (not accounting_reset): "
            f"{[(e.code.value, e.message[:80]) for e in unexpected]}"
        )

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
