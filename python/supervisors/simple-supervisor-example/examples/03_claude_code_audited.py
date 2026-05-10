"""Example 03 — Audited Claude Code session (observer pattern, avp-claude-agent).

Story: the user runs an existing Claude Code session (the Claude Agent SDK
owns its own loop) but the supervisor still wants the same observability and
the same Commission-declared environment they'd get from a driver-pattern agent.

What this example demonstrates:
  - The same Commission-building flow as example 01 — profile + overrides
  - Translation of Commission → ClaudeAgentOptions:
      Commission.enabled_builtin_tools → SDK's `tools` parameter
      Commission.system_prompt        → SDK's system_prompt
      Commission.model                → SDK's model
  - Claude Code hooks (PreToolUse / PostToolUse) registered by the translator
    to emit AVP tool_invoked / tool_returned in step with the SDK's own dispatch
  - Same post-run summary as the driver examples

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

from simple_supervisor import build_commission, render, summarize

from avp_claude_agent import ClaudeAgentTranslator


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    run_id = f"claude-code-audit-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    # Tool names here are Claude Code's (Read / Write / Bash / Edit / Glob).
    # The supervisor narrows the surface to a read-only audit; the SDK enforces
    # it via the `tools` parameter the translator passes through.
    config = build_commission(
        run_id=run_id,
        prompt="Read the README.md and tell me what this project demonstrates. End with 'DONE'.",
        profile="read-only",
        model="claude-haiku-4-5-20251001",
    ).model_copy(update={"enabled_builtin_tools": ["Read"]})

    print("== Commission (compiled from profile='read-only', re-targeted at Claude Code tools) ==")
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
                f"  [turn {ev.data.step}] cost=${ev.data.avp_cost_usd:.5f}  "
                f"tokens={ev.data.gen_ai_usage_input_tokens}+{ev.data.gen_ai_usage_output_tokens}"
            )
        elif type_name == "TextEmittedEvent":
            preview = ev.data.avp_text.replace("\n", " ")[:80]
            print(f"  [turn {ev.data.step}] text: {preview!r}")
        elif type_name == "ToolInvokedEvent":
            print(
                f"  [turn {ev.data.step}] -> {ev.data.gen_ai_tool_name}({list(ev.data.gen_ai_tool_call_arguments.keys())})"
            )
        elif type_name == "ToolReturnedEvent":
            head = ev.data.avp_tool_result_text.replace("\n", " ")[:60]
            print(f"  [turn {ev.data.step}] <- {ev.data.gen_ai_tool_name}: {head!r}...")
        elif type_name == "AgentStoppedEvent":
            print(f"  STOPPED reason={ev.data.avp_reason}")

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
    if str(stop.data.avp_reason) != "converged":
        issues.append(f"expected stop reason 'converged'; got {stop.data.avp_reason!r}")

    tool_invokes = [ev for ev in events if type(ev).__name__ == "ToolInvokedEvent"]
    if not tool_invokes:
        issues.append("no tool calls — agent should have used Read")
    elif not any(ev.data.gen_ai_tool_name == "Read" for ev in tool_invokes):
        issues.append(
            f"agent never called Read; called: {[ev.data.gen_ai_tool_name for ev in tool_invokes]}"
        )

    if "TextEmittedEvent" not in types:
        issues.append("no text_emitted events — agent didn't produce a response")

    # accounting_reset is a known SDK quirk (see avp-claude-agent README).
    # Any OTHER error_occurred is a real failure.
    errs = [ev for ev in events if type(ev).__name__ == "ErrorOccurredEvent"]
    unexpected = [ev for ev in errs if ev.data.avp_error_code.value != "accounting_reset"]
    if unexpected:
        issues.append(
            f"unexpected error_occurred (not accounting_reset): "
            f"{[(e.data.avp_error_code.value, e.data.avp_error_message[:80]) for e in unexpected]}"
        )

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
