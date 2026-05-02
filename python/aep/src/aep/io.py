"""NDJSON I/O for AEP trajectories and supervisor messages."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from typing import IO, Any

from pydantic import BaseModel

from aep.types import parse_event, parse_supervisor_message


def write_event(event: BaseModel | dict[str, Any], file: IO | None = None) -> None:
    """Serialize one event to NDJSON. Flushes after the line per SPEC.md §5.1."""
    out = file if file is not None else sys.stdout
    if isinstance(event, BaseModel):
        # exclude_none drops optional fields the runner did not set; matches the wire shape.
        line = event.model_dump_json(exclude_none=True)
    else:
        line = json.dumps(event, separators=(",", ":"))
    out.write(line + "\n")
    out.flush()


def iter_events(file: IO) -> Iterator[BaseModel | dict[str, Any]]:
    """Iterate events from an NDJSON stream, parsing each line.

    Custom event types are returned as raw dicts (per spec §13).
    """
    for raw in file:
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        yield parse_event(payload)


def read_supervisor_message(file: IO) -> BaseModel | None:
    """Read one supervisor message line from a file. Returns None on EOF."""
    raw = file.readline()
    if not raw:
        return None
    line = raw.strip()
    if not line:
        return None
    payload = json.loads(line)
    return parse_supervisor_message(payload)
