"""A run's directory, under `~/.avp/runs/`, mounted in the sandbox: the
Commission goes in, the Trajectory comes out."""

from datetime import UTC, datetime
from pathlib import Path

from avp_cli import paths


def create(run_id: str, commission: str, at: Path | None = None) -> Path:
    """A new directory holding the dispatched Commission: `at`, or by default
    one under `~/.avp/runs/` named by time first, so runs sort by when they
    started."""
    if at is None:
        at = paths.runs() / paths.stamped(run_id, datetime.now(UTC))
    at.mkdir(parents=True)
    (at / paths.COMMISSION).write_text(commission)
    return at
