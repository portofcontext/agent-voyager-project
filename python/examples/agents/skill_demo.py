"""Tool-call eval — define a tool, run it through the agent, assert on structured output.

The agent is asked to analyse a short text and call a ``record_findings``
tool with structured output (topic, sentiment, key_points).  The supervisor
collects the tool_call events and asserts that:

  1. The tool was invoked  (tool_call event)
  2. The call contained all required structured fields
  3. ``sentiment`` is one of the expected enum values

Note: ``skill_execute`` events are intentionally absent here because
``record_findings`` is a user-defined tool, not an Anthropic Agent Skill
(those run via ``container.skills`` with the ``skills-2025-10-02`` beta and
emit ``skill_execute`` when a ``server_tool_use`` block appears in the stream).

Setup::

    cd python/runners/anthropic-sdk && uv sync --extra dev

Usage::

    ANTHROPIC_API_KEY=... python python/examples/agents/skill_demo.py
"""

from __future__ import annotations

import asyncio
import sys

from anthropic_aep import query


# ── tool definition (standard Anthropic SDK tool format) ──────────────────────

TOOLS = [
    {
        "name": "record_findings",
        "description": (
            "Record the findings from your analysis. "
            "Call this exactly once when you have completed your analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The main topic or subject of the text",
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "negative", "neutral", "mixed"],
                    "description": "Overall sentiment of the text",
                },
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 2-4 key points from the text",
                },
            },
            "required": ["topic", "sentiment", "key_points"],
        },
    }
]

TEXT_TO_ANALYSE = (
    "The new renewable energy initiative has been met with widespread enthusiasm. "
    "Local communities are embracing solar installations, and early data shows a "
    "35% reduction in carbon emissions across participating neighbourhoods. "
    "Critics note that costs remain high for lower-income households."
)

PROMPT = (
    f"Analyse the following text and call record_findings with your structured assessment:\n\n"
    f"{TEXT_TO_ANALYSE}"
)


# ── agent ─────────────────────────────────────────────────────────────────────


async def run() -> None:
    async for _ in query(
        prompt=PROMPT,
        model="claude-haiku-4-5-20251001",
        tools=TOOLS,
        tool_handlers={
            "record_findings": lambda inp: f"Recorded: {inp.get('sentiment')}"
        },
    ):
        pass


# ── supervisor / eval ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.argv[1:2] == ["--agent"]:
        asyncio.run(run())
    else:
        from anthropic_aep import supervise

        tool_inputs: dict[str, dict] = {}

        for event in supervise([sys.executable, __file__, "--agent"]):
            t = event["type"]
            if t == "agent_start":
                print(f"[start]  run_id={event['run_id'][:8]}  model={event['model']}")
            elif t == "tool_call":
                tool_inputs[event["tool"]] = event.get("input", {})
                print(f"[call]   {event['tool']}({str(event.get('input', ''))[:80]})")
            elif t == "tool_result":
                print(f"[result] {event['tool']} → {event.get('output', '')[:60]}")
            elif t == "text_output":
                print(f"\n{event['text']}\n")
            elif t == "agent_stop":
                print(
                    f"[stop]   reason={event['reason']}  turns={event['total_turns']}  ${event['total_cost_usd']:.4f}"
                )

        print("\n── eval ──────────────────────────────────────────────────────")

        # 1. Tool was invoked
        tool_called = "record_findings" in tool_inputs
        print(f"{'✓' if tool_called else '✗'}  record_findings tool was called")

        # 2. All required structured fields present and valid
        finding = tool_inputs.get("record_findings", {})
        has_topic = isinstance(finding.get("topic"), str) and len(finding["topic"]) > 0
        has_sentiment = finding.get("sentiment") in (
            "positive",
            "negative",
            "neutral",
            "mixed",
        )
        has_key_points = (
            isinstance(finding.get("key_points"), list)
            and len(finding["key_points"]) >= 1
        )

        print(
            f"{'✓' if has_topic else '✗'}  topic present  ({finding.get('topic', '–')!r})"
        )
        print(
            f"{'✓' if has_sentiment else '✗'}  sentiment valid  ({finding.get('sentiment', '–')!r})"
        )
        print(
            f"{'✓' if has_key_points else '✗'}  key_points present  ({len(finding.get('key_points', []))} items)"
        )

        if has_key_points:
            for pt in finding["key_points"]:
                print(f"   • {pt}")

        passed = tool_called and has_topic and has_sentiment and has_key_points
        print(f"\n{'PASS' if passed else 'FAIL'}")
        sys.exit(0 if passed else 1)
