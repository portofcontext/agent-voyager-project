"""ATIF wire models and document IO, using Harbor's pinned reference models."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
from avp.artifacts import ArtifactFile, atomic_write, write_artifacts


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
    artifacts: dict[str, ArtifactFile] = field(default_factory=dict)

    def write(self, path: Path) -> None:
        """Publish assets first, then atomically replace the readable document."""
        path.parent.mkdir(parents=True, exist_ok=True)
        files = self.artifacts.copy()
        for name, content in self.assets.items():
            file = ArtifactFile(content, "output")
            if name in files and files[name] != file:
                raise ValueError(f"conflicting media artifact: {name}")
            files[name] = file
        if path.name == "artifacts.json" or path.name in files:
            raise ValueError("an artifact cannot replace the trajectory")
        write_artifacts(path.parent, self.trajectory.session_id or "unknown", files)
        atomic_write(
            path, (self.trajectory.model_dump_json(exclude_none=True, indent=2) + "\n").encode()
        )
