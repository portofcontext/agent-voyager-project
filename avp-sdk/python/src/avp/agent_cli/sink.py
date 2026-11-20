"""Write the run's ATIF document once, when the run ends."""

import sys
from pathlib import Path

from avp._base import TrajectorySink
from avp.trajectory import Recording


def trajectory_sink(out: Path | None) -> TrajectorySink:
    """Write to `out`, or to stdout when it is None. Stdout can't carry the
    referenced files, so a run with images or skill files needs a path."""

    async def sink(recording: Recording) -> None:
        if out is not None:
            recording.write(out)
            return
        if recording.assets:
            raise ValueError("a Trajectory with referenced files needs --out with a file path")
        sys.stdout.write(recording.json() + "\n")
        sys.stdout.flush()

    return sink
