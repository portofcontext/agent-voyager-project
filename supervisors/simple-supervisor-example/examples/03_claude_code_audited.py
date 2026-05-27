"""Example 03 — Audited Claude Code session (observer pattern, avp-claude-agent-sdk).

Story: the user runs an existing Claude Code session (the Claude Agent SDK
owns its own loop) but the supervisor still wants the same observability and
the same Commission-declared environment they'd get from a driver-pattern agent.

What this example demonstrates:
  - The same Commission-building flow as example 01 — profile + overrides
  - Translation of Commission → ClaudeAgentOptions (done inside
    `AVPClaudeSDKClient`):
      Commission.enabled_builtin_tools → SDK's `tools` parameter
      Commission.system_prompt        → SDK's system_prompt
      Commission.model                → SDK's model
  - Claude Code hooks register AVP tool_invoked / tool_returned in step with
    the SDK's own dispatch
  - Same post-run summary as the driver examples

Requires:
  - The Claude Code CLI binary on PATH (the SDK shells out to it; not pure Python)
      npm install -g @anthropic-ai/claude-code
      claude /login
  - ANTHROPIC_API_KEY set in the environment
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import sys
from datetime import UTC, datetime

from simple_supervisor import build_commission, render, summarize

from avp.content import TextBlock


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2
    if importlib.util.find_spec("claude_agent_sdk") is None:
        print("error: install claude-agent-sdk (pip install claude-agent-sdk)", file=sys.stderr)
        return 2
    if shutil.which("claude") is None:
        print("error: install the Claude Code CLI; `claude` must be on PATH", file=sys.stderr)
        return 2

    from avp_claude_agent_sdk import AVPClaudeSDKClient

    run_id = f"claude-code-audit-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    # Tool names here are Claude Code's (Read / Write / Bash / Edit / Glob).
    # The supervisor narrows the surface to a read-only audit; the SDK enforces
    # it via the `tools` parameter AVPClaudeSDKClient passes through.
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

    async def sink(ev) -> None:
        events.append(ev)

    async def _run() -> None:
        async with AVPClaudeSDKClient(commission=config, sink=sink) as client:
            await client.query(config.prompt)
            async for _message in client.receive_response():
                pass

    asyncio.run(_run())

    for ev in events:
        type_name = type(ev).__name__
        if type_name == "AssistantMessageEvent":
            print(
                f"  [turn {ev.data.step}] cost=${ev.data.cost_usd:.5f}  "
                f"tokens={ev.data.usage.input_tokens}+{ev.data.usage.output_tokens}"
            )
            for block in ev.data.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    print(
                        f"  [turn {ev.data.step}] text: {block.text.replace(chr(10), ' ')[:80]!r}"
                    )
        elif type_name == "ToolInvokedEvent":
            print(
                f"  [turn {ev.data.step}] -> {ev.data.tool_name}({list(ev.data.tool_input.keys())})"
            )
        elif type_name == "ToolReturnedEvent":
            head = str(ev.data.tool_result.content).replace("\n", " ")[:60]
            print(f"  [turn {ev.data.step}] <- {ev.data.tool_name}: {head!r}...")
        elif type_name == "AgentStoppedEvent":
            print(f"  STOPPED reason={ev.data.reason}")

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
      - The agent produced some assistant text (it actually answered)
      - No error_occurred events
    """
    issues: list[str] = []

    stop = next((ev for ev in events if type(ev).__name__ == "AgentStoppedEvent"), None)
    if stop is None:
        issues.append("no agent_stopped event — run exited mid-trajectory")
        return issues
    if stop.data.reason.value != "converged":
        issues.append(f"expected stop reason 'converged'; got {stop.data.reason!r}")

    tool_invokes = [ev for ev in events if type(ev).__name__ == "ToolInvokedEvent"]
    if not tool_invokes:
        issues.append("no tool calls — agent should have used Read")
    elif not any(ev.data.tool_name == "Read" for ev in tool_invokes):
        issues.append(
            f"agent never called Read; called: {[ev.data.tool_name for ev in tool_invokes]}"
        )

    # Some assistant_message must carry visible text (the agent answered).
    msgs = [ev for ev in events if type(ev).__name__ == "AssistantMessageEvent"]
    has_text = any(
        isinstance(b, TextBlock) and b.text.strip() for ev in msgs for b in ev.data.content
    )
    if not has_text:
        issues.append("no assistant text — agent didn't produce a response")

    errs = [ev for ev in events if type(ev).__name__ == "ErrorOccurredEvent"]
    if errs:
        issues.append(
            f"error_occurred events present: "
            f"{[(e.data.error_code.value, e.data.error_message[:80]) for e in errs]}"
        )

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
