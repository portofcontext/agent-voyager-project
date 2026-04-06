"""Tool call eval — verify the agent called a supervisor-declared tool.

The supervisor declares a ``get_project_info`` tool in an AEP config and passes
it to the runner as a subprocess. When the model calls the tool, the runner
emits a ``tool_exec_request`` event; the supervisor executes the function
locally and writes a ``tool_exec_result`` back over stdin.

The eval asserts:

  1. ``tool_exec_request`` was emitted for ``get_project_info``
  2. ``tool_exec_applied`` was emitted (result consumed without timeout)
  3. Bash was also called

Setup::

    cd python/runners/claude-agent-sdk && uv sync --extra dev

Usage::

    ANTHROPIC_API_KEY=... python ../../examples/agents/tool_call_eval.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from agent_execution_protocol import AepConfig, AepTool


# ── Supervisor-side tool implementations ──────────────────────────────────────


def get_project_info(_) -> str:
    """Called locally by the supervisor when the model requests project metadata."""
    return json.dumps(
        {
            "name": "agent-execution-protocol",
            "description": "Open standard for agent observability",
            "language": "Python",
        }
    )


TOOL_HANDLERS: dict = {
    "get_project_info": get_project_info,
}


# ── AEP config (supervisor declares the tool) ─────────────────────────────────

CONFIG = AepConfig(
    run_id="tool-call-eval",
    model="anthropic/claude-haiku-4-5-20251001",
    prompt=(
        "Call get_project_info to learn about this project. "
        "Then use Bash to count Python files (exclude .venv). "
        "Report: '<project name> has <N> Python files.'"
    ),
    tools=[
        AepTool(
            name="get_project_info",
            description="Returns metadata about this project (name, description, language).",
            input_schema={"type": "object", "properties": {}},
        ),
    ],
)


# ── Agent (runner reads config from stdin) ────────────────────────────────────

if __name__ == "__main__":
    if sys.argv[1:2] == ["--agent"]:
        from claude_agent_sdk_aep import run_from_stdin

        run_from_stdin()

    # ── Supervisor ────────────────────────────────────────────────────────────

    else:
        tool_exec_requests: list[dict] = []
        tool_exec_applied: list[dict] = []
        tools_called: list[str] = []

        proc = subprocess.Popen(
            [sys.executable, __file__, "--agent"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=os.environ.copy(),
        )

        # Send AEP config as line 1 of stdin
        proc.stdin.write(json.dumps(CONFIG.to_dict()) + "\n")
        proc.stdin.flush()

        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            t = event["type"]

            if t == "agent_start":
                print(f"[start]  run_id={event['run_id'][:8]}  model={event['model']}")
            elif t == "tool_call":
                tools_called.append(event["tool"])
                print(f"[call]   {event['tool']}({str(event.get('input', ''))[:60]})")
            elif t == "tool_result":
                print(f"[result] {event['tool']} → {str(event.get('output', ''))[:80]}")
            elif t == "tool_exec_request":
                tool_exec_requests.append(event)
                tool_name = event["tool"]
                print(f"[exec]   supervisor executing {tool_name}")

                handler = TOOL_HANDLERS.get(tool_name)
                output = (
                    handler(event.get("input", {}))
                    if handler
                    else f"Unknown tool: {tool_name}"
                )

                proc.stdin.write(
                    json.dumps(
                        {
                            "type": "tool_exec_result",
                            "run_id": event["run_id"],
                            "call_id": event["call_id"],
                            "output": output,
                            "ts": datetime.now(timezone.utc)
                            .isoformat()
                            .replace("+00:00", "Z"),
                        }
                    )
                    + "\n"
                )
                proc.stdin.flush()
            elif t == "tool_exec_applied":
                tool_exec_applied.append(event)
                print(
                    f"[exec]   applied {event['tool']} timed_out={event.get('timed_out', False)}"
                )
            elif t == "text_output":
                print(f"\n{event['text'][:200]}\n")
            elif t == "agent_stop":
                print(
                    f"[stop]   reason={event['reason']}  turns={event['total_turns']}  ${event['total_cost_usd']:.4f}"
                )

        proc.wait()

        print("\n── eval ──────────────────────────────────────────────────────")

        has_exec_request = any(
            e["tool"] == "get_project_info" for e in tool_exec_requests
        )
        has_exec_applied = any(
            e["tool"] == "get_project_info" and not e.get("timed_out")
            for e in tool_exec_applied
        )
        bash_called = "Bash" in tools_called

        print(
            f"{'✓' if has_exec_request else '✗'}  tool_exec_request emitted for get_project_info"
        )
        print(
            f"{'✓' if has_exec_applied else '✗'}  tool_exec_applied emitted (timed_out=False)"
        )
        print(f"{'✓' if bash_called else '✗'}  Bash also called")

        passed = has_exec_request and has_exec_applied and bash_called
        print(f"\n{'PASS' if passed else 'FAIL'}")
        sys.exit(0 if passed else 1)
