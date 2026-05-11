"""Example 10 — Audited OpenAI Agents SDK session (observer pattern, avp-openai-agent).

Story: the user runs an existing OpenAI Agents SDK session (the SDK
owns its own loop and RunHooks lifecycle) but the supervisor still wants
the same observability and the same Commission-declared environment they'd
get from a driver-pattern agent.

What this example demonstrates:
  - The same Commission-building flow as example 01 / 03 — profile + overrides
  - Translation of Commission → OpenAI Agents SDK constructor args:
      Commission.system_prompt → Agent.instructions
      Commission.model         → Agent.model
      Commission.prompt        → Runner.run input
  - The translator subclasses agents.RunHooks; the SDK calls back into our
    on_llm_start / on_llm_end / on_agent_end hooks and AVP events flow on
    the wire in step
  - Same post-run summary as the driver examples

Requires:
  - `openai-agents` Python package (pip install openai-agents)
  - OPENAI_API_KEY set in the environment
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import UTC, datetime

from avp_openai_agent import OpenAIAgentTranslator, descriptor
from simple_supervisor import build_commission, render, summarize


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("error: set OPENAI_API_KEY before running this example", file=sys.stderr)
        return 2
    if importlib.util.find_spec("agents") is None:
        print(
            "error: openai-agents not installed (pip install openai-agents)",
            file=sys.stderr,
        )
        return 2

    run_id = f"openai-agents-audit-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    # No hosted tools enabled: the smoke prompt is text-only so the run
    # stays cheap (well under $0.01 on gpt-5-nano). Supervisors who want
    # web_search / file_search / etc. enable them via
    # enabled_builtin_tools=[...] on the Commission.
    config = build_commission(
        run_id=run_id,
        prompt=(
            "Greet the user with the single word 'hello', then explain in "
            "one short sentence what the AVP wire format is for. End with 'DONE'."
        ),
        profile="read-only",
        model="gpt-5-nano",
    ).model_copy(update={"enabled_builtin_tools": []})

    print("== Commission (compiled from profile='read-only', re-targeted at OpenAI Agents SDK) ==")
    print(config.model_dump_json(indent=2, exclude_none=True))
    print()
    print("== Live trajectory ==")

    events: list = []
    translator = OpenAIAgentTranslator(
        config,
        on_event=events.append,
        descriptor=descriptor(),
    )
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
        elif type_name == "ReasoningEmittedEvent":
            preview = (ev.data.avp_reasoning_text or "<redacted>").replace("\n", " ")[:60]
            print(f"  [turn {ev.data.step}] reasoning: {preview!r}")
        elif type_name == "ToolInvokedEvent":
            print(f"  [turn {ev.data.step}] -> {ev.data.gen_ai_tool_name}")
        elif type_name == "ToolReturnedEvent":
            head = (ev.data.avp_tool_result_text or "").replace("\n", " ")[:60]
            print(f"  [turn {ev.data.step}] <- {ev.data.gen_ai_tool_name}: {head!r}...")
        elif type_name == "AgentStoppedEvent":
            print(f"  STOPPED reason={ev.data.avp_reason}")

    print()
    print(render(summarize(events)))

    issues = _validate_outcome(events)
    print()
    if issues:
        print("== ✗ FAIL — example 10 ==")
        for msg in issues:
            print(f"  - {msg}")
        return 1
    print("== ✓ PASS — example 10 ==")
    return 0


def _validate_outcome(events: list) -> list[str]:
    """Post-conditions for example 10. LLM trajectory varies; outcomes don't.

    PASS criteria:
      - Run converged
      - At least one model turn happened
      - Some text was emitted (the agent actually answered)
      - No unexpected error_occurred events
    """
    issues: list[str] = []
    types = [type(ev).__name__ for ev in events]

    stop = next((ev for ev in events if type(ev).__name__ == "AgentStoppedEvent"), None)
    if stop is None:
        issues.append("no agent_stopped event — translator exited mid-trajectory")
        return issues
    if str(stop.data.avp_reason) != "converged":
        issues.append(f"expected stop reason 'converged'; got {stop.data.avp_reason!r}")

    if "ModelTurnEndedEvent" not in types:
        issues.append("no model_turn_ended — translator never saw an LLM call")

    if "TextEmittedEvent" not in types:
        issues.append("no text_emitted events — agent didn't produce a response")

    errs = [ev for ev in events if type(ev).__name__ == "ErrorOccurredEvent"]
    if errs:
        issues.append(
            f"unexpected error_occurred: "
            f"{[(e.data.avp_error_code.value, e.data.avp_error_message[:80]) for e in errs]}"
        )

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
