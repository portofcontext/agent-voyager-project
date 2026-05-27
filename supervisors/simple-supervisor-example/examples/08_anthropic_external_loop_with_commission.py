"""Example 08 — Instrument your own loop, Phase 2: layer in Commission.

The "Instrument your own loop" path in PATTERNS.md: your code owns the
`messages.create` loop, and now the supervisor's Commission starts
driving real run configuration on top of the tracing you added in
Phase 1 (`06_anthropic_traced_client.py`).

Composition:

  1. `Commission`                                       parse / construct
  2. resolve refs (inline stand-in for a resolver service)
  3. `build_anthropic_tools(commission, builtins=...)`  Commission → tools=
  4. `AnthropicTracedClient(client, commission=, on_event=)`  run + per-turn events

What this demonstrates concretely:

  - `enabled_builtin_tools` filters the local tool catalog. The agent has
    three local tools (add / subtract / multiply); the Commission allows
    only `add` and `subtract`, so the model never sees `multiply`.
  - One `skills` ref resolves to inline SKILL.md content that's prepended
    to the system prompt — the model adopts the skill without the agent
    hardcoding it.
  - `AnthropicTracedClient` instruments `messages.create` so every turn
    emits one `assistant_message` (with `avp.content`, `avp.usage`,
    `avp.cost_usd`), bracketed by `run_requested` / `agent_started` /
    `agent_stopped`.
  - Tool dispatch is wrapped with `client.tool(...)` so AVP records the
    actual execution span (a `tool_invoked` / `tool_returned` pair).

Run:
  ANTHROPIC_API_KEY=... python examples/08_anthropic_external_loop_with_commission.py
"""

from __future__ import annotations

import os
import sys

import anthropic

from avp.commission import (
    Commission,
    SkillRef,
)
from avp_anthropic import AnthropicTracedClient, build_anthropic_tools, print_event

# Local tool catalog the agent exposes. The Commission's
# `enabled_builtin_tools` allowlist gates which of these the model sees.
LOCAL_TOOLS: list[dict] = [
    {
        "name": "add",
        "description": "Adds two integers a and b. Returns the sum.",
        "input_schema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "subtract",
        "description": "Subtracts b from a. Returns the difference.",
        "input_schema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "multiply",
        "description": "Multiplies two integers. Returns the product.",
        "input_schema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    },
]


def dispatch(name: str, args: dict) -> str:
    a, b = int(args["a"]), int(args["b"])
    if name == "add":
        return str(a + b)
    if name == "subtract":
        return str(a - b)
    if name == "multiply":
        return str(a * b)
    raise ValueError(f"unknown tool {name!r}")


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    # ── Commission: enabled_builtin_tools + one skill ref ─────────────────────
    commission = Commission(
        schema_version="0.1",
        run_id="external-loop-example",
        model="claude-haiku-4-5-20251001",
        prompt="Compute 17 + 25, then subtract 4. State the final result and stop.",
        enabled_builtin_tools=["add", "subtract"],  # multiply gated off
        skills=[SkillRef(id="arithmetic-style", ref="local://skills/arithmetic-style")],
    )

    # ── Resolver: inline stand-in for a real supervisor service ───────────────
    # In production a resolver service dereferences each ref (per
    # `spec/v0.1/resolver.md`). Here we resolve inline by id.
    _RESOLUTIONS: dict[str, dict] = {
        "arithmetic-style": {
            "content": (
                "# Arithmetic style\n\n"
                "When asked to compute, call exactly one tool per step. "
                "Do not chain operations in a single call. Show the running result."
            ),
        }
    }

    # ── Resolve managed refs (skills here; mcp_servers / subagents identical) ──
    system_prompt_parts: list[str] = []
    for skill_ref in commission.skills or []:
        material = _RESOLUTIONS.get(skill_ref.id, {})
        if content := material.get("content"):
            system_prompt_parts.append(content)
    # If commission.mcp_servers were set:
    #     resolved = {entry.id: resolver.resolve(kind="mcp_server", id=entry.id, ref=entry.ref)
    #                 for entry in commission.mcp_servers or []}
    #     mcp_servers_param = build_anthropic_mcp_servers_from_resolved(resolved)
    # then pass mcp_servers_param to client.messages.create(...).

    # ── Tool catalog gated by enabled_builtin_tools ───────────────────────────
    tools = build_anthropic_tools(commission, builtins=LOCAL_TOOLS)
    # tools now contains only the entries whose name is in
    # commission.enabled_builtin_tools — i.e. add + subtract, not multiply.

    # ── Run: instrument the client; the loop body is otherwise unchanged ──────
    with AnthropicTracedClient(
        anthropic.Anthropic(), commission=commission, on_event=print_event
    ) as client:
        system = "\n\n".join(system_prompt_parts) or None
        msgs: list[dict] = [{"role": "user", "content": commission.prompt}]
        for _ in range(8):  # turn budget; v0.1 leaves bounded execution to caller
            create_kwargs = {
                "model": commission.model,
                "max_tokens": 300,
                "messages": msgs,
                "tools": tools,
            }
            if system is not None:
                create_kwargs["system"] = system
            resp = client.messages.create(**create_kwargs)

            # Append the assistant turn so the next call has the right history.
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

            # Dispatch tools, recording each span on the trajectory.
            for block in tool_uses:
                with client.tool(call_id=block.id, name=block.name, input=dict(block.input)) as t:
                    output = dispatch(block.name, dict(block.input))
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
