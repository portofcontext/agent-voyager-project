"""Example 05 — Managed-subagent delegation via the AVP resolver protocol.

Story: a supervisor declares ONE managed subagent — a `summarizer` whose
job is to turn a passage into a couple of bullets. The Commission carries
just an opaque ref for the subagent; an in-process `ScriptedResolver`
stands in for what a production supervisor would wire as an HTTP service
(per SPEC.md §6). The parent agent runs against Claude, calls
`avp.spawn_subagent` when the model invokes the subagent, and emits the
expected lifecycle on the wire.

What you'll see on the wire:
  - `agent_described.data["avp.manifest"]` — the agent's whoami
  - `agent_started.data.subagents = [{name: "summarizer"}]` — id-only
    stub (descriptions arrive via `managed_ref_resolved`)
  - `managed_ref_resolved` (for the subagent ref) before any model turn
  - One or more `model_turn_*` from the parent's loop
  - `subagent_invoked` carrying `avp.subagent.run_id` = the child run
  - `subagent_returned` carrying the inline summary the resolver returned
  - The parent's converging turn, `agent_stopped(reason=converged)`

Why this matters: managed-subagent dispatch is supervisor-mediated. The
parent agent doesn't run a sub-loop in-process — it asks the resolver to
spawn the subagent. The wire shape stays the same as if the subagent ran
in-process (subagent_invoked → subagent_returned), but with
`avp.subagent.run_id` letting consumers correlate the parent and child
trajectories.

Requires ANTHROPIC_API_KEY (the parent run hits real Claude).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from simple_supervisor import render, summarize

from avp import Commission, SubagentRef
from avp.agent import AVPAgent
from avp.agent.mock import ScriptedResolver, ScriptedSupervisor
from avp_anthropic import (
    SHELL_TOOL_SCHEMAS,
    AnthropicModelDriver,
    build_anthropic_tools,
    manifest,
)
from avp_anthropic.shell_tools import ShellTools


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    run_id = f"subagent-delegation-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    commission = Commission(
        schema_version="0.1",
        run_id=run_id,
        model="claude-haiku-4-5-20251001",
        system_prompt=(
            "You are a delegating agent. Call the `summarizer` subagent ONCE "
            "with a short passage, then report what it returned. End with 'DONE'."
        ),
        prompt=(
            "Summarize this for me: 'Async I/O lets a single thread interleave "
            "multiple network requests by yielding while waiting for bytes, so "
            "you get throughput without the memory cost of one OS thread per "
            "in-flight request.' Use the summarizer subagent."
        ),
        subagents=[SubagentRef(id="summarizer", ref="example-05/summarizer/v1")],
    )

    # In production the supervisor stands up a resolver service and sets
    # AVP_RESOLVER_URL on the agent's environment; the CLI dials it via
    # HttpResolver. For this example we wire a ScriptedResolver directly
    # so the demonstration doesn't require a live service.
    resolver = ScriptedResolver(
        resolutions={
            "subagent:summarizer": {
                "result": {
                    "name": "summarizer",
                    "description": "Compresses a passage into 2 short bullets.",
                }
            }
        },
        subagent_spawns={
            "summarizer": {
                "child_run_id": f"sub-{run_id}-summarizer-1",
                "text": "- Async I/O interleaves requests on one thread.\n- Saves the memory cost of one OS thread per in-flight request.",
                "reason": "converged",
                "duration_ms": 75,
                "usage": {"total_cost_usd": 0.0006, "total_tokens": 95, "total_turns": 1},
            }
        },
    )

    events: list = []

    driver = AnthropicModelDriver(
        model=commission.model,
        tools_param=build_anthropic_tools(commission, builtins=list(SHELL_TOOL_SCHEMAS)) or None,
        max_tokens=400,
    )

    agent = AVPAgent(
        commission=commission,
        model=driver,
        tools=ShellTools(),
        supervisor=ScriptedSupervisor(),
        agent_builtin_tools=list(SHELL_TOOL_SCHEMAS),
        resolver=resolver,
        manifest=manifest(),
        on_event=events.append,
    )
    agent.run()

    print(f"== Run {run_id} ==")
    for ev in events:
        type_name = type(ev).__name__
        if type_name == "ManagedRefResolvedEvent":
            print(f"  resolved {ev.data.avp_managed_kind}:{ev.data.avp_managed_id}")
        elif type_name == "ModelTurnEndedEvent":
            print(
                f"  [turn {ev.data.step}] cost=${ev.data.avp_cost_usd:.5f} "
                f"tokens={ev.data.gen_ai_usage_input_tokens}+{ev.data.gen_ai_usage_output_tokens}"
            )
        elif type_name == "SubagentInvokedEvent":
            print(
                f"  -> subagent invoked: {ev.data.gen_ai_agent_name} "
                f"(child run_id={ev.data.avp_subagent_run_id})"
            )
        elif type_name == "SubagentReturnedEvent":
            preview = ev.data.avp_subagent_result_text.replace("\n", " ")[:80]
            print(f"  <- subagent returned: {preview!r}")
        elif type_name == "TextEmittedEvent":
            preview = ev.data.avp_text.replace("\n", " ")[:120]
            print(f"  [turn {ev.data.step}] text: {preview!r}")
        elif type_name == "AgentStoppedEvent":
            print(f"  STOPPED reason={ev.data.avp_reason}")

    print()
    print(render(summarize(events)))

    issues = _validate_outcome(events)
    print()
    if issues:
        print("== ✗ FAIL — example 05 ==")
        for msg in issues:
            print(f"  - {msg}")
        return 1
    print("== ✓ PASS — example 05 ==")
    return 0


def _validate_outcome(events: list) -> list[str]:
    issues: list[str] = []
    types = [type(ev).__name__ for ev in events]

    if "ManagedRefResolvedEvent" not in types:
        issues.append("expected managed_ref_resolved for the subagent ref")

    invoked = [ev for ev in events if type(ev).__name__ == "SubagentInvokedEvent"]
    returned = [ev for ev in events if type(ev).__name__ == "SubagentReturnedEvent"]
    if not invoked:
        issues.append("subagent_invoked never fired — model didn't call the summarizer")
    if not returned:
        issues.append("subagent_returned never fired")
    if invoked and not invoked[0].data.avp_subagent_run_id:
        issues.append(
            "subagent_invoked missing avp.subagent.run_id (managed subagent should carry it)"
        )
    if invoked and returned and invoked[0].data.span_id != returned[0].data.span_id:
        issues.append("subagent_invoked/returned span_ids don't pair")

    stop = next((ev for ev in events if type(ev).__name__ == "AgentStoppedEvent"), None)
    if stop is None:
        issues.append("no agent_stopped event")
    elif str(stop.data.avp_reason) != "converged":
        issues.append(f"expected stop=converged; got {stop.data.avp_reason!r}")

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
