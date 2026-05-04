"""Surface the three classes of trajectory facts.

SPEC.md §10 splits trajectory events into three semantically distinct kinds:

  1. What the agent did    — model_turn_*, tool_invoked/returned/failed, text_emitted
  2. What the rules said   — verifier_evaluated
  3. What the run cost     — cost_recorded, model_turn_ended.usage

A real supervisor framework will surface these on separate UI tracks. This
module ships a `Summary` dataclass that holds them split, plus a renderer
that prints a compact post-run report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from aep import (
    AgentStoppedEvent,
    CostRecordedEvent,
    ErrorOccurredEvent,
    ModelTurnEndedEvent,
    ToolFailedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    VerifierEvaluatedEvent,
)


@dataclass
class ToolUsage:
    name: str
    invocations: int = 0
    failures: int = 0


@dataclass
class VerifierResult:
    name: str
    passed: bool
    step: int | None
    data: dict[str, Any] | None


@dataclass
class Summary:
    run_id: str
    stop_reason: str | None = None

    # What the agent did
    total_turns: int = 0
    tools: dict[str, ToolUsage] = field(default_factory=dict)
    text_chunks: int = 0

    # What the rules said
    verifier_results: list[VerifierResult] = field(default_factory=list)

    # What the run cost
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    duration_ms: int = 0

    # Errors / RPC anomalies
    errors: list[str] = field(default_factory=list)

    @property
    def verifier_pass_count(self) -> int:
        return sum(1 for v in self.verifier_results if v.passed)

    @property
    def verifier_fail_count(self) -> int:
        return sum(1 for v in self.verifier_results if not v.passed)

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
            usage = s.tools.setdefault(ev.tool, ToolUsage(name=ev.tool))
            usage.invocations += 1
        elif isinstance(ev, ToolFailedEvent):
            usage = s.tools.setdefault(ev.tool, ToolUsage(name=ev.tool))
            usage.failures += 1
        elif isinstance(ev, ToolReturnedEvent):
            pass  # invocation already counted on ToolInvoked
        elif isinstance(ev, VerifierEvaluatedEvent):
            s.verifier_results.append(
                VerifierResult(name=ev.name, passed=ev.passed, step=ev.step, data=ev.data)
            )
        elif isinstance(ev, CostRecordedEvent):
            # Snapshot wins — last-write semantics
            s.total_cost_usd = ev.state.total_cost_usd
            s.total_tokens = ev.state.total_tokens
            if ev.state.duration_ms is not None:
                s.duration_ms = ev.state.duration_ms
        elif isinstance(ev, AgentStoppedEvent):
            s.run_id = ev.run_id
            s.stop_reason = str(ev.reason)
            if ev.total_cost_usd is not None:
                s.total_cost_usd = ev.total_cost_usd
            if ev.total_tokens is not None:
                s.total_tokens = ev.total_tokens
            if ev.duration_ms is not None:
                s.duration_ms = ev.duration_ms
        elif isinstance(ev, ErrorOccurredEvent):
            s.errors.append(f"{ev.code}: {ev.message}")

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
    lines.append("")
    lines.append("What the rules said:")
    if not s.verifier_results:
        lines.append("  (no verifiers ran)")
    else:
        lines.append(f"  {s.verifier_pass_count} passed, {s.verifier_fail_count} failed")
        for v in s.verifier_results:
            mark = "PASS" if v.passed else "FAIL"
            step = f"@step={v.step}" if v.step is not None else ""
            lines.append(f"  [{mark}] {v.name} {step}")
            if not v.passed and v.data:
                cmd = v.data.get("command", "")
                if cmd:
                    lines.append(f"      cmd: {cmd}")
    if s.errors:
        lines.append("")
        lines.append("Errors:")
        for e in s.errors:
            lines.append(f"  ! {e}")
    return "\n".join(lines)
