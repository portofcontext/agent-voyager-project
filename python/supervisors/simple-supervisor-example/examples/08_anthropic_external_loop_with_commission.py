"""Example 08 — Instrument your own loop, Phase 2: layer in Commission.

The "Instrument your own loop" path in PATTERNS.md: your code owns the
`messages.create` loop, and now the supervisor's Commission starts
driving real run configuration on top of the tracing you added in
Phase 1 (`06_anthropic_traced_client.py`).

Composition:

  1. `Commission`                                       parse / construct
  2. `HttpResolver` / `ScriptedResolver`                dereference refs
  3. `build_anthropic_tools(commission, builtins=...)`  Commission → tools=
  4. `build_anthropic_mcp_servers_from_resolved(...)`   resolved → mcp_servers=
  5. `AVPTracer(commission, on_event=...)`              run lifecycle
  6. `wrap_anthropic(client)`                           per-turn AVP events

What this demonstrates concretely:

  - `enabled_builtin_tools` filters the local tool catalog. The agent has
    three local tools (add / subtract / multiply); the Commission allows
    only `add` and `subtract`, so the model never sees `multiply`.
  - One `skills` ref resolves to inline SKILL.md content that's prepended
    to the system prompt — the model adopts the skill without the agent
    hardcoding it.
  - `wrap_anthropic` proxies `messages.create` so every turn emits
    `model_turn_started / _ended`, `text_emitted`, `tool_invoked`, and
    `cost_recorded` events. The active `AVPTracer` is found via
    contextvar.
  - Tool dispatch is wrapped with `tracer.tool(...)` so AVP records the
    actual execution span (matching the model's `tool_invoked` to a
    `tool_returned`).

Run:
  ANTHROPIC_API_KEY=... python examples/08_anthropic_external_loop_with_commission.py
"""

from __future__ import annotations

import os
import sys

import anthropic

from avp import Commission, SkillRef, print_event
from avp.agent.mock import ScriptedResolver
from avp.tracer import AVPTracer
from avp_anthropic import build_anthropic_tools, wrap_anthropic

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

    # ── Resolver: in-process stand-in for a real supervisor service ───────────
    # In production, this is `HttpResolver(url=..., token=...)` or
    # `http_resolver_from_env()`. The shape returned per resolution matches
    # `spec/resolver/v0.1-beta/resolver.md` §3.
    resolver = ScriptedResolver(
        resolutions={
            "skill:arithmetic-style": {
                "result": {
                    "content": (
                        "# Arithmetic style\n\n"
                        "When asked to compute, call exactly one tool per step. "
                        "Do not chain operations in a single call. Show the running result."
                    ),
                }
            }
        }
    )

    # ── Resolve managed refs (skills here; mcp_servers / subagents identical) ──
    system_prompt_parts: list[str] = []
    for skill_ref in commission.skills or []:
        material = resolver.resolve(kind="skill", id=skill_ref.id, ref=skill_ref.ref)
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

    # ── Run: tracer first, then wrap the client (composes via contextvar) ────
    with AVPTracer(commission, on_event=print_event) as tracer:
        client = wrap_anthropic(anthropic.Anthropic())

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
                with tracer.tool(call_id=block.id, name=block.name, input=dict(block.input)) as t:
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
                tracer.converged()
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
