"""avp.sink — Event-sink type and a stdout NDJSON sink.

An :data:`EventSink` is any async callable that consumes one trajectory
event at a time. It owns serialization and I/O (stdout, file, DB, etc.)
so the surrounding agent stays I/O-agnostic.

:func:`stdio_sink` is the trivial built-in: NDJSON to stdout, one event
per line. Convenient for local runs, examples, and conformance smoke
tests.
"""

import json
from collections.abc import Awaitable, Callable

from avp.trajectory import Event

EventSink = Callable[[Event], Awaitable[None]]
"""Async callable that consumes one trajectory event at a time."""


async def stdio_sink(event: Event) -> None:
    """Built-in :data:`EventSink`: print one event as NDJSON to stdout.

    Uses ``by_alias=True`` so dotted CloudEvents / AVP wire keys
    (``avp.correlation_id`` etc.) round-trip in their canonical form.
    """
    print(json.dumps(event.model_dump(by_alias=True, exclude_none=True, mode="json")), flush=True)
