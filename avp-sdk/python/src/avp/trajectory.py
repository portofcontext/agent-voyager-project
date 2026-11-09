"""ATIF wire models and document IO, using Harbor's pinned reference models."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from avp._vendor.atif import (  # noqa: F401
    Agent,
    ContentPart,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    SubagentTrajectoryRef,
    ToolCall,
    Trajectory,
)


def parse_trajectory(value: dict[str, Any] | str | bytes) -> Trajectory:
    """Read any supported upstream ATIF document, including non-AVP producers."""
    if isinstance(value, dict):
        return Trajectory.model_validate(value)
    return Trajectory.model_validate_json(value)


def documents(trajectory: Trajectory):
    """Walk a document and its embedded descendants once."""
    yield trajectory
    for child in trajectory.subagent_trajectories or []:
        yield from documents(child)


def avp_metadata(value: Trajectory | Step | ToolCall | ObservationResult) -> dict[str, Any]:
    """Optional AVP operational metadata; external ATIF need not supply it."""
    return (value.extra or {}).get("avp", {})


@dataclass(frozen=True)
class Recording:
    """A snapshot of the current ATIF document and referenced media bytes."""

    trajectory: Trajectory
    assets: dict[str, bytes] = field(default_factory=dict)

    def write(self, path: Path) -> None:
        """Publish assets first, then atomically replace the readable document."""
        path.parent.mkdir(parents=True, exist_ok=True)
        for name, content in self.assets.items():
            asset = path.parent / name
            if not asset.resolve().is_relative_to(path.parent.resolve()):
                raise ValueError("asset path escapes the trajectory directory")
            asset.parent.mkdir(parents=True, exist_ok=True)
            if not asset.exists():
                asset.write_bytes(content)
        temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
        # Use ordinary file permissions (filtered by umask), like the media files
        # and TypeScript sink. mkstemp's 0600 prevents a host supervisor from
        # reading snapshots written by a different user inside a container.
        file = temporary.open("x", encoding="utf-8")
        try:
            with file:
                file.write(self.trajectory.model_dump_json(exclude_none=True, indent=2) + "\n")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
