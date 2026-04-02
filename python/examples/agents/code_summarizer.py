"""Code summarizer — summarize Python files in a directory.

The agent uses ``claude_agent_sdk_aep.query`` (one import change from the
plain SDK). The supervisor spawns it as a subprocess and pretty-prints events.

Setup::

    cd python/runners/claude-agent-sdk && uv sync --extra dev

Usage::

    ANTHROPIC_API_KEY=... python python/examples/agents/code_summarizer.py
    ANTHROPIC_API_KEY=... python python/examples/agents/code_summarizer.py src/
"""

from __future__ import annotations

import asyncio
import sys

from claude_agent_sdk_aep import query          # ← only AEP change
from claude_agent_sdk import ClaudeAgentOptions


# ── agent ─────────────────────────────────────────────────────────────────────

async def run(target: str) -> None:
    async for _ in query(
        prompt=(
            f"List the Python files under {target}. "
            "For each file show its path and a one-sentence description of what it does. "
            "Use Bash to find the files, then Read to inspect each one."
        ),
        options=ClaudeAgentOptions(
            model="claude-haiku-4-5-20251001",
            allowed_tools=["Bash", "Read"],
        ),
    ):
        pass


# ── supervisor ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.argv[1:2] == ["--agent"]:
        # ── agent entrypoint (spawned by supervisor below) ─────────────────
        asyncio.run(run(sys.argv[2] if len(sys.argv) > 2 else "."))
    else:
        # ── supervisor ──────────────────────────────────────────────────────
        from claude_agent_sdk_aep import supervise

        target = next((a for a in sys.argv[1:] if not a.startswith("--")), ".")

        for event in supervise([sys.executable, __file__, "--agent", target]):
            t = event["type"]
            if t == "agent_start":
                print(f"[start]  run_id={event['run_id'][:8]}  model={event['model']}")
            elif t == "tool_call":
                print(f"[tool]   {event['tool']}  {str(event.get('input', ''))[:60]}")
            elif t == "text_output":
                print(f"\n{event['text']}\n")
            elif t == "agent_stop":
                print(f"[stop]   reason={event['reason']}  turns={event['total_turns']}  ${event['total_cost_usd']:.4f}")
