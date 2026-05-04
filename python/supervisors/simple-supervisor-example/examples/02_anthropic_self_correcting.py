"""Example 02 — Self-correcting agent via inject_correction verifier (driver pattern).

Story: the supervisor wants the agent to write some Python but ALSO wants it to
not commit lazy `# TODO:` comments. A verifier on `on_tool:write_file` scans
the workspace for newly-introduced TODOs after every write; on_failure is
'inject_correction', so the agent receives a user-role message in its history
when it leaves a TODO and self-corrects on the next turn.

What you'll see:
  - At least one verifier_evaluated event with passed=false
  - Followed by a fresh model_turn_started where the agent reads the correction
  - A final file with no TODO comments

Verifier mechanism:
  - Trigger: on_tool:write_file (fires after each write_file tool_returned)
  - Source:  shell command that greps for new TODO lines in `git diff`
  - on_failure: inject_correction
  - correction_message: user-role text the runner injects into history

The supervisor doesn't reach in mid-run. It declared the rule in Config; the
runner enforces it deterministically. The trajectory records every check.

Requires:
  pip install -e python/aep -e python/runners/aep-anthropic \\
              -e python/supervisors/simple-supervisor-example
  export ANTHROPIC_API_KEY=...
  Run from a git working tree (so `git diff` works for the verifier).

Run:
  python examples/02_anthropic_self_correcting.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from simple_supervisor import build_config, render, stream_subprocess, summarize


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    # The runner's CWD will be the workspace. We give it a fresh tempdir so the
    # 'git diff' verifier has clean baseline to compare against. (In a real
    # supervisor, the deployment layer would provision this — see SPEC.md §14.)
    workspace = Path(tempfile.mkdtemp(prefix="aep-self-correct-"))
    os.system(f"cd {workspace} && git init -q && git commit -q --allow-empty -m init")

    target_file = workspace / "math_helpers.py"

    run_id = f"self-correcting-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    config = build_config(
        run_id=run_id,
        prompt=(
            f"Create the file {target_file} containing a Python function "
            "`safe_divide(a, b)` that returns a/b but returns 0.0 if b == 0. "
            "Include a one-line docstring. Then converge by saying DONE."
        ),
        profile="ddd-strict",
        model="claude-haiku-4-5-20251001",
        # Override the placeholder 'tests-pass' verifier with a no-op for this demo
        # (we don't have a real test suite in the tempdir).
        boundary_overrides={"max_steps": 8, "max_cost_usd": 0.10},
    )
    # Strip the placeholder tests-pass verifier; keep no-todos-in-writes.
    if config.verifiers:
        config = config.model_copy(
            update={"verifiers": [v for v in config.verifiers if v.name == "no-todos-in-writes"]}
        )

    print(f"== Workspace: {workspace} ==")
    print()
    print("== Config (compiled from profile='ddd-strict', stripped to one verifier) ==")
    print(config.model_dump_json(indent=2, exclude_none=True))
    print()
    print("== Live trajectory ==")

    events = []
    for ev in stream_subprocess(
        ["aep-anthropic"],
        config,
        cwd=str(workspace),
    ):
        events.append(ev)
        type_name = getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else "?")
        if type_name == "model_turn_ended":
            print(
                f"  [turn {ev.step}] cost=${ev.cost_usd:.5f}  tokens={ev.tokens_input}+{ev.tokens_output}"
            )
        elif type_name == "tool_invoked":
            print(f"  [turn {ev.step}] -> {ev.tool}({list(ev.input.keys())})")
        elif type_name == "verifier_evaluated":
            mark = "PASS" if ev.passed else "FAIL"
            print(f"  [turn {ev.step}] verifier '{ev.name}': {mark}")
            if not ev.passed and ev.data:
                stdout = ev.data.get("stdout", "").strip()
                if stdout:
                    print(f"      offending diff: {stdout[:120]}")
        elif type_name == "agent_stopped":
            print(f"  STOPPED reason={ev.reason}")

    print()
    print(render(summarize(events)))

    # Show what landed in the workspace
    if target_file.exists():
        print()
        print(f"== {target_file.name} (final contents) ==")
        print(target_file.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
