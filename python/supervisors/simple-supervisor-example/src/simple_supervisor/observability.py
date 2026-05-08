"""Surface the two classes of trajectory facts.

SPEC.md §10 splits trajectory events into two semantically distinct kinds
in v0.1:

  1. What the agent did    — model_turn_*, tool_invoked/returned/failed, text_emitted
  2. What the run cost     — cost_recorded, model_turn_ended.usage

A real supervisor framework will surface these on separate UI tracks. This
module ships a `Summary` dataclass that holds them split, plus a renderer
that prints a compact post-run report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from avp import (
    AgentStoppedEvent,
    CostRecordedEvent,
    ErrorOccurredEvent,
    ModelTurnEndedEvent,
    ToolFailedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)


@dataclass
class ToolUsage:
    name: str
    invocations: int = 0
    failures: int = 0


@dataclass
class Summary:
    run_id: str
    stop_reason: str | None = None

    # What the agent did
    total_turns: int = 0
    tools: dict[str, ToolUsage] = field(default_factory=dict)
    text_chunks: int = 0

    # What the run cost
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    duration_ms: int = 0

    # Errors / RPC anomalies
    errors: list[str] = field(default_factory=list)

    @property
    def tool_invocation_count(self) -> int:
        return sum(t.invocations for t in self.tools.values())


def summarize(events: list[BaseModel | dict[str, Any]]) -> Summary:
    """Walk a captured trajectory and produce a Summary."""
    s = Summary(run_id="(unknown)")

    for ev in events:
        if isinstance(ev, dict):
            continue  # custom event passthrough; ignored here

        if isinstance(ev, ModelTurnEndedEvent):
            s.total_turns += 1
        elif isinstance(ev, ToolInvokedEvent):
            tool = ev.data.gen_ai_tool_name
            usage = s.tools.setdefault(tool, ToolUsage(name=tool))
            usage.invocations += 1
        elif isinstance(ev, ToolFailedEvent):
            tool = ev.data.gen_ai_tool_name
            usage = s.tools.setdefault(tool, ToolUsage(name=tool))
            usage.failures += 1
        elif isinstance(ev, ToolReturnedEvent):
            pass  # invocation already counted on ToolInvoked
        elif isinstance(ev, CostRecordedEvent):
            # Snapshot wins — last-write semantics
            snap = ev.data.avp_state
            s.total_cost_usd = snap.total_cost_usd
            s.total_tokens = snap.total_tokens
            if snap.duration_ms is not None:
                s.duration_ms = snap.duration_ms
        elif isinstance(ev, AgentStoppedEvent):
            s.run_id = ev.subject or "(unknown)"
            s.stop_reason = str(ev.data.avp_reason)
            if ev.data.avp_total_cost_usd is not None:
                s.total_cost_usd = ev.data.avp_total_cost_usd
            if ev.data.avp_total_tokens is not None:
                s.total_tokens = ev.data.avp_total_tokens
            if ev.data.avp_duration_ms is not None:
                s.duration_ms = ev.data.avp_duration_ms
        elif isinstance(ev, ErrorOccurredEvent):
            s.errors.append(f"{ev.data.avp_error_code}: {ev.data.avp_error_message}")

    return s


def render(s: Summary) -> str:
    """Compact human-readable post-run report."""
    lines: list[str] = []
    lines.append(f"== Run {s.run_id} - stopped={s.stop_reason} ==")
    lines.append(
        f"  turns={s.total_turns}  cost=${s.total_cost_usd:.4f}  "
        f"tokens={s.total_tokens:,}  duration={s.duration_ms}ms"
    )
    lines.append("")
    lines.append("What the agent did:")
    if not s.tools:
        lines.append("  (no tool calls)")
    else:
        for name, u in sorted(s.tools.items()):
            fail = f" ({u.failures} failed)" if u.failures else ""
            lines.append(f"  {name}: {u.invocations} call(s){fail}")
    if s.errors:
        lines.append("")
        lines.append("Errors:")
        for e in s.errors:
            lines.append(f"  ! {e}")
    return "\n".join(lines)
