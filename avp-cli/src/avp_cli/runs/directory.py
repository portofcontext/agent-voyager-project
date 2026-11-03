"""A run's directory, under `~/.avp/runs/`, mounted in the sandbox: the
Commission goes in, the Trajectory comes out."""

from datetime import UTC, datetime
from pathlib import Path

from avp_cli import paths

COMMISSION = "commission.json"
TRAJECTORY = "trajectory.ndjson"
STDERR = "agent.stderr"
"""What the agent printed to stderr, which avp shows only the end of."""


def create(run_id: str, commission: str, at: Path | None = None) -> Path:
    """A new directory holding the Commission, as given: `at`, or by default
    one under `~/.avp/runs/` named by time first, so runs sort by when they
    started and a reused `run_id` gets its own."""
    if at is None:
        started = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        at = paths.runs() / f"{started}-{run_id}"
    at.mkdir(parents=True)
    (at / COMMISSION).write_text(commission)
    return at
