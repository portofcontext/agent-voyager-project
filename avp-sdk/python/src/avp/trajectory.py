"""ATIF wire models and document IO, using Harbor's pinned reference models."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from avp._files import atomic_write, local_path, write_document
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
from avp.agent_start import AgentStart
from avp.commission import Commission
from avp.descriptor import AgentDescriptor


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


def final_output(trajectory: Trajectory) -> Any:
    """Returned value, falling back to the final root agent message in ATIF."""
    meta = avp_metadata(trajectory)
    if "output" in meta:
        return meta["output"]
    if meta.get("complete") is False:
        return None
    for step in reversed(trajectory.steps):
        if step.source == "agent":
            return (
                step.message
                if isinstance(step.message, str)
                else [part.model_dump(mode="json", exclude_none=True) for part in step.message]
            )
    return None


@dataclass(frozen=True)
class Recording:
    """A snapshot of the current ATIF document and referenced media bytes."""

    trajectory: Trajectory
    assets: dict[str, bytes] = field(default_factory=dict)
    commission: Commission | None = None
    descriptor: AgentDescriptor | None = None
    agent_start: AgentStart | None = None

    def write(self, path: Path) -> None:
        """Publish start documents and referenced images before the ATIF snapshot."""
        if path.name in {"commission.json", "descriptor.json", "agent-start.json"}:
            raise ValueError("trajectory path conflicts with a run document")
        path.parent.mkdir(parents=True, exist_ok=True)
        for name, document in (
            ("commission.json", self.commission),
            ("descriptor.json", self.descriptor),
            ("agent-start.json", self.agent_start),
        ):
            if document is not None:
                write_document(path.parent, name, document)
        for name, content in self.assets.items():
            target = local_path(path.parent, name)
            if target.resolve() == path.resolve():
                raise ValueError("an image cannot replace the trajectory")
            if not target.exists():
                atomic_write(target, content)
            elif target.read_bytes() != content:
                raise ValueError(f"image already exists with different content: {name}")
        atomic_write(
            path, (self.trajectory.model_dump_json(exclude_none=True, indent=2) + "\n").encode()
        )
