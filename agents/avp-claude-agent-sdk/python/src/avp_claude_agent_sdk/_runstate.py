"""Per-run state for the Claude Agent SDK adapter.

The trajectory's ordering and span rules live in `avp.recorder.Recorder`;
this module only carries what the adapter itself needs between SDK messages.
"""

from __future__ import annotations

import contextvars
import dataclasses
from collections.abc import AsyncIterable
from typing import Any

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
    # `message_id` of the inference currently streaming. The CLI fans one API
    # response out as one AssistantMessage per content block, all sharing the
    # id; a chunk without one belongs to the inference already streaming.
    turn_key: str | None = None

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
