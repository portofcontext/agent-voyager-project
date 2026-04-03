"""Skill demo — run an Anthropic Agent Skill and observe skill_read / skill_execute events.

The agent is asked to create a simple spreadsheet using the ``xlsx`` skill.
The supervisor watches the AEP event stream and asserts that:

  1. A ``skill_read`` event was emitted at startup (skill loaded)
  2. A ``skill_execute`` event was emitted (skill was invoked)

This requires the Anthropic Skills beta.  The runner automatically sets the
``skills-2025-10-02`` beta flag and passes a persistent container when skills
are provided.

Setup::

    cd python/runners/anthropic-sdk && uv sync --extra dev

Usage::

    ANTHROPIC_API_KEY=... python python/examples/agents/skill_demo.py
"""

from __future__ import annotations

import asyncio
import sys

from anthropic_aep import query


# ── skills ───────────────────────────────────────────────────────────────────

SKILLS = [
    {"type": "anthropic", "skill_id": "xlsx", "version": "latest"},
]

PROMPT = (
    "Create a simple spreadsheet with three columns: Name, Role, Start Date. "
    "Add three example rows of employee data."
)


# ── agent ────────────────────────────────────────────────────────────────────

async def run() -> None:
    async for _ in query(
        prompt=PROMPT,
        model="claude-sonnet-4-6",
        skills=SKILLS,
    ):
        pass


# ── supervisor / eval ────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.argv[1:2] == ["--agent"]:
        asyncio.run(run())
    else:
        from anthropic_aep import supervise

        skill_reads: list[dict] = []
        skill_executes: list[dict] = []

        for event in supervise([sys.executable, __file__, "--agent"]):
            t = event["type"]
            if t == "agent_start":
                print(f"[start]  run_id={event['run_id'][:8]}  model={event['model']}")
            elif t == "skill_read":
                skill_reads.append(event)
                print(f"[skill]  loaded {event['name']} (source={event.get('source')})")
            elif t == "skill_execute":
                skill_executes.append(event)
                print(f"[skill]  executed {event['name']} at step {event['step']}")
            elif t == "tool_call":
                print(f"[call]   {event['tool']}({str(event.get('input', ''))[:80]})")
            elif t == "tool_result":
                print(f"[result] {event['tool']} → {event.get('output', '')[:60]}")
            elif t == "text_output":
                print(f"\n{event['text'][:200]}\n")
            elif t == "agent_stop":
                print(
                    f"[stop]   reason={event['reason']}  turns={event['total_turns']}  ${event['total_cost_usd']:.4f}"
                )

        print("\n── eval ──────────────────────────────────────────────────────")

        # 1. skill_read emitted at startup
        read_names = [e["name"] for e in skill_reads]
        has_read = "xlsx" in read_names
        print(f"{'✓' if has_read else '✗'}  skill_read emitted for xlsx")

        # 2. skill_execute emitted during run
        exec_names = [e["name"] for e in skill_executes]
        has_exec = len(exec_names) > 0
        print(f"{'✓' if has_exec else '✗'}  skill_execute emitted  ({exec_names or '–'})")

        passed = has_read and has_exec
        print(f"\n{'PASS' if passed else 'FAIL'}")
        sys.exit(0 if passed else 1)
