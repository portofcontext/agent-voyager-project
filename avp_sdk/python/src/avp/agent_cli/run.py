"""What the agent gives the command line."""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import JsonValue

from avp._base import EventSink
from avp.descriptor import AgentDescriptor

RunFn = Callable[[JsonValue, EventSink], Awaitable[None]]
"""The agent's run: takes the Commission as received and writes every event of
the Trajectory to the sink, through `avp.recorder.Recorder` or by hand. When
cancelled, it ends the Trajectory (`agent_stopped` with `interrupted`) and
re-raises `CancelledError`."""
DescribeFn = Callable[[], AgentDescriptor | Awaitable[AgentDescriptor]]


def read_commission(value: str) -> JsonValue:
    """The Commission as received: parsed JSON, or the text when it isn't JSON."""
    text = value if value.lstrip().startswith("{") else Path(value).read_text()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def get_descriptor(describe: DescribeFn) -> AgentDescriptor:
    descriptor = describe()
    if isinstance(descriptor, AgentDescriptor):
        return descriptor
    return await descriptor
