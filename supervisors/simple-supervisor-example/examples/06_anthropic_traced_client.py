"""Example 06 — drop-in instrumentation for an existing Anthropic SDK loop.

Wrap your `anthropic.Anthropic()` in `AnthropicTracedClient(...)`, give it
a Commission and an on_event sink, and your existing loop emits AVP events.
The loop body is otherwise unchanged: `messages.create()` returns the same
SDK object, you walk `.content` blocks the same way, you dispatch tools
the same way.

v0.1 leaves bounded execution to the caller — wire external safety
(subprocess timeouts, supervisor SIGKILL, caller-side turn budgets) as
needed.

Run:
  ANTHROPIC_API_KEY=... python examples/06_anthropic_traced_client.py
"""

from __future__ import annotations

import os
import sys

import anthropic

from avp.commission import Commission
from avp_anthropic import AnthropicTracedClient, print_event


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    commission = Commission(
        schema_version="0.1",
        run_id="traced-client-example",
        model="claude-haiku-4-5-20251001",
        prompt=(
            "Use the `add_two_numbers` tool to compute 17 + 25, then state "
            "the result and stop. Do not compute it yourself."
        ),
    )

    # Local tool implementation. In a real agent this is your existing dispatch.
    def add_two_numbers(args: dict) -> str:
        return str(int(args["a"]) + int(args["b"]))

    tools = [
        {
            "name": "add_two_numbers",
            "description": "Adds two integers a and b. Returns the sum as a string.",
            "input_schema": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
        }
    ]

    # The loop you'd already have, with one wrapper added. Compare to a
    # vanilla Anthropic SDK loop:
    #
    #     client = anthropic.Anthropic()
    #     while True:
    #         resp = client.messages.create(...)
    #         if resp.stop_reason == "end_turn": break
    #         for block in resp.content: ...
    #
    # Only changes:
    #   - wrap with `AnthropicTracedClient(real, commission=, on_event=)`
    #   - wrap tool dispatch with `client.tool(...)` so AVP can record it
    #   - call `client.converged()` to mark a clean exit
    with AnthropicTracedClient(
        anthropic.Anthropic(), commission=commission, on_event=print_event
    ) as client:
        msgs = [{"role": "user", "content": commission.prompt}]
        while True:
            resp = client.messages.create(
                model=commission.model, max_tokens=300, messages=msgs, tools=tools
            )

            # Append the assistant turn (text + tool_use blocks) so the next
            # call has correct conversation history.
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

            # Dispatch tools, wrapped with `client.tool(...)` so AVP records.
            for block in tool_uses:
                with client.tool(call_id=block.id, name=block.name, input=dict(block.input)) as t:
                    output = add_two_numbers(dict(block.input))
                    t.record(output)
                msgs.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": block.id, "content": output}
                        ],
                    }
                )

            if resp.stop_reason == "end_turn":
                client.converged()
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
