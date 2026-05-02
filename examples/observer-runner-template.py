"""Observer-pattern AEP runner — minimal template.

Use this when an SDK already owns the agent loop (Claude Agent SDK,
LangChain, AutoGen, your internal framework) and you want AEP observability
over its lifecycle. The reference implementation against the Claude Agent SDK
lives at python/runners/aep-claude-agent/.

The pattern: subscribe to the SDK's lifecycle events, translate each into the
corresponding AEP event, accumulate run state for cost/token reporting per
AEP §10.4.

To run:
    pip install -e python/aep
    python examples/observer-runner-template.py
"""

from __future__ import annotations

import itertools
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from aep import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Config,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    RunStateSnapshot,
    StopReason,
    TextEmittedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    write_event,
)
from aep.types import now_iso


def _monotonic_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


class MyTranslator:
    """Translate a third-party SDK's lifecycle into AEP v0.1 events.

    The SDK calls our handlers; our handlers emit AEP. We don't drive the SDK's
    loop — it drives us. Cost/token accounting still mirrors the canonical
    runner (RunStateSnapshot per §10.4, monotonic non-decreasing).
    """

    def __init__(self, config: Config, on_event: Callable[[BaseModel], None]) -> None:
        self.config = config
        self.on_event = on_event
        self._step = 0
        self._call_seq = itertools.count(1)
        self._started_at = now_iso()
        self._started_monotonic_ms = _monotonic_ms()
        # Run state — mirror what the canonical runner tracks.
        self._total_turns = 0
        self._total_cost_usd = 0.0
        self._total_tokens = 0
        self._tools_invoked: dict[str, int] = {}

    def _snapshot(self) -> RunStateSnapshot:
        return RunStateSnapshot(
            total_cost_usd=self._total_cost_usd,
            total_tokens=self._total_tokens,
            total_turns=self._total_turns,
            tools_invoked=dict(self._tools_invoked) or None,
            started_at=self._started_at,
            duration_ms=max(0, _monotonic_ms() - self._started_monotonic_ms),
        )

    # ── Public lifecycle handlers (your SDK adapter calls these) ────────────

    def begin(self) -> None:
        self.on_event(
            AgentStartedEvent(
                run_id=self.config.run_id,
                model=self.config.model or "unspecified",
                prompt=self.config.prompt,
                system_prompt=self.config.system_prompt,
            )
        )

    def turn_started(self) -> None:
        self._step += 1
        self.on_event(
            ModelTurnStartedEvent(
                run_id=self.config.run_id,
                step=self._step,
            )
        )

    def turn_ended(
        self,
        *,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
        duration_ms: int,
        tokens_cache_read: int | None = None,
    ) -> None:
        # AEP §10.4: tokens_input INCLUDES cache reads. If your SDK reports
        # them separately, ADD them in before passing to this handler.
        self.on_event(
            ModelTurnEndedEvent(
                run_id=self.config.run_id,
                step=self._step,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                tokens_cache_read=tokens_cache_read,
            )
        )
        self._total_turns += 1
        self._total_cost_usd += cost_usd
        self._total_tokens += tokens_input + tokens_output
        self.on_event(
            CostRecordedEvent(
                run_id=self.config.run_id,
                state=self._snapshot(),
            )
        )

    def tool_invoked(self, *, tool: str, input: dict[str, Any]) -> str:
        call_id = f"call-{next(self._call_seq)}"
        self.on_event(
            ToolInvokedEvent(
                run_id=self.config.run_id,
                step=self._step,
                call_id=call_id,
                tool=tool,
                input=input,
            )
        )
        self._tools_invoked[tool] = self._tools_invoked.get(tool, 0) + 1
        return call_id

    def tool_returned(self, *, call_id: str, tool: str, output: str, duration_ms: int) -> None:
        self.on_event(
            ToolReturnedEvent(
                run_id=self.config.run_id,
                step=self._step,
                call_id=call_id,
                tool=tool,
                output=output,
                duration_ms=duration_ms,
            )
        )

    def text(self, content: str) -> None:
        self.on_event(
            TextEmittedEvent(
                run_id=self.config.run_id,
                step=self._step,
                text=content,
            )
        )

    def end(self, reason: StopReason = StopReason.converged) -> AgentStoppedEvent:
        snap = self._snapshot()
        ev = AgentStoppedEvent(
            run_id=self.config.run_id,
            reason=reason,
            state=snap,
            total_tokens=snap.total_tokens,
            total_cost_usd=snap.total_cost_usd,
            total_turns=snap.total_turns,
            duration_ms=snap.duration_ms,
        )
        self.on_event(ev)
        return ev


# ── Example: simulate an SDK driving the translator ─────────────────────────


def main() -> None:
    config = Config(
        schema_version="0.1",
        run_id="demo-observer-runner",
        model="your-sdk-model",
        prompt="Refactor the auth module.",
    )

    # Stream events as NDJSON to stdout. In production, pipe this to a file
    # or to a supervisor's input channel.
    t = MyTranslator(config=config, on_event=lambda ev: write_event(ev, file=sys.stdout))

    # Below: the SDK's lifecycle events would call into these handlers.
    # The translator stays out of the SDK's way; it just records what happened.
    t.begin()
    t.turn_started()
    t.turn_ended(tokens_input=120, tokens_output=40, cost_usd=0.0006, duration_ms=800)
    t.text("here's what I'd do...")
    cid = t.tool_invoked(tool="bash", input={"command": "ls"})
    t.tool_returned(call_id=cid, tool="bash", output="file1\nfile2", duration_ms=12)
    t.turn_started()
    t.turn_ended(tokens_input=80, tokens_output=20, cost_usd=0.0004, duration_ms=600)
    t.text("done.")
    t.end(StopReason.converged)


if __name__ == "__main__":
    main()
