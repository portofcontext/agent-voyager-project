"""ClaudeAgentTranslator — observer/translator that turns Claude Agent SDK
lifecycle events into AEP v0.1 events.

Structurally different from aep-anthropic's driver pattern: the Claude Agent
SDK owns the agent loop, so we cannot drive turns ourselves. Instead, we wire
into whatever lifecycle hooks the SDK exposes (turn start/end, tool dispatch,
usage updates, completion) and emit the corresponding AEP events.

The integration points marked with `# TODO(claude-agent-sdk):` need to be
filled in against the actual version of `claude_agent_sdk` you ship — its
public hook surface determines how cleanly each AEP event maps. The shape of
this module is the durable part; the SDK calls are the volatile part.
"""

from __future__ import annotations

import itertools
import logging
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
    Source,
    StopReason,
    TextEmittedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
from aep.types import now_iso

logger = logging.getLogger(__name__)


def _monotonic_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


class ClaudeAgentTranslator:
    """Translates a Claude Agent SDK run into AEP v0.1 events.

    Construct with a Config and an `on_event` callback that receives each
    emitted AEP event (Pydantic model). Call .run() to start the SDK; events
    fire as the SDK progresses.

    The translator maintains the same RunStateSnapshot accounting as the
    reference runner so cost_recorded and agent_stopped report consistent
    figures.
    """

    def __init__(
        self,
        config: Config,
        on_event: Callable[[BaseModel], None],
    ) -> None:
        self.config = config
        self.on_event = on_event
        self._call_seq = itertools.count(1)
        self._step = 0
        # Run state mirrors AEPRunner's accounting
        self._started_at = now_iso()
        self._started_monotonic_ms = _monotonic_ms()
        self._total_turns = 0
        self._total_cost_usd = 0.0
        self._total_tokens = 0
        self._tools_invoked: dict[str, int] = {}

    # ── Snapshot ────────────────────────────────────────────────────────────

    def _snapshot(self) -> RunStateSnapshot:
        return RunStateSnapshot(
            total_cost_usd=self._total_cost_usd,
            total_tokens=self._total_tokens,
            total_turns=self._total_turns,
            tools_invoked=dict(self._tools_invoked) or None,
            started_at=self._started_at,
            duration_ms=max(0, _monotonic_ms() - self._started_monotonic_ms),
        )

    def _emit(self, event: BaseModel) -> None:
        self.on_event(event)

    # ── Public lifecycle ────────────────────────────────────────────────────

    def run(self) -> AgentStoppedEvent:
        """Start the Claude Agent SDK run and emit AEP events as it progresses.

        Returns the terminal AgentStoppedEvent."""
        self._emit_agent_started()

        try:
            self._invoke_sdk()
            return self._emit_agent_stopped(StopReason.converged)
        except KeyboardInterrupt:
            return self._emit_agent_stopped(StopReason.interrupted)
        except Exception as e:
            logger.exception("aep-claude-agent: SDK error")
            return self._emit_agent_stopped(StopReason.error, error_msg=str(e))

    # ── SDK integration (TODOs) ────────────────────────────────────────────

    def _invoke_sdk(self) -> None:
        """Drive the Claude Agent SDK and route its lifecycle events to translator handlers.

        Pseudocode shape — fill in against the actual claude_agent_sdk public API:

            from claude_agent_sdk import query
            options = self._build_sdk_options()
            for sdk_event in query(prompt=self.config.prompt, options=options):
                self._on_sdk_event(sdk_event)
        """
        # TODO(claude-agent-sdk): import and invoke the SDK's query/run entry point;
        # iterate or subscribe to its lifecycle events; route each through self._on_sdk_event.
        raise NotImplementedError(
            "aep-claude-agent: SDK integration is a scaffold. Fill in _invoke_sdk and "
            "_on_sdk_event against the version of claude_agent_sdk you depend on."
        )

    def _build_sdk_options(self) -> dict[str, Any]:
        """Translate Config → claude_agent_sdk options dict.

        The mapping is implementation-dependent; this is the pattern:
        - config.model       → options['model']
        - config.system_prompt → options['system_prompt']
        - config.tools       → options['tools'] (supervisor-executed; runner registers handlers)
        - config.boundary    → options for max-turns / max-cost where the SDK supports them
        """
        opts: dict[str, Any] = {}
        if self.config.model:
            opts["model"] = self.config.model
        if self.config.system_prompt:
            opts["system_prompt"] = self.config.system_prompt
        # TODO(claude-agent-sdk): map config.tools, config.boundary, etc.
        return opts

    def _on_sdk_event(self, sdk_event: Any) -> None:
        """Route a single SDK lifecycle event to the appropriate AEP emitter.

        Match the SDK's own event taxonomy and dispatch:
          - turn-start    → self._on_turn_start()
          - turn-end (with usage) → self._on_turn_end(usage)
          - tool-use      → self._on_tool_invoked(call_id, tool, input)
          - tool-result   → self._on_tool_returned(call_id, tool, output)
          - text-output   → self._on_text(text)
          - completion    → handled at top level in run()
        """
        # TODO(claude-agent-sdk): switch on the SDK's event/message type.
        raise NotImplementedError

    # ── AEP emission helpers ───────────────────────────────────────────────

    def _emit_agent_started(self) -> None:
        cfg = self.config
        tools_meta = None
        if cfg.tools:
            tools_meta = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in cfg.tools
            ]
        self._emit(
            AgentStartedEvent(
                run_id=cfg.run_id,
                model=cfg.model or "unspecified",
                prompt=cfg.prompt,
                system_prompt=cfg.system_prompt,
                tools=tools_meta,
                skills=[s.name for s in (cfg.skills or [])] or None,
                thread_id=cfg.thread_id,
                tags=cfg.tags,
                meta=cfg.meta,
            )
        )

    def _on_turn_start(self) -> None:
        self._step += 1
        self._emit(
            ModelTurnStartedEvent(
                run_id=self.config.run_id,
                step=self._step,
            )
        )

    def _on_turn_end(
        self,
        *,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
        duration_ms: int,
        tokens_cache_read: int | None = None,
        tokens_cache_write: int | None = None,
    ) -> None:
        cfg = self.config
        self._emit(
            ModelTurnEndedEvent(
                run_id=cfg.run_id,
                step=self._step,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                tokens_cache_read=tokens_cache_read,
                tokens_cache_write=tokens_cache_write,
            )
        )
        self._total_turns += 1
        self._total_cost_usd += cost_usd
        self._total_tokens += tokens_input + tokens_output
        self._emit(CostRecordedEvent(run_id=cfg.run_id, state=self._snapshot()))

    def _on_tool_invoked(self, *, call_id: str, tool: str, input: dict[str, Any]) -> None:
        self._emit(
            ToolInvokedEvent(
                run_id=self.config.run_id,
                step=self._step,
                call_id=call_id,
                tool=tool,
                input=input,
            )
        )
        self._tools_invoked[tool] = self._tools_invoked.get(tool, 0) + 1

    def _on_tool_returned(
        self,
        *,
        call_id: str,
        tool: str,
        output: str,
        duration_ms: int,
        rejected: bool | None = None,
        rejection_reason: str | None = None,
    ) -> None:
        self._emit(
            ToolReturnedEvent(
                run_id=self.config.run_id,
                step=self._step,
                call_id=call_id,
                tool=tool,
                output=output,
                duration_ms=duration_ms,
                rejected=rejected,
                rejection_reason=rejection_reason,
            )
        )

    def _on_text(self, text: str) -> None:
        self._emit(
            TextEmittedEvent(
                run_id=self.config.run_id,
                step=self._step,
                text=text,
            )
        )

    def _emit_agent_stopped(
        self, reason: StopReason, *, error_msg: str | None = None
    ) -> AgentStoppedEvent:
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
        self._emit(ev)
        return ev


# Quiet unused-import warning for the `Source` re-export at top-level.
_ = Source
