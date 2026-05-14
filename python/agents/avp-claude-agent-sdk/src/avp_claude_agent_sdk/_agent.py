"""Skeleton entry point for AVP-instrumented claude_agent_sdk runs."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from avp._envelope import new_trace_id
from avp.agent.sink import EventSink, stdio_sink
from avp.commission import Commission
from avp_claude_agent_sdk._patches import apply_patches
from avp_claude_agent_sdk._runstate import RunState, reset_run, set_run


async def run_avp_agent(
    commission: Commission,
    agent_main: Callable[[], Awaitable[Any]],
    sink: EventSink = stdio_sink,
) -> Any:
    """Apply patches, scope a RunState, and run agent_main.

    Stage 0 skeleton: patches + runstate only. Stage 1 adds prelude
    emission and per-message handlers; Stage 4 wires Commission fields.
    """
    apply_patches()
    state = RunState(
        trace_id=new_trace_id(),
        run_id=str(uuid.uuid4()),
        sink=sink,
    )
    token = set_run(state)
    try:
        return await agent_main()
    finally:
        reset_run(token)
