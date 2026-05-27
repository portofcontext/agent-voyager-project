"""Example 05: in-process subagent delegation.

A parent agent runs against Claude through `AnthropicTracedClient`. It
exposes one tool, `summarize`. When the model calls it, the example
delegates to a "summarizer" subagent: a second, focused model call,
bracketed on the wire by `subagent_invoked` / `subagent_returned` via
`client.subagent(...)`. The summary comes back as the tool result, the
parent reports it, and the run converges.

What you'll see on the wire:
  - `run_requested` + `agent_started` (the prelude)
  - `assistant_message` for the parent's turn that calls `summarize`
  - `subagent_invoked` -> `subagent_returned` (span-paired) around the
    summarizer sub-call
  - `tool_returned` carrying the summary back to the parent
  - the parent's converging turn, `agent_stopped(reason=converged)`

Note: v0.1 dropped the resolver-managed subagent path (a subagent with a
separate child `run_id`, dereferenced from a Commission ref); that is
tracked in the conformance COVERAGE notes. This example shows the IN-PROCESS
shape, which is what the wire records either way: `subagent_invoked` ->
`subagent_returned`, span-paired.

Requires ANTHROPIC_API_KEY (both the parent and summarizer hit real Claude).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import anthropic
from simple_supervisor import render, summarize

from avp.commission import Commission
from avp_anthropic import AnthropicTracedClient, print_event

_SUMMARIZE_TOOL = {
    "name": "summarize",
    "description": "Delegate a passage to the summarizer subagent. Returns 2 short bullets.",
    "input_schema": {
        "type": "object",
        "required": ["passage"],
        "properties": {"passage": {"type": "string", "description": "Text to summarize."}},
    },
}


def _run_summarizer(raw: anthropic.Anthropic, model: str, passage: str) -> str:
    """The subagent: a focused, untraced sub-call. (Untraced so it doesn't
    emit a parent-level assistant_message; the subagent_* pair is the wire
    record of this delegation.)"""
    resp = raw.messages.create(
        model=model,
        max_tokens=200,
        system="You compress a passage into exactly 2 short bullet points. Output only the bullets.",
        messages=[{"role": "user", "content": passage}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    run_id = f"subagent-delegation-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    model = "claude-haiku-4-5-20251001"
    commission = Commission(
        schema_version="0.1",
        run_id=run_id,
        model=model,
        system_prompt=(
            "You are a delegating agent. Call the `summarize` tool ONCE with the "
            "passage the user gives you, then report the bullets it returns. End with 'DONE'."
        ),
        prompt=(
            "Summarize this: 'Async I/O lets a single thread interleave multiple "
            "network requests by yielding while waiting for bytes, so you get "
            "throughput without the memory cost of one OS thread per in-flight request.'"
        ),
    )

    events: list = []

    def on_event(ev) -> None:
        events.append(ev)
        print_event(ev)

    with AnthropicTracedClient(
        anthropic.Anthropic(), commission=commission, on_event=on_event
    ) as client:
        msgs: list[dict] = [{"role": "user", "content": commission.prompt}]
        for _ in range(6):
            resp = client.messages.create(
                model=model,
                max_tokens=400,
                system=commission.system_prompt,
                messages=msgs,
                tools=[_SUMMARIZE_TOOL],
            )

            assistant_blocks: list = []
            tool_uses = []
            for block in resp.content:
                if block.type == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_blocks.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
                    tool_uses.append(block)
            if assistant_blocks:
                msgs.append({"role": "assistant", "content": assistant_blocks})

            for block in tool_uses:
                passage = str(dict(block.input).get("passage", ""))
                with client.subagent(name="summarizer", input={"passage": passage}) as sa:
                    summary = _run_summarizer(client.real, model, passage)
                    sa.record_result(summary)
                msgs.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": block.id, "content": summary}
                        ],
                    }
                )

            if resp.stop_reason == "end_turn":
                client.converged()
                break

    print(f"\n== Run {run_id} ==")
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
    invoked = [ev for ev in events if type(ev).__name__ == "SubagentInvokedEvent"]
    returned = [ev for ev in events if type(ev).__name__ == "SubagentReturnedEvent"]
    if not invoked:
        issues.append("subagent_invoked never fired — model didn't call the summarize tool")
    if not returned:
        issues.append("subagent_returned never fired")
    if invoked and returned and invoked[0].data.span_id != returned[0].data.span_id:
        issues.append("subagent_invoked/returned span_ids don't pair")

    stop = next((ev for ev in events if type(ev).__name__ == "AgentStoppedEvent"), None)
    if stop is None:
        issues.append("no agent_stopped event")
    elif str(stop.data.reason) != "StopReason.converged" and stop.data.reason.value != "converged":
        issues.append(f"expected stop=converged; got {stop.data.reason!r}")
    return issues


if __name__ == "__main__":
    raise SystemExit(main())
