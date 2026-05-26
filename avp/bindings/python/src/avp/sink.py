"""avp.sink — Event-sink type and built-in NDJSON sinks.

An :data:`EventSink` is any async callable that consumes one trajectory
event at a time. It owns serialization and I/O (stdout, file, DB, etc.)
so the surrounding agent stays I/O-agnostic.

Two built-ins are provided:

- :func:`stdio_sink` writes NDJSON to stdout (local runs, examples).
- :func:`jsonl_sink` writes NDJSON to a file (agent implementors
  satisfying the conformance ``run --out <path.jsonl>`` contract).
"""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from avp.trajectory import Event

EventSink = Callable[[Event], Awaitable[None]]
"""Async callable that consumes one trajectory event at a time."""


def _serialize(event: Event) -> str:
    """Serialize an event to its canonical NDJSON line (no trailing newline).

    Uses ``by_alias=True`` so dotted CloudEvents / AVP wire keys
    (``avp.correlation_id`` etc.) round-trip in their canonical form.
    """
    return json.dumps(event.model_dump(by_alias=True, exclude_none=True, mode="json"))


async def stdio_sink(event: Event) -> None:
    """Built-in :data:`EventSink`: print one event as NDJSON to stdout."""
    print(_serialize(event), flush=True)


def jsonl_sink(path: Path) -> EventSink:
    """Build an :data:`EventSink` that writes events to a JSONL file at ``path``.

    The file is truncated on call so each run replaces any prior content,
    then each event is appended in its own ``open("a") / write / close``
    cycle. That makes progress visible to a concurrent reader (e.g. ``tail
    -f``) without relying on OS-level buffer flushing. Used by agent
    implementors to satisfy the conformance ``run --out <path>`` contract.

    Example::

        from avp.sink import jsonl_sink

        async def run(commission, out_path):
            sink = jsonl_sink(out_path)
            await sink(some_event)
            ...
    """
    path.open("w").close()  # reset file

    async def sink(event: Event) -> None:
        with path.open("a") as file:
            file.write(_serialize(event) + "\n")

    return sink
