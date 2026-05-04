"""Lightweight constructors for SupervisorMessage instances (v0.1).

v0.1 has one SupervisorMessage type: tool_exec_resolved (the RPC reply for a
supervisor-provided tool service). No hook resolution, no unsolicited domain
events.
"""

from __future__ import annotations

from typing import Any

from aep.types import ToolExecRequestEvent, ToolExecResolvedEvent


def resolve_tool(
    request: ToolExecRequestEvent,
    *,
    output: str,
    output_json: Any | None = None,
    error: str | None = None,
) -> ToolExecResolvedEvent:
    return ToolExecResolvedEvent(
        run_id=request.run_id,
        request_id=request.request_id,
        output=output,
        output_json=output_json,
        error=error,
    )


__all__ = ["resolve_tool"]
