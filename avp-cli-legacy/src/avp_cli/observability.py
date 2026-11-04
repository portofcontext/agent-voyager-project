"""Surface the two classes of trajectory facts.

`spec/v0.1/trajectory.md` §1 splits trajectory events into two semantically
distinct kinds in v0.1:

  1. What the agent did    — assistant_message, tool_invoked/returned
  2. What the run cost     — assistant_message.avp.usage + avp.cost_usd

The agent does NOT publish cumulative totals; per-turn deltas live on each
`assistant_message` and the consumer reduces the stream. This module does
exactly that: a `Summary` dataclass that holds the split facts, plus a
renderer that prints a compact post-run report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from avp.trajectory import (
    AgentStoppedEvent,
    AssistantMessageEvent,
    ErrorOccurredEvent,
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

    # What the run cost (reduced from per-turn assistant_message deltas)
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    duration_ms: int = 0

    # Errors / RPC anomalies
    errors: list[str] = field(default_factory=list)

    @property
    def tool_invocation_count(self) -> int:
        return sum(t.invocations for t in self.tools.values())


def summarize(events: list[BaseModel | dict[str, Any]]) -> Summary:
    """Walk a captured trajectory and produce a Summary.

    Totals are reduced from each `assistant_message`'s per-turn deltas
    (`avp.cost_usd`, `avp.usage`, `avp.duration_ms`): the agent publishes no
    cumulative snapshot, so the consumer sums. `input_tokens` already includes
    cache reads (Usage convention), so summing input + output does not double
    count.
    """
    s = Summary(run_id="(unknown)")

    for ev in events:
        if isinstance(ev, dict):
            continue  # custom event passthrough; ignored here

        if isinstance(ev, AssistantMessageEvent):
            s.total_turns += 1
            s.total_cost_usd += ev.data.cost_usd
            s.total_tokens += ev.data.usage.input_tokens + ev.data.usage.output_tokens
            s.duration_ms += ev.data.duration_ms
        elif isinstance(ev, ToolInvokedEvent):
            tool = ev.data.tool_name
            usage = s.tools.setdefault(tool, ToolUsage(name=tool))
            usage.invocations += 1
        elif isinstance(ev, ToolReturnedEvent):
            if ev.data.tool_result.is_error:
                tool = ev.data.tool_name
                usage = s.tools.setdefault(tool, ToolUsage(name=tool))
                usage.failures += 1
        elif isinstance(ev, AgentStoppedEvent):
            s.run_id = ev.subject or "(unknown)"
            s.stop_reason = str(ev.data.reason)
        elif isinstance(ev, ErrorOccurredEvent):
            s.errors.append(f"{ev.data.error_code}: {ev.data.error_message}")

    return s


def tool_tally(s: Summary, *, limit: int = 4) -> str:
    """A compact, busiest-first tool tally like `Bash:4 Read:2` (empty if none)."""
    items = sorted(s.tools.values(), key=lambda t: -t.invocations)
    parts = [f"{t.name}:{t.invocations}" for t in items[:limit]]
    if len(items) > limit:
        parts.append("…")
    return " ".join(parts)


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
