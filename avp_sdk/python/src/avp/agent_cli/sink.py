"""Writing events as NDJSON."""

import sys
from pathlib import Path

from avp._base import EventSink
from avp.trajectory import Event


def ndjson_sink(out: Path | None) -> EventSink:
    """Write each event as one JSON line to `out`, or to stdout. Reopens the file
    per event so a reader following it sees each event at once."""
    if out is not None:
        out.write_text("")

    async def sink(event: Event) -> None:
        line = event.model_dump_json(exclude_none=True) + "\n"
        if out is None:
            sys.stdout.write(line)
            sys.stdout.flush()
        else:
            with out.open("a") as file:
                file.write(line)

    return sink
