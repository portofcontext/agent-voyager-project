"""What the agent gives the command line."""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import JsonValue

from avp._base import TrajectorySink
from avp.descriptor import AgentDescriptor

RunFn = Callable[[JsonValue, TrajectorySink], Awaitable[None]]
"""The agent receives a Commission and publishes native ATIF Recording snapshots.
On cancellation it publishes an interrupted outcome and re-raises CancelledError."""
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
