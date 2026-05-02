"""Lightweight constructors for SupervisorMessage instances (v0.1).

v0.1 has only two SupervisorMessage types — both RPC replies the agent's
environment provides. No hook resolution, no unsolicited domain events.
"""

from __future__ import annotations

from typing import Any

from aep.types import (
    ReObservationRequestEvent,
    ReObservationResolvedEvent,
    ToolExecRequestEvent,
    ToolExecResolvedEvent,
)


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


def resolve_re_observation(
    request: ReObservationRequestEvent, *, content: str
) -> ReObservationResolvedEvent:
    return ReObservationResolvedEvent(
        run_id=request.run_id,
        request_id=request.request_id,
        content=content,
    )


__all__ = ["resolve_re_observation", "resolve_tool"]
