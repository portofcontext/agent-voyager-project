"""Stand-in for the harness you are adapting. DELETE this file.

It mimics what an agent SDK hands an observer: a stream of native events. A
real adapter iterates the SDK's own stream (or hooks) instead. The scripted
"model" calls the `echo` tool once when the prompt mentions a tool, then
answers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from avp_agent_template.commission import HarnessConfig


async def stream(config: HarnessConfig) -> AsyncIterator[dict[str, Any]]:
    usage = {"prompt_tokens": 120, "completion_tokens": 8}
    if "tool" in config.prompt and "echo" in config.tools:
        yield {
            "kind": "message",
            "id": "msg_1",
            "text": "Calling echo.",
            "tool_calls": [{"id": "call_1", "name": "echo", "args": {"text": config.prompt}}],
            "usage": usage,
        }
        yield {"kind": "tool_result", "call_id": "call_1", "output": config.prompt, "error": False}
    yield {"kind": "message", "id": "msg_2", "text": "DONE", "tool_calls": [], "usage": usage}
    yield {"kind": "done", "status": "completed", "output": "DONE"}
