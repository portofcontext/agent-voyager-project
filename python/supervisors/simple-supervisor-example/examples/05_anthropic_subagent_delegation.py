"""Example 05 — Subagent delegation (driver pattern, avp-anthropic).

Story: a supervisor declares ONE subagent — a `summarizer` whose only job is to
turn a passage into 2 crisp bullets. The parent agent's task is to call the
summarizer once and report what it returned. Both agents run on Claude; the
agent emits a nested span tree so the supervisor can see the subagent's
internal turns interleaved with the parent's.

What you'll see on the wire:
  - `agent_started.data.subagents = [{name: 'summarizer', ...}]` — the model-
    facing subagent surface
  - `avp.subagent_invoked` (parent calls the subagent)
  - One or more `avp.model_turn_started` / `avp.model_turn_ended` whose
    `parent_span_id` chains through the subagent's frame span — these are
    the subagent's internal turns, observable IN-LINE on the parent's stream
  - `avp.text_emitted` from inside the subagent's frame
  - `avp.subagent_returned` carrying the subagent's text + a usage rollup
  - The parent's converging turn, `agent_stopped(reason=converged)`

Why this matters: every other multi-agent SDK exposes subagent activity in a
different shape (LangSmith nested runs, ADK dotted `branch`, Claude Agent SDK
opaque tool result). AVP gives consumers ONE wire shape: a span tree on the
event stream. The supervisor doesn't need provider-specific glue to reconstruct
who did what.

Requires:
  pip install -e python/avp -e python/agents/avp-anthropic \
              -e python/supervisors/simple-supervisor-example
  export ANTHROPIC_API_KEY=...

Run:
  python examples/05_anthropic_subagent_delegation.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from simple_supervisor import stream_subprocess

from avp import Commission, Subagent

WORKSPACE = Path(__file__).resolve().parent


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    run_id = f"subagent-delegation-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    passage = (
        "The Agent Voyage Protocol (AVP) draws one line, between two roles, and "
        "ships a wire format across that line. Supervisors declare the agent's complete "
        "environment in a Commission sent at startup; agents run the agent inside that "
        "environment and emit a stream of facts."
    )

    # Build the Commission directly. We bypass the profile builder because subagents
    # aren't yet a concern of the profile DSL — they're a Commission primitive.
    config = Commission(
        schema_version="0.1",
        run_id=run_id,
        model="claude-haiku-4-5-20251001",
        prompt=(
            "You have one task: call the `summarizer` subagent with the passage below "
            "and then report what it returned. Then say DONE.\n\n"
            f"PASSAGE:\n{passage}"
        ),
        subagents=[
            Subagent(
                name="summarizer",
                description=(
                    "Summarizes a passage as exactly 2 short bullet points. Input "
                    "shape: {prompt: <passage>}. Returns a 2-bullet summary."
                ),
                system_prompt=(
                    "You are a precise summarizer. Given a passage, produce exactly two "
                    "bullets, each ≤ 12 words. Output nothing else."
                ),
                model="claude-haiku-4-5-20251001",
                # The subagent's own turn budget — tight, since the job is small.
                # The parent's overall budget (set below) caps the whole run regardless.
            )
        ],
        allowed_tools=["summarizer"],  # parent agent can call ONLY the subagent
    )

    print(f"== Workspace (agent CWD): {WORKSPACE} ==")
    print()
    print("== Commission (subagent declared as a top-level primitive) ==")
    print(config.model_dump_json(indent=2, exclude_none=True, by_alias=True))
    print()
    print("== Live trajectory ==")

    events = []
    frame_span_by_invoke: dict[str, str] = {}
    for ev in stream_subprocess(["avp-anthropic"], config, cwd=str(WORKSPACE)):
        events.append(ev)
        type_name = getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else "?")

        if type_name == "avp.agent_started":
            sa_decls = ev.data.subagents or []
            names = [s.name for s in sa_decls]
            print(f"  agent_started — subagents on the wire: {names}")
        elif type_name == "avp.subagent_invoked":
            frame_span_by_invoke[ev.data.avp_subagent_invocation_id] = ev.data.span_id
            print(
                f"  -> subagent_invoked '{ev.data.gen_ai_agent_name}' "
                f"(invocation_id={ev.data.avp_subagent_invocation_id}, "
                f"frame_span={ev.data.span_id[:8]}…)"
            )
        elif type_name == "avp.model_turn_ended":
            # Mark whether this turn belonged to the parent or to a subagent
            # frame (parent_span_id chains through the frame span).
            parent_span = ev.data.parent_span_id
            inside_subagent = parent_span in frame_span_by_invoke.values()
            location = "subagent" if inside_subagent else "parent"
            print(
                f"     [{location} turn {ev.data.step}] "
                f"in={ev.data.gen_ai_usage_input_tokens} "
                f"out={ev.data.gen_ai_usage_output_tokens} "
                f"cost=${ev.data.avp_cost_usd:.5f}"
            )
        elif type_name == "avp.subagent_returned":
            head = ev.data.avp_subagent_result_text.replace("\n", " ")[:80]
            print(
                f"  <- subagent_returned '{ev.data.gen_ai_agent_name}' "
                f"reason={ev.data.avp_subagent_reason} "
                f"turns={ev.data.avp_subagent_usage.total_turns} "
                f"cost=${ev.data.avp_subagent_usage.total_cost_usd:.5f}"
            )
            print(f"     result: {head!r}")
        elif type_name == "avp.subagent_failed":
            print(
                f"  ✗ subagent_failed '{ev.data.gen_ai_agent_name}' "
                f"error={ev.data.avp_subagent_error!r}"
            )
        elif type_name == "avp.agent_stopped":
            print(
                f"  STOPPED reason={ev.data.avp_reason} "
                f"cost=${ev.data.avp_state.total_cost_usd:.5f} "
                f"tokens={ev.data.avp_state.total_tokens}"
            )

    print()
    issues = _validate_outcome(events)
    if issues:
        print("== ✗ FAIL — example 05 ==")
        for msg in issues:
            print(f"  - {msg}")
        return 1
    print("== ✓ PASS — example 05 ==")
    return 0


def _validate_outcome(events: list) -> list[str]:
    """PASS criteria: the supervisor saw exactly one subagent_invoked /
    returned pair (frame spans matched), the parent run converged, and the
    subagent's nested turns chained through the frame span (proves the
    span tree assembled correctly)."""
    issues: list[str] = []
    types = [type(ev).__name__ for ev in events]

    if "AgentStoppedEvent" not in types:
        issues.append("no agent_stopped — agent exited mid-trajectory")
        return issues

    invoked = [ev for ev in events if type(ev).__name__ == "SubagentInvokedEvent"]
    returned = [ev for ev in events if type(ev).__name__ == "SubagentReturnedEvent"]
    failed = [ev for ev in events if type(ev).__name__ == "SubagentFailedEvent"]

    if not invoked:
        issues.append("parent never invoked the subagent")
        return issues
    if failed:
        issues.append(
            f"subagent_failed events present: {[f.data.avp_subagent_error for f in failed]}"
        )
    if len(invoked) != len(returned):
        issues.append(
            f"unmatched subagent lifecycle: {len(invoked)} invoked / {len(returned)} returned"
        )

    if invoked and returned:
        if invoked[0].data.span_id != returned[0].data.span_id:
            issues.append("frame span_id MUST match across subagent_invoked / subagent_returned")
        frame = invoked[0].data.span_id
        nested_turns = [
            ev
            for ev in events
            if type(ev).__name__ == "ModelTurnStartedEvent" and ev.data.parent_span_id == frame
        ]
        if not nested_turns:
            issues.append(
                "no nested model_turn descended from the subagent's frame — "
                "AnthropicSubagentDriver didn't chain spans correctly"
            )

    stop = next(ev for ev in events if type(ev).__name__ == "AgentStoppedEvent")
    if str(stop.data.avp_reason) != "converged":
        issues.append(f"unexpected stop reason {stop.data.avp_reason!r}")

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
