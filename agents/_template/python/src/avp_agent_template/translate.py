"""Native harness data -> AVP wire shapes. REPLACE the bodies.

Only translation lives here. Ordering, spans, steps, tool pairing, and cost
are the Recorder's job.
"""

from __future__ import annotations

from typing import Any

from avp.content import AVPContentBlock, TextBlock, ToolUseBlock
from avp.trajectory import StopReason, Usage


def content(message: dict[str, Any]) -> list[AVPContentBlock]:
    """The model's output for one inference. Tool calls MUST appear as
    `tool_use` blocks: the Recorder derives `tool_invoked` from them."""
    blocks: list[AVPContentBlock] = []
    if message["text"]:
        blocks.append(TextBlock(text=message["text"]))
    blocks += [
        ToolUseBlock(id=c["id"], name=c["name"], input=c["args"]) for c in message["tool_calls"]
    ]
    return blocks


def usage(native: dict[str, Any]) -> Usage:
    """`input_tokens` counts the whole prompt, cache reads and writes included."""
    return Usage(input_tokens=native["prompt_tokens"], output_tokens=native["completion_tokens"])


def stop_reason(status: str) -> StopReason:
    return {"completed": StopReason.converged, "cancelled": StopReason.interrupted}.get(
        status, StopReason.error
    )
