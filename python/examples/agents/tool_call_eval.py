"""Tool call eval — verify the agent used the right tools and produced expected output.

Runs the agent as a subprocess and reads its AEP event stream. The eval asserts:

  1. Bash was called  (tool_call event)
  2. The Bash result contains .py file paths  (tool_result event output)

Setup::

    cd python/runners/claude-agent-sdk && uv sync --extra dev

Usage::

    ANTHROPIC_API_KEY=... python python/examples/agents/tool_call_eval.py
    ANTHROPIC_API_KEY=... python python/examples/agents/tool_call_eval.py src/
"""

from __future__ import annotations

import asyncio
import sys

from claude_agent_sdk_aep import query          # ← only AEP change
from claude_agent_sdk import ClaudeAgentOptions


# ── agent ─────────────────────────────────────────────────────────────────────

async def run(target: str) -> None:
    async for _ in query(
        prompt=f"Use Bash to find all Python files under {target}. Exclude .venv directories.",
        options=ClaudeAgentOptions(
            model="claude-haiku-4-5-20251001",
            allowed_tools=["Bash"],
            permission_mode="acceptEdits",
        ),
    ):
        pass


# ── supervisor / eval ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.argv[1:2] == ["--agent"]:
        asyncio.run(run(sys.argv[2] if len(sys.argv) > 2 else "."))
    else:
        from claude_agent_sdk_aep import supervise

        target = next((a for a in sys.argv[1:] if not a.startswith("--")), ".")

        tools_called: list[str] = []
        tool_outputs: list[str] = []

        for event in supervise([sys.executable, __file__, "--agent", target]):
            t = event["type"]
            if t == "tool_call":
                tools_called.append(event["tool"])
                print(f"[tool]   {event['tool']}({str(event.get('input', ''))[:60]})")
            elif t == "tool_result":
                tool_outputs.append(event.get("output", ""))
            elif t == "agent_stop":
                print(f"[stop]   reason={event['reason']}  turns={event['total_turns']}  ${event['total_cost_usd']:.4f}")

        combined_output = "\n".join(tool_outputs)

        print("\n── eval ──────────────────────────────────────────────────────")

        # 1. Tool call assertion
        bash_called = "Bash" in tools_called
        print(f"{'✓' if bash_called else '✗'}  Bash tool was called  (called: {tools_called})")

        # 2. Tool result assertion — output contains .py file paths
        py_files = [line for line in combined_output.splitlines() if line.strip().endswith(".py")]
        has_py_files = len(py_files) > 0
        print(f"{'✓' if has_py_files else '✗'}  Bash result contains .py file paths  (found: {len(py_files)})")
        for f in py_files[:5]:
            print(f"   {f.strip()}")
        if len(py_files) > 5:
            print(f"   … and {len(py_files) - 5} more")

        passed = bash_called and has_py_files
        print(f"\n{'PASS' if passed else 'FAIL'}")
        sys.exit(0 if passed else 1)
