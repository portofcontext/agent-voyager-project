"""Lightweight constructors for SupervisorMessage instances (v0.1).

v0.1 has one SupervisorMessage type: aep.tool_exec_resolved (the JSON-RPC reply
for a supervisor- or MCP-server-provided tool service). The wire payload is a
CloudEvents envelope wrapping a JSON-RPC 2.0 response.
"""

from __future__ import annotations

from typing import Any

from aep.types import (
    SOURCE_SUPERVISOR,
    ZERO_SPAN_ID,
    JsonRpcError,
    JsonRpcResponsePayload,
    ToolExecRequestEvent,
    ToolExecResolvedData,
    ToolExecResolvedEvent,
    new_span_id,
    new_trace_id,
    source_for_mcp,
)


def resolve_tool(
    request: ToolExecRequestEvent,
    *,
    result: Any | None = None,
    error: JsonRpcError | dict[str, Any] | None = None,
    server_id: str | None = None,
) -> ToolExecResolvedEvent:
    """Build an aep.tool_exec_resolved event from a request.

    Exactly one of `result` or `error` MUST be provided (per JSON-RPC 2.0).
    `result` may be any JSON-serializable value (string, dict, list, etc.).
    `error` is a JsonRpcError or a dict like {code: int, message: str, data?: ...}.

    `server_id` (optional) flips the `source` URI to `aep://mcp/<server_id>`
    indicating the reply came from an MCP server rather than the supervisor.

    Note: trace context (trace_id / parent_span_id) on the produced event is
    a placeholder. The runner overrides it with the rpc-span context when it
    receives the reply, so the trajectory's span tree stays consistent.
    """
    if (result is None) == (error is None):
        raise ValueError("resolve_tool: exactly one of `result` or `error` required")

    rpc_error: JsonRpcError | None = None
    if error is not None:
        rpc_error = error if isinstance(error, JsonRpcError) else JsonRpcError(**error)

    rpc = JsonRpcResponsePayload(
        id=request.data.rpc.id,
        result=result if rpc_error is None else None,
        error=rpc_error,
    )
    source = source_for_mcp(server_id) if server_id else SOURCE_SUPERVISOR
    data = ToolExecResolvedData(
        trace_id=new_trace_id(),  # placeholder; runner restamps on receipt
        span_id=new_span_id(),
        parent_span_id=ZERO_SPAN_ID,
        rpc=rpc,
        **{"aep.request_id": request.data.aep_request_id},
    )
    return ToolExecResolvedEvent(subject=request.subject, source=source, data=data)


__all__ = ["resolve_tool"]
