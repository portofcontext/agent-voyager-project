"""avp.agent.sink — BETA sink-style agent and built-in sinks.

:class:`AVPAgentSink` fans every emitted trajectory event out to a
single async callable (the *sink*). Use this when the agent owns its
run lifecycle and the trajectory is meant to land in stdout / a file /
a database / etc.; the sink callable owns serialization and I/O so the
agent stays I/O-agnostic.

:func:`stdio_sink` is the trivial built-in: NDJSON to stdout, one event
per line. Convenient for local runs, examples, and conformance smoke
tests.
"""

from collections.abc import Awaitable, Callable

from avp.agent.base import AVPAgent
from avp.trajectory import Event

EventSink = Callable[[Event], Awaitable[None]]
"""Async callable that consumes one trajectory event at a time."""


class AVPAgentSink(AVPAgent):
    """BETA: trajectory-as-output agent. Events flow one-way to a sink.

    ``sink`` is an async callable invoked once per event. The sink owns
    serialization and I/O (stdout, file, DB, etc.); the agent owns the
    run lifecycle.
    """

    def __init__(self, sink: EventSink) -> None:
        self._sink = sink

    async def emit(self, event: Event) -> None:
        await self._sink(event)


async def stdio_sink(event: Event) -> None:
    """Built-in :data:`EventSink`: print one event as NDJSON to stdout.

    Uses ``by_alias=True`` so dotted CloudEvents / AVP wire keys
    (``avp.correlation_id`` etc.) round-trip in their canonical form.
    """
    print(event.model_dump_json(by_alias=True), flush=True)
