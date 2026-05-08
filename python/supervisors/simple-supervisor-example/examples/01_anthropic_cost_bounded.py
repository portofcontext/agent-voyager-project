"""Example 01 — Cost-bounded inspection (driver pattern, avp-anthropic).

Story: a code-explanation agent with a tiny budget. The supervisor cares about
ONE thing: not letting it run away with cost. Profile = `read-only`
(allowed_tools=[read_file], max_cost_usd=$0.05, max_steps=3).

What you'll see:
  - The Commission the supervisor compiled (printed as JSON before launch)
  - Live trajectory: each event as it streams from avp-anthropic's stdout
  - Post-run summary (what the agent did / cost)
  - agent_stopped reason — usually 'converged' for short tasks

Requires:
  pip install -e python/avp -e python/agents/avp-anthropic \\
              -e python/supervisors/simple-supervisor-example
  export ANTHROPIC_API_KEY=...

Run:
  python examples/01_anthropic_cost_bounded.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from simple_supervisor import build_commission, render, stream_subprocess, summarize

# Workspace the agent subprocess will see as CWD. The supervisor's deployment
# layer picks this; we point it at this examples/ directory so the agent's
# relative file path below resolves against a known location.
WORKSPACE = Path(__file__).resolve().parent


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    run_id = f"read-only-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    config = build_commission(
        run_id=run_id,
        prompt=(
            "Use the read_file tool to read 01_anthropic_cost_bounded.py and explain "
            "in 3 sentences what the supervisor in that file is gating against. End "
            "your reply with the phrase 'EXPLANATION DONE.'"
        ),
        profile="read-only",
        model="claude-haiku-4-5-20251001",
    )

    print(f"== Workspace (agent CWD): {WORKSPACE} ==")
    print()
    print("== Commission (compiled from profile='read-only') ==")
    print(config.model_dump_json(indent=2, exclude_none=True))
    print()
    print("== Live trajectory ==")

    events = []
    for ev in stream_subprocess(["avp-anthropic"], config, cwd=str(WORKSPACE)):
        events.append(ev)
        # One-line preview of each event as it arrives
        type_name = getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else "?")
        if type_name == "model_turn_ended":
            print(
                f"  [turn {ev.data.step}] tokens_in={ev.data.gen_ai_usage_input_tokens} tokens_out={ev.data.gen_ai_usage_output_tokens} "
                f"cost=${ev.data.avp_cost_usd:.5f}"
            )
        elif type_name == "tool_invoked":
            print(
                f"  [turn {ev.data.step}] -> {ev.data.gen_ai_tool_name}({list(ev.data.gen_ai_tool_call_arguments.keys())})"
            )
        elif type_name == "tool_returned":
            head = ev.data.avp_tool_result_text.replace("\n", " ")[:60]
            print(f"  [turn {ev.data.step}] <- {ev.data.gen_ai_tool_name}: {head!r}...")
        elif type_name == "agent_stopped":
            print(f"  STOPPED reason={ev.data.avp_reason}")

    print()
    print(render(summarize(events)))

    issues = _validate_outcome(events)
    print()
    if issues:
        print("== ✗ FAIL — example 01 ==")
        for msg in issues:
            print(f"  - {msg}")
        return 1
    print("== ✓ PASS — example 01 ==")
    return 0


def _validate_outcome(events: list) -> list[str]:
    """Post-conditions for example 01. LLM trajectory varies; outcomes don't.

    PASS criteria:
      - Run terminated with reason=converged
      - At least one tool call was made (and it was read_file, the only
        allowed tool)
      - No error_occurred events
    """
    issues: list[str] = []
    types = [type(ev).__name__ for ev in events]

    if "AgentStoppedEvent" not in types:
        issues.append("no agent_stopped event — agent exited mid-trajectory")
        return issues

    stop = next(ev for ev in events if type(ev).__name__ == "AgentStoppedEvent")
    accepted_reasons = {"converged"}
    if str(stop.data.avp_reason) not in accepted_reasons:
        issues.append(
            f"unexpected stop reason {stop.data.avp_reason!r}; expected one of {accepted_reasons}"
        )

    tool_invokes = [ev for ev in events if type(ev).__name__ == "ToolInvokedEvent"]
    if not tool_invokes:
        issues.append("no tool calls — agent should have used read_file")
    else:
        wrong = [
            ev.data.gen_ai_tool_name
            for ev in tool_invokes
            if ev.data.gen_ai_tool_name != "read_file"
        ]
        if wrong:
            issues.append(f"agent called disallowed tools (allowed_tools=[read_file]): {wrong}")

    if "ErrorOccurredEvent" in types:
        errs = [ev for ev in events if type(ev).__name__ == "ErrorOccurredEvent"]
        issues.append(f"error_occurred events present: {[e.data.avp_error_message for e in errs]}")

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
