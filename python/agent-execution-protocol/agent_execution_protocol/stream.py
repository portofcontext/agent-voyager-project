"""NDJSON stream reader/writer for AEP event streams."""

from __future__ import annotations

import io
import json
import sys
from typing import Any, Iterator, TextIO

from .events import AepEvent, HookVerdict, event_from_dict


def write_event(event: AepEvent, file: TextIO | None = None) -> None:
    """Serialize one AEP event as a NDJSON line to file (default: stdout), flushing immediately."""
    out = file or sys.stdout
    out.write(json.dumps(event.to_dict()) + "\n")
    out.flush()


def read_config(file: TextIO | None = None) -> dict[str, Any]:
    """Read one JSON line from file (default: stdin) and return it as a dict.

    Raises ValueError if the line is not valid JSON or is empty.
    """
    src = file or sys.stdin
    raw = src.readline()
    if not raw.strip():
        raise ValueError("AEP config: empty input (expected JSON on first line)")
    return json.loads(raw)


def read_verdict(file: TextIO | None = None) -> HookVerdict:
    """Read one hook_verdict line from file (default: stdin).

    Called by the runner after emitting a hook_request, to receive the
    supervisor's verdict. Blocks until a line is available.

    Raises ValueError if the line is not valid JSON, not a hook_verdict, or
    is missing required fields (run_id, request_id, verdict).
    """
    src = file or sys.stdin
    raw = src.readline()
    if not raw.strip():
        raise ValueError("AEP hook_verdict: empty input")
    d = json.loads(raw)
    if d.get("type") != "hook_verdict":
        raise ValueError(f"Expected hook_verdict, got type={d.get('type')!r}")
    for key in ("run_id", "request_id", "verdict"):
        if key not in d:
            raise ValueError(f"AEP hook_verdict missing required field: {key!r}")
    return HookVerdict(
        run_id=d["run_id"],
        request_id=d["request_id"],
        verdict=d["verdict"],
        ts=d.get("ts", ""),
        message=d.get("message"),
    )


def send_verdict(verdict: HookVerdict, file: TextIO | None = None) -> None:
    """Write a hook_verdict to file (default: stdout), flushing immediately.

    Called by the supervisor to respond to a hook_request. In practice the
    supervisor passes the runner's stdin pipe as ``file``.
    """
    out = file or sys.stdout
    out.write(json.dumps(verdict.to_dict()) + "\n")
    out.flush()


def parse_stream(text: str) -> tuple[list[Any], list[str]]:
    """Parse an NDJSON string into events and errors.

    Returns:
        (events, errors) — events that parsed successfully, and error messages for
        lines that failed. Empty lines are silently skipped.

    Known AEP event types are returned as typed dataclasses. Unknown event types
    (e.g. custom or future types) are returned as raw dicts and do not produce errors.
    """
    events: list[Any] = []
    errors: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            events.append(event_from_dict(d))
        except json.JSONDecodeError as e:
            errors.append(f"line {lineno}: JSON parse error — {e}")
        except ValueError as e:
            errors.append(f"line {lineno}: {e}")
    return events, errors


def iter_stream(file: TextIO) -> Iterator[tuple[int, Any | None, str | None]]:
    """Iterate over an NDJSON stream line by line.

    Yields (lineno, event_or_none, error_or_none) for each non-empty line.
    Known AEP event types are returned as typed dataclasses; unknown types as raw dicts.
    """
    for lineno, line in enumerate(file, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            yield lineno, event_from_dict(d), None
        except (json.JSONDecodeError, ValueError) as e:
            yield lineno, None, str(e)
