"""Example 01 — Cost-bounded inspection (driver pattern, aep-anthropic).

Story: a code-explanation agent with a tiny budget. The supervisor cares about
ONE thing: not letting it run away with cost. Profile = `cost-bounded`
(allowed_tools=[read_file], max_cost_usd=$0.05, max_steps=3).

What you'll see:
  - The Config the supervisor compiled (printed as JSON before launch)
  - Live trajectory: each event as it streams from aep-anthropic's stdout
  - Post-run summary in three classes (what the agent did / rules / cost)
  - agent_stopped reason — usually 'converged' for short tasks, 'budget_exhausted'
    or 'turn_limit' if the agent overshoots

Requires:
  pip install -e python/aep -e python/runners/aep-anthropic \\
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

from simple_supervisor import build_config, render, stream_subprocess, summarize

# Workspace the runner subprocess will see as CWD. The supervisor's deployment
# layer picks this; we point it at this examples/ directory so the agent's
# relative file path below resolves against a known location.
WORKSPACE = Path(__file__).resolve().parent


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    run_id = f"cost-bounded-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    config = build_config(
        run_id=run_id,
        prompt=(
            "Use the read_file tool to read 01_anthropic_cost_bounded.py and explain "
            "in 3 sentences what the supervisor in that file is gating against. End "
            "your reply with the phrase 'EXPLANATION DONE.'"
        ),
        profile="cost-bounded",
        model="claude-haiku-4-5-20251001",
    )

    print(f"== Workspace (runner CWD): {WORKSPACE} ==")
    print()
    print("== Config (compiled from profile='cost-bounded') ==")
    print(config.model_dump_json(indent=2, exclude_none=True))
    print()
    print("== Live trajectory ==")

    events = []
    for ev in stream_subprocess(["aep-anthropic"], config, cwd=str(WORKSPACE)):
        events.append(ev)
        # One-line preview of each event as it arrives
        type_name = getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else "?")
        if type_name == "model_turn_ended":
            print(
                f"  [turn {ev.step}] tokens_in={ev.tokens_input} tokens_out={ev.tokens_output} "
                f"cost=${ev.cost_usd:.5f}"
            )
        elif type_name == "tool_invoked":
            print(f"  [turn {ev.step}] -> {ev.tool}({list(ev.input.keys())})")
        elif type_name == "tool_returned":
            head = ev.output.replace("\n", " ")[:60]
            print(f"  [turn {ev.step}] <- {ev.tool}: {head!r}...")
        elif type_name == "agent_stopped":
            print(f"  STOPPED reason={ev.reason}")

    print()
    print(render(summarize(events)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
