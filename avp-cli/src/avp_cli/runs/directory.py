"""A run's directory, under `~/.avp/runs/`, mounted in the sandbox: the
Commission goes in, the Trajectory comes out."""

from datetime import UTC, datetime
from pathlib import Path

from avp_cli import paths

COMMISSION = "commission.json"
TRAJECTORY = "trajectory.ndjson"
STDERR = "agent.stderr"
"""What the agent printed to stderr, which avp shows only the end of."""


def create(run_id: str, commission: str) -> Path:
    """A new directory holding the Commission, as given. Named by time first,
    so runs sort by when they started and a reused `run_id` gets its own."""
    started = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    directory = paths.runs() / f"{started}-{run_id}"
    directory.mkdir(parents=True)
    (directory / COMMISSION).write_text(commission)
    return directory
