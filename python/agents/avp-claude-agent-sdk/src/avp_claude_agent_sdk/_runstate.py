"""Per-run state holder for AVP trajectory emission."""

from __future__ import annotations

import contextvars
import dataclasses

from avp.agent.sink import EventSink


@dataclasses.dataclass
class RunState:
    """Flat per-run state. One instance per active run, stored in a context-var."""

    trace_id: str
    run_id: str
    sink: EventSink
    agent_span_id: str | None = None
    current_turn_span_id: str | None = None
    # tool_use_id → span_id; populated in Stage 2
    tool_spans: dict[str, str] = dataclasses.field(default_factory=dict)


_current: contextvars.ContextVar[RunState | None] = contextvars.ContextVar(
    "avp_claude_agent_run", default=None
)


def current_run() -> RunState | None:
    return _current.get()


def set_run(state: RunState) -> contextvars.Token[RunState | None]:
    return _current.set(state)


def reset_run(token: contextvars.Token[RunState | None]) -> None:
    _current.reset(token)
