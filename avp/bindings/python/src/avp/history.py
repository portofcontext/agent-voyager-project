"""avp.history — Reconstruct a provider-style message history from a trajectory.

A trajectory is the agent's stream-of-events record. A *message history*
is the provider's input shape: a list of `{role, content}` records. This
module converts the former to the latter, faithfully enough that the
same conversation could be replayed against any provider's chat API.

The mapping is:

- `agent_started.avp.system_prompt` → one `system` message.
- `agent_started.avp.prompt`        → one `user` message (initial turn).
- `assistant_message.avp.content`   → one `assistant` message per turn.
- Each `tool_returned.avp.tool_result` between two assistant turns
  bundles into a single `user` message preceding the next assistant turn
  (mirroring how providers shuttle tool results in user-role messages).

Other event types (`tool_invoked`, `mcp_*`, `error_occurred`, `agent_*`,
`UnknownEvent`, ...) are observability or run-control facts that don't
contribute to message history; they are skipped.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel

from avp.content import AVPContentBlock, TextBlock
from avp.envelope import _OPEN
from avp.trajectory import (
    AgentStartedEvent,
    AssistantMessageEvent,
    Event,
    ToolReturnedEvent,
)


class Message(BaseModel):
    """One entry of a provider-style message history."""

    model_config = _OPEN
    role: Literal["user", "assistant", "system"]
    content: list[AVPContentBlock]


def to_messages(events: Iterable[Event]) -> list[Message]:
    """Reconstruct a provider-style message history from a trajectory.

    See the module docstring for the event-to-message mapping.
    """
    messages: list[Message] = []
    pending: list[AVPContentBlock] = []

    def flush() -> None:
        if pending:
            messages.append(Message(role="user", content=list(pending)))
            pending.clear()

    for event in events:
        if isinstance(event, AgentStartedEvent):
            if event.data.system_prompt:
                messages.append(
                    Message(
                        role="system",
                        content=[TextBlock(text=event.data.system_prompt)],
                    )
                )
            if event.data.prompt:
                messages.append(
                    Message(
                        role="user",
                        content=[TextBlock(text=event.data.prompt)],
                    )
                )
        elif isinstance(event, AssistantMessageEvent):
            flush()
            messages.append(Message(role="assistant", content=list(event.data.content)))
        elif isinstance(event, ToolReturnedEvent):
            pending.append(event.data.tool_result)

    flush()
    return messages


__all__ = ["Message", "to_messages"]
