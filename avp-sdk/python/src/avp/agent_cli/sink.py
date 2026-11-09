"""Publish a native ATIF artifact, preserving readable partial runs."""

import sys
from pathlib import Path

from avp._base import TrajectorySink
from avp.trajectory import Recording, avp_metadata


def trajectory_sink(out: Path | None) -> TrajectorySink:
    """Files update atomically; stdout receives one final JSON document.

    Use a file for live monitoring and media. Stdout cannot bundle media files.
    """

    async def sink(recording: Recording) -> None:
        if out is not None:
            recording.write(out)
        elif avp_metadata(recording.trajectory).get("complete"):
            if recording.assets:
                raise ValueError("media requires --out with a file path")
            sys.stdout.write(recording.trajectory.model_dump_json(exclude_none=True) + "\n")
            sys.stdout.flush()

    return sink
