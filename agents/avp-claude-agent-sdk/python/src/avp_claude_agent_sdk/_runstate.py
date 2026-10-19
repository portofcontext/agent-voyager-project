"""Per-run state for the Claude Agent SDK adapter.

The trajectory's ordering and span rules live in `avp.recorder.Recorder`;
this module only carries what the adapter itself needs between SDK messages.
"""

from __future__ import annotations

import contextvars
import dataclasses
from collections.abc import AsyncIterable
from typing import Any

from claude_agent_sdk.types import TaskNotificationMessage, UserMessage

from avp.pricing import PriceTable, load_default_prices
from avp.recorder import Recorder
from avp.sink import EventSink
from avp_claude_agent_sdk._translator import get_dispatch_target

PROVIDER_NAME = "anthropic"


@dataclasses.dataclass
class RunState:
    """Flat per-run state. One instance per active run."""

    # Prompt the agent was started with
    prompt: str | AsyncIterable[dict[str, Any]] | None
    # Builds the trajectory from what the message handlers report.
    rec: Recorder
    # Commission `enabled_builtin_tools` allow-list (None = expose all). Applied
    # to `agent_started.data.avp.tools` so the merged surface reflects the
    # Commission's subtractive filter over the descriptor's tool bag.
    enabled_builtin_tools: list[str] | None = None
    # Commission `enabled_builtin_subagents` allow-list (None = expose all). The
    # CLI's init still lists subagents its deny rules hide, so this filters them.
    enabled_builtin_subagents: list[str] | None = None
    # The run's SDK `skills` filter when it names skills (None = all). The
    # CLI's init lists the skills it hides too.
    skills_filter: list[str] | None = None
    # `message_id` of the inference currently streaming. The CLI fans one API
    # response out as one AssistantMessage per content block, all sharing the
    # id; a chunk without one belongs to the inference already streaming.
    turn_key: str | None = None
    # The streaming inference's usage so far: the CLI stamps every block with
    # the `message_start` snapshot, and the response's `message_delta` (a
    # partial-message StreamEvent) completes it. None once a tool result has
    # closed the turn.
    turn_usage: dict[str, Any] | None = None
    # Whether a main-thread response is still streaming (`message_start` until
    # `message_stop`). The CLI runs a tool as soon as its call streams in, so a
    # response's later calls can arrive after an earlier call's result.
    streaming: bool = False
    # Tool-result messages held until the response that called them completes.
    held_results: list[UserMessage] = dataclasses.field(default_factory=list)
    # Subagent completions waiting for their `Agent` tool result, which
    # carries the child's final usage and answer, keyed by tool_use_id.
    finished_tasks: dict[str, TaskNotificationMessage] = dataclasses.field(default_factory=dict)
    # Tool calls whose result has arrived. A subagent launched in the
    # background returns before it finishes and closes on its notification.
    answered_calls: set[str] = dataclasses.field(default_factory=set)

    @property
    def stopped(self) -> bool:
        return self.rec.stopped


def new_run_state(
    sink: EventSink,
    prompt: str | AsyncIterable[dict[str, Any]] | None,
    *,
    run_id: str | None = None,
    prices: PriceTable | None = None,
    enabled_builtin_tools: list[str] | None = None,
    enabled_builtin_subagents: list[str] | None = None,
    skills_filter: list[str] | None = None,
) -> RunState:
    return RunState(
        prompt=prompt,
        rec=Recorder(
            sink,
            run_id=run_id,
            provider=PROVIDER_NAME,
            prices=prices if prices is not None else load_default_prices(),
            # The SDK namespaces MCP tools as `mcp__<server>__<tool>`, which
            # holds even for a server the init catalog failed to resolve.
            dispatch_target=get_dispatch_target,
        ),
        enabled_builtin_tools=enabled_builtin_tools,
        enabled_builtin_subagents=enabled_builtin_subagents,
        skills_filter=skills_filter,
    )


# ---------------------------------------------------------------------------
# Ambient run access (asyncio-task-scoped via contextvars)
# ---------------------------------------------------------------------------

_current: contextvars.ContextVar[RunState | None] = contextvars.ContextVar(
    "avp_claude_agent_run", default=None
)


def current_run() -> RunState | None:
    """Read the active `RunState` for this asyncio task / thread, or `None`."""
    return _current.get()


def set_run(state: RunState) -> contextvars.Token[RunState | None]:
    """Bind `state` as the active run; pair with `reset_run(token)` on cleanup."""
    return _current.set(state)


def reset_run(token: contextvars.Token[RunState | None]) -> None:
    """Restore the prior active run using the token returned by `set_run`."""
    _current.reset(token)
